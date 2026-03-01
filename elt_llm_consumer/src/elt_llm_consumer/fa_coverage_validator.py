"""FA Coverage Validator.

Answers: does the FA conceptual model contain the right entities, as validated
against the FA Handbook?

Two-direction analysis — no LLM synthesis, pure retrieval scoring:

  Direction 1 — Model → Handbook (coverage check)
      For every entity in the LeanIX conceptual model XML, retrieve chunks from
      the FA Handbook collection and score how much content exists.
      No LLM call — pure embedding similarity. ~3-7 min for ~217 entities.

  Direction 2 — Handbook → Model (gap check)  [--gap-analysis]
      If fa_handbook_candidate_entities.json exists (Consumer 2 output), compare
      entity name lists to find:
        MODEL_ONLY    — in conceptual model, not mentioned in handbook
        HANDBOOK_ONLY — handbook discusses it, but it is absent from the model
        MATCHED       — present in both

Verdict bands (cosine similarity of top retrieved chunk):
  STRONG    ≥ 0.70  — handbook clearly discusses this entity
  MODERATE  0.55–0.70 — handbook mentions it; some governance context available
  THIN      0.40–0.55 — weak signal; handbook may use different terminology
  ABSENT    < 0.40  — entity not meaningfully present in handbook

Outputs (~/Documents/__data/resources/thefa/):
  fa_coverage_report.json   — per-entity: domain, score, verdict
  fa_gap_analysis.json      — bidirectional gap table (requires --gap-analysis)

Output format: JSON (not CSV) to properly support multi-line content,
hierarchical structures, and nested fields from combined data sources.

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator

    uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator \\
        --gap-analysis

    RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator

Runtime: ~217 entities × 1-2 s retrieval = 3-7 min (no LLM, embedding only)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_query.query import load_index, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_XML = Path(
    "~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path("~/.tmp/elt_llm_consumer").expanduser()

_DEFAULT_HANDBOOK_JSON = _DEFAULT_OUTPUT_DIR / "fa_handbook_candidate_entities.json"

# ---------------------------------------------------------------------------
# Verdict thresholds (cosine similarity of top retrieved chunk)
# ---------------------------------------------------------------------------

_STRONG = 0.70
_MODERATE = 0.55
_THIN = 0.40
_DEFAULT_TOP_K = 5  # chunks retrieved per entity

# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------


def load_conceptual_model_entities(xml_path: Path) -> list[dict]:
    """Parse LeanIX draw.io XML → list of entity dicts."""
    try:
        from elt_llm_ingest.doc_leanix_parser import LeanIXExtractor
    except ImportError:
        print(
            "ERROR: elt_llm_ingest not available. Run: uv sync --all-packages",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Parsing XML: {xml_path}")
    extractor = LeanIXExtractor(str(xml_path))
    extractor.parse_xml()
    extractor.extract_all()

    entities: list[dict] = []
    for asset in extractor.assets.values():
        if not asset.label or not asset.fact_sheet_id:
            continue
        entities.append({
            "fact_sheet_id": asset.fact_sheet_id,
            "entity_name": asset.label,
            "domain": asset.parent_group or "UNKNOWN",
        })

    print(f"  {len(entities)} entities loaded from conceptual model")
    return entities


def load_handbook_entities(csv_path: Path) -> list[str]:
    """Load entity names from Consumer 2 (fa_handbook_model_builder) output CSV."""
    if not csv_path.exists():
        return []
    names: list[str] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            name = (row.get("entity_name") or row.get("entity") or "").strip()
            if name:
                names.append(name)
    print(f"  {len(names)} handbook-discovered entities loaded from {csv_path.name}")
    return names


# ---------------------------------------------------------------------------
# Checkpoint
# ---------------------------------------------------------------------------


def load_checkpoint(out_path: Path) -> set[str]:
    """Return set of fact_sheet_ids already written."""
    if not out_path.exists():
        return set()
    done: set[str] = set()
    with open(out_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        for row in data:
            fsid = (row.get("fact_sheet_id") or "").strip()
            if fsid:
                done.add(fsid)
    print(f"  Resuming — {len(done)} rows already written")
    return done


# ---------------------------------------------------------------------------
# Coverage scoring (retrieval only — no LLM)
# ---------------------------------------------------------------------------


def score_entity(
    entity_name: str,
    domain: str,
    index,
    top_k: int,
) -> dict:
    """Retrieve handbook chunks for an entity; return coverage metrics.

    No LLM synthesis — purely measures retrieval similarity so the whole run
    completes in minutes rather than hours.
    """
    query = (
        f"{entity_name} FA Football Association {domain} "
        "rules obligations governance handbook"
    )
    retriever = index.as_retriever(similarity_top_k=top_k)
    try:
        nodes = retriever.retrieve(query)
    except Exception as exc:
        return {
            "chunks_found": 0,
            "top_score": 0.0,
            "avg_score": 0.0,
            "top_chunk_preview": "",
            "error": str(exc),
        }

    scores = [n.score for n in nodes if n.score is not None]
    top_text = nodes[0].node.text[:120].replace("\n", " ").strip() if nodes else ""

    if not scores:
        return {
            "chunks_found": 0,
            "top_score": 0.0,
            "avg_score": 0.0,
            "top_chunk_preview": "",
        }

    return {
        "chunks_found": len(scores),
        "top_score": round(max(scores), 4),
        "avg_score": round(sum(scores) / len(scores), 4),
        "top_chunk_preview": top_text,
    }


def coverage_verdict(top_score: float, chunks_found: int) -> str:
    if chunks_found == 0 or top_score < _THIN:
        return "ABSENT"
    if top_score < _MODERATE:
        return "THIN"
    if top_score < _STRONG:
        return "MODERATE"
    return "STRONG"


# ---------------------------------------------------------------------------
# Direction 1: Model → Handbook
# ---------------------------------------------------------------------------


def run_coverage_check(
    entities: list[dict],
    handbook_index,
    top_k: int,
    output_dir: Path,
    resume: bool,
) -> dict[str, int]:
    """Score every model entity against FA Handbook. Returns verdict counts."""
    out_path = output_dir / "fa_coverage_report.json"
    done = load_checkpoint(out_path) if resume else set()

    total = len(entities)
    written = 0
    verdicts: dict[str, int] = {"STRONG": 0, "MODERATE": 0, "THIN": 0, "ABSENT": 0}

    # Load existing results for resume mode
    all_results: list[dict] = []
    if resume and out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            all_results = json.load(f)
        print(f"  Loaded {len(all_results)} existing results from checkpoint")

    print(f"\n=== Direction 1: Model → Handbook ({total} entities) ===")

    for i, entity in enumerate(entities, 1):
        fsid = entity["fact_sheet_id"]
        if fsid in done:
            continue

        name = entity["entity_name"]
        domain = entity["domain"]
        print(f"  [{i}/{total}] {name} ({domain})…", end=" ", flush=True)

        metrics = score_entity(name, domain, handbook_index, top_k)
        v = coverage_verdict(metrics["top_score"], metrics["chunks_found"])
        verdicts[v] = verdicts.get(v, 0) + 1
        print(f"{v} (top={metrics['top_score']})")

        all_results.append({
            "fact_sheet_id": fsid,
            "entity_name": name,
            "domain": domain,
            "chunks_found": metrics["chunks_found"],
            "top_score": metrics["top_score"],
            "avg_score": metrics["avg_score"],
            "verdict": v,
            "top_chunk_preview": metrics.get("top_chunk_preview", ""),
        })

        # Write checkpoint after each entity
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2, ensure_ascii=False)

        written += 1

    print(f"\n  Written: {written} new rows → {out_path}")
    return verdicts


# ---------------------------------------------------------------------------
# Direction 2: Handbook → Model (gap analysis)
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Lowercase + collapse whitespace for fuzzy matching."""
    return " ".join(name.lower().split())


