"""FA Handbook → LeanIX Glossary Mapper.

Extracts all defined terms from the FA Handbook collection and maps each to its
corresponding entity in the LeanIX Enterprise Conceptual Data Model.

Term source: the fa_handbook docstore — all nodes containing definition chunks
produced by RegulatoryPDFPreprocessor (format:
  **FA Handbook defined term** [source: explicit|detected|both]: TERM means DEFINITION.)

Process:
  Step 1 — Extract terms from fa_handbook docstore (~700 terms from Sections 8
            and 23, tagged with source confidence: explicit / detected / both)
  Step 2 — Map each term to a LeanIX conceptual model entity
            (queries fa_leanix_dat_enterprise_conceptual_model_* collections)
  Step 3 — Optionally enrich with inventory descriptions
            (queries fa_leanix_global_inventory_* collections; use --enrich)

Outputs (elt_llm_rag/.tmp/):
  fa_handbook_glossary.json  — per-term: handbook definition, LeanIX entity,
                               domain, fact_sheet_id, mapping confidence,
                               governance_rules (from ToR file if available)

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-handbook-glossary

    # Enrich mapped terms with LeanIX inventory descriptions
    uv run --package elt-llm-consumer elt-llm-consumer-handbook-glossary --enrich

    # Resume after interruption
    RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-handbook-glossary

    # Supplement governance rules from an existing ToR file
    uv run --package elt-llm-consumer elt-llm-consumer-handbook-glossary \\
        --tor-json elt_llm_rag/.tmp/fa_handbook_terms_of_reference.json

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b

Runtime: ~700 terms × 10–20 s each ≈ 2–4 hours (varies by model and hardware)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

_HANDBOOK_COLLECTION = "fa_handbook"
_CONCEPTUAL_MODEL_PREFIX = "fa_leanix_dat_enterprise_conceptual_model"
_INVENTORY_PREFIX = "fa_leanix_global_inventory"

# Definition chunk marker produced by RegulatoryPDFPreprocessor
_DEF_MARKER = "**FA Handbook defined term**"
_DEF_LINE_PAT = re.compile(
    r"\*\*FA Handbook defined term\*\* \[source: (\w+)\]: (.+?) means (.+)",
)

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert FA Enterprise Architect and Data Management consultant.
You have access to the FA LeanIX Enterprise Conceptual Data Model, which defines
the canonical entities, domains, and relationships for The Football Association's
enterprise data landscape.

When mapping terms:
- Only map to entities that explicitly exist in the conceptual model.
- If a term is a sub-type or synonym of an entity, map it to that entity and explain.
- If a term is operational, procedural, or not represented as a distinct entity, respond with ENTITY: Not mapped.
- Ground every answer in the retrieved content. Do not invent entity names or IDs."""

# ---------------------------------------------------------------------------
# Query templates
# ---------------------------------------------------------------------------

_MAPPING_QUERY = """\
The FA Handbook defines the term '{term}' as:
"{definition}"

In the FA Enterprise Conceptual Data Model (LeanIX), which entity does this term correspond to?

Provide:
ENTITY: [exact entity name from the model, or "Not mapped" if no entity matches]
DOMAIN: [domain the entity belongs to, e.g. PARTY, PRODUCT, AGREEMENTS, TRANSACTION AND EVENTS]
FACT_SHEET_ID: [LeanIX fact sheet ID if shown in the retrieved content, otherwise leave blank]
CONFIDENCE: [high / medium / low]
RATIONALE: [one sentence explaining the mapping]"""

_INVENTORY_QUERY = """\
Provide the LeanIX inventory description for the entity '{entity}'.
Use the LeanIX global inventory fact sheet content.

DESCRIPTION: [inventory description from LeanIX, or "Not documented" if not found]"""

# ---------------------------------------------------------------------------
# Term extraction from docstore
# ---------------------------------------------------------------------------