def run_gap_analysis(
    model_entities: list[dict],
    handbook_json: Path,
    output_dir: Path,
) -> None:
    """Bidirectional diff of model entity names vs handbook-discovered names."""
    handbook_names = load_handbook_entities(handbook_json)
    if not handbook_names:
        print(
            f"\n  Gap analysis skipped — {handbook_json.name} not found.\n"
            "  Run Consumer 2 first:\n"
            "    uv run --package elt-llm-consumer elt-llm-consumer-handbook-model"
        )
        return

    model_norm: dict[str, str] = {_normalize(e["entity_name"]): e["entity_name"]
                                   for e in model_entities}
    handbook_norm: dict[str, str] = {_normalize(n): n for n in handbook_names}

    all_keys = sorted(set(model_norm) | set(handbook_norm))
    rows: list[dict] = []
    counts = {"MATCHED": 0, "MODEL_ONLY": 0, "HANDBOOK_ONLY": 0}

    for key in all_keys:
        in_model = key in model_norm
        in_handbook = key in handbook_norm
        if in_model and in_handbook:
            status = "MATCHED"
        elif in_model:
            status = "MODEL_ONLY"
        else:
            status = "HANDBOOK_ONLY"
        counts[status] += 1
        rows.append({
            "normalized_name": key,
            "model_name": model_norm.get(key, ""),
            "handbook_name": handbook_norm.get(key, ""),
            "status": status,
        })

    out_path = output_dir / "fa_gap_analysis.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    print(f"\n=== Gap Analysis ===")
    print(f"  MATCHED:       {counts['MATCHED']}")
    print(f"  MODEL_ONLY:    {counts['MODEL_ONLY']}  ← in model, not in handbook")
    print(f"  HANDBOOK_ONLY: {counts['HANDBOOK_ONLY']}  ← in handbook, missing from model")
    print(f"  Gap report → {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate FA conceptual model entity coverage against the FA Handbook. "
            "No LLM — pure retrieval scoring."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Direction 1 always runs: scores every model entity against fa_handbook RAG.\n"
            "Direction 2 (--gap-analysis): compares entity name lists (requires Consumer 2 output).\n\n"
            "Verdict thresholds (cosine similarity):\n"
            f"  STRONG ≥ {_STRONG}  |  MODERATE {_MODERATE}–{_STRONG}"
            f"  |  THIN {_THIN}–{_MODERATE}  |  ABSENT < {_THIN}\n\n"
            "Resume:  RESUME=1 elt-llm-consumer-coverage-validator\n"
            "Output:  JSON format (not CSV) for multi-line content support"
        ),
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_RAG_CONFIG,
        help=f"Path to rag_config.yaml (default: {_DEFAULT_RAG_CONFIG})",
    )
    parser.add_argument(
        "--xml", type=Path, default=_DEFAULT_XML,
        help=f"Path to LeanIX draw.io XML (default: {_DEFAULT_XML})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--top-k", type=int, default=_DEFAULT_TOP_K,
        help=f"Handbook chunks to retrieve per entity (default: {_DEFAULT_TOP_K})",
    )
    parser.add_argument(
        "--gap-analysis", action="store_true",
        help="Also run bidirectional gap analysis (Direction 2)",
    )
    parser.add_argument(
        "--handbook-json", type=Path, default=_DEFAULT_HANDBOOK_CSV.with_suffix(".json"),
        help=f"Consumer 2 entity JSON for gap analysis (default: {_DEFAULT_HANDBOOK_CSV.with_suffix('.json')})",
    )
    args = parser.parse_args()
    resume = os.environ.get("RESUME", "0") == "1"

    xml_path = args.xml.expanduser()
    output_dir = args.output_dir.expanduser()

    if not xml_path.exists():
        print(f"ERROR: XML not found: {xml_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)
    print(f"  Embedding model: {rag_config.ollama.embedding_model}")
    if resume:
        print("  Mode: RESUME (skipping already-written rows)")

    print("\nLoading sources…")
    entities = load_conceptual_model_entities(xml_path)

    print(f"\nLoading FA Handbook index (retrieval only — no LLM)…")
    handbook_index = load_index("fa_handbook", rag_config)
    print("  Index loaded")

    verdicts = run_coverage_check(entities, handbook_index, args.top_k, output_dir, resume)

    print("\n=== Coverage Summary ===")
    total = sum(verdicts.values())
    for v in ("STRONG", "MODERATE", "THIN", "ABSENT"):
        n = verdicts.get(v, 0)
        pct = round(n / total * 100) if total else 0
        bar = "█" * (pct // 5)
        print(f"  {v:<10} {n:>3}  {pct:>3}%  {bar}")

    if args.gap_analysis:
        handbook_json = args.handbook_json.expanduser()
        run_gap_analysis(entities, handbook_json, output_dir)

    print("\n=== Complete ===")
    print(f"  Coverage report → {output_dir / 'fa_coverage_report.json'}")
    if args.gap_analysis:
        print(f"  Gap analysis    → {output_dir / 'fa_gap_analysis.json'}")