def extract_terms_from_docstore(rag_config: RagConfig) -> list[dict]:
    """Load all nodes from the fa_handbook docstore and extract definition terms.

    Filters nodes for lines produced by RegulatoryPDFPreprocessor in the format:
      **FA Handbook defined term** [source: explicit]: TERM means DEFINITION.

    Returns:
        List of dicts with keys: term, definition, definition_source.
    """
    from llama_index.core import StorageContext

    docstore_path = get_docstore_path(rag_config.chroma, _HANDBOOK_COLLECTION)
    if not docstore_path.exists():
        print(
            f"ERROR: Docstore not found at {docstore_path}.\n"
            "Run ingestion first: "
            "uv run python -m elt_llm_ingest.runner ingest ingest_fa_handbook",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Loading docstore from: {docstore_path}")
    storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
    nodes = list(storage.docstore.docs.values())
    print(f"  {len(nodes)} total nodes in fa_handbook docstore")

    terms: list[dict] = []
    seen: set[str] = set()

    for node in nodes:
        text = getattr(node, "text", "") or ""
        for line in text.splitlines():
            line = line.strip()
            if _DEF_MARKER not in line:
                continue
            m = _DEF_LINE_PAT.match(line)
            if not m:
                continue
            source = m.group(1).strip().lower()
            term = m.group(2).strip()
            defn = m.group(3).strip().rstrip(".")
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append({"term": term, "definition": defn, "definition_source": source})

    # Sort alphabetically for consistent ordering
    terms.sort(key=lambda x: x["term"].lower())
    print(f"  {len(terms)} unique defined terms extracted")
    return terms


# ---------------------------------------------------------------------------
# ToR enrichment (governance rules from existing ToR file)
# ---------------------------------------------------------------------------


def load_tor_index(tor_path: Path) -> dict[str, dict]:
    """Load ToR JSON and return a dict keyed by lowercased term."""
    with open(tor_path, encoding="utf-8") as f:
        data = json.load(f)
    return {row["term"].lower(): row for row in data if row.get("term")}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_checkpoint(out_path: Path) -> set[str]:
    """Return lowercased set of terms already written to the output JSON."""
    if not out_path.exists():
        return set()
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)
    done = {row["term"].lower() for row in data if row.get("term")}
    print(f"  Resuming — {len(done)} terms already written to {out_path.name}")
    return done


def run_query(query: str, collections: list[str], rag_config: RagConfig) -> str:
    """Query collections and return the synthesised response."""
    try:
        result = query_collections(collections, query, rag_config)
        return result.response.strip()
    except Exception as e:
        return f"[Query failed: {e}]"


def parse_mapping_response(response: str) -> dict:
    """Parse structured mapping response into a dict."""
    result: dict = {}
    for line in response.splitlines():
        line = line.strip()
        for key in ("ENTITY", "DOMAIN", "FACT_SHEET_ID", "CONFIDENCE", "RATIONALE"):
            if line.startswith(f"{key}:"):
                result[key.lower()] = line[len(key) + 1:].strip()
                break
    return result


def parse_inventory_response(response: str) -> str:
    """Extract DESCRIPTION value from inventory response."""
    for line in response.splitlines():
        line = line.strip()
        if line.startswith("DESCRIPTION:"):
            return line[len("DESCRIPTION:"):].strip()
    return response.strip()


# ---------------------------------------------------------------------------
# Main mapping loop
# ---------------------------------------------------------------------------


def run_mapping(
    terms: list[dict],
    model_collections: list[str],
    inventory_collections: list[str],
    rag_config: RagConfig,
    tor_index: dict[str, dict],
    output_dir: Path,
    enrich: bool,
    resume: bool,
) -> None:
    """Map each handbook term to a LeanIX conceptual model entity."""
    out_path = output_dir / "fa_handbook_glossary.json"
    done = load_checkpoint(out_path) if resume else set()

    all_rows: list[dict] = []
    if resume and out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            all_rows = json.load(f)
        print(f"  Loaded {len(all_rows)} existing rows from checkpoint")

    model = rag_config.ollama.llm_model
    total = len(terms)

    for i, term_entry in enumerate(terms, 1):
        term = term_entry["term"]
        if term.lower() in done:
            continue

        definition = term_entry["definition"]
        def_source = term_entry["definition_source"]
        print(f"  [{i}/{total}] {term}…", end=" ", flush=True)

        # Step 1: Map to LeanIX conceptual model entity
        mapping_resp = run_query(
            _MAPPING_QUERY.format(term=term, definition=definition),
            model_collections,
            rag_config,
        )
        mapping = parse_mapping_response(mapping_resp)
        entity = mapping.get("entity", "Not mapped")
        is_mapped = entity.lower() not in ("not mapped", "not_mapped", "")

        # Step 2: Optionally enrich with inventory description
        inventory_description = ""
        if enrich and is_mapped and inventory_collections:
            inv_resp = run_query(
                _INVENTORY_QUERY.format(entity=entity),
                inventory_collections,
                rag_config,
            )
            inventory_description = parse_inventory_response(inv_resp)

        # Step 3: Pull governance rules from ToR index if available
        tor_entry = tor_index.get(term.lower(), {})
        governance_rules = tor_entry.get("governance_rules", "")

        row = {
            "term": term,
            "handbook_definition": definition,
            "definition_source": def_source,
            "leanix_entity": entity,
            "leanix_domain": mapping.get("domain", ""),
            "fact_sheet_id": mapping.get("fact_sheet_id", ""),
            "mapping_confidence": mapping.get("confidence", ""),
            "mapping_rationale": mapping.get("rationale", ""),
            "inventory_description": inventory_description,
            "governance_rules": governance_rules,
            "model_used": model,
        }
        all_rows.append(row)
        done.add(term.lower())
        print(f"→ {entity}" if is_mapped else "→ not mapped")

        # Checkpoint after each term
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_rows, f, indent=2, ensure_ascii=False)

    mapped = sum(
        1 for r in all_rows
        if r.get("leanix_entity", "").lower() not in ("not mapped", "not_mapped", "")
    )
    print(f"\n  Glossary → {out_path}")
    print(f"  {mapped}/{len(all_rows)} terms mapped to LeanIX entities")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map FA Handbook defined terms to LeanIX conceptual model entities",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b\n"
            "Resume:  RESUME=1 elt-llm-consumer-handbook-glossary\n"
            "Output:  elt_llm_rag/.tmp/fa_handbook_glossary.json"
        ),
    )
    parser.add_argument(
        "--model", default=None,
        help="Override LLM model (default: from rag_config.yaml)",
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_RAG_CONFIG,
        help=f"Path to rag_config.yaml (default: {_DEFAULT_RAG_CONFIG})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--tor-json", type=Path, default=None,
        help=(
            "Path to fa_handbook_terms_of_reference.json to supplement governance_rules "
            "(default: auto-detect from output directory)"
        ),
    )
    parser.add_argument(
        "--enrich", action="store_true", default=False,
        help="Also query LeanIX inventory for descriptions of mapped entities",
    )
    args = parser.parse_args()
    resume = os.environ.get("RESUME", "0") == "1"

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    if args.model:
        rag_config.ollama.llm_model = args.model
        print(f"  Model override: {args.model}")

    rag_config.query.system_prompt = _SYSTEM_PROMPT
    print(f"  LLM:    {rag_config.ollama.llm_model}")
    if resume:
        print("  Mode:   RESUME")
    if args.enrich:
        print("  Enrich: enabled (will query inventory for mapped entities)")

    # Step 1: Extract terms from docstore
    print("\nExtracting terms from fa_handbook docstore…")
    terms = extract_terms_from_docstore(rag_config)
    if not terms:
        print(
            "ERROR: No definition terms found in fa_handbook docstore.\n"
            "Ensure fa_handbook was ingested with RegulatoryPDFPreprocessor "
            "and def_sections configured.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load ToR index for governance_rules supplementation
    tor_index: dict[str, dict] = {}
    tor_path = args.tor_json or (output_dir / "fa_handbook_terms_of_reference.json")
    if tor_path.exists():
        tor_index = load_tor_index(tor_path)
        print(f"  ToR index loaded: {len(tor_index)} entries from {tor_path.name}")
    else:
        print(
            f"  ToR file not found at {tor_path.name} — governance_rules will be empty. "
            "Run elt-llm-consumer-handbook-model first to generate it."
        )

    # Step 2: Resolve collections
    print("\nResolving collections…")
    model_collections = resolve_collection_prefixes([_CONCEPTUAL_MODEL_PREFIX], rag_config)
    if not model_collections:
        print(
            f"ERROR: No collections found matching '{_CONCEPTUAL_MODEL_PREFIX}_*'.\n"
            "Run: uv run python -m elt_llm_ingest.runner ingest "
            "ingest_fa_leanix_dat_enterprise_conceptual_model",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"  Conceptual model ({len(model_collections)}): {', '.join(model_collections)}")

    inventory_collections: list[str] = []
    if args.enrich:
        inventory_collections = resolve_collection_prefixes([_INVENTORY_PREFIX], rag_config)
        if not inventory_collections:
            print(
                f"  WARNING: No inventory collections found matching '{_INVENTORY_PREFIX}_*' — "
                "inventory enrichment will be skipped."
            )
        else:
            print(
                f"  Inventory ({len(inventory_collections)}): {', '.join(inventory_collections)}"
            )

    # Step 3: Map terms
    print(f"\nMapping {len(terms)} terms…")
    run_mapping(
        terms=terms,
        model_collections=model_collections,
        inventory_collections=inventory_collections,
        rag_config=rag_config,
        tor_index=tor_index,
        output_dir=output_dir,
        enrich=args.enrich,
        resume=resume,
    )

    print("\n=== Complete ===")
    print(f"  Glossary → {output_dir / 'fa_handbook_glossary.json'}")
