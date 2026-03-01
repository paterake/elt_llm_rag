"""FA Handbook conceptual model builder.

Discovers candidate entities, terms of reference, and relationships from the
FA Handbook *alone* — no LeanIX required. Useful for bootstrapping or for
validating the LeanIX conceptual model against the authoritative governance text.

Process (two passes):
  Pass 1 — Entity extraction: query fa_handbook per seed topic to discover
            defined terms, roles, organisations, and concepts.
  Pass 2 — Relationship extraction: for entity pairs that co-appeared in the
            same topic, query how they relate.

Outputs (~/Documents/__data/resources/thefa/):
  fa_handbook_candidate_entities.json       ← discovered terms + definitions
  fa_handbook_candidate_relationships.json  ← inferred relationships
  fa_handbook_terms_of_reference.json       ← consolidated ToR per term

Output format: JSON (not CSV) to properly support multi-line content,
hierarchical structures, and nested fields from combined data sources.

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-handbook-model

    # Subset of topics
    uv run --package elt-llm-consumer elt-llm-consumer-handbook-model \\
        --topics Club Player Competition

    # Override model
    uv run --package elt-llm-consumer elt-llm-consumer-handbook-model \\
        --model qwen2.5:14b

    # Resume after interruption (Pass 1 only; Pass 2 always re-runs)
    RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-handbook-model

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
from itertools import combinations
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_query.query import query_collections

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

# ---------------------------------------------------------------------------
# Seed topics — FA Handbook domain areas
# ---------------------------------------------------------------------------

_DEFAULT_TOPICS = [
    "Club",
    "Player",
    "Official",
    "Referee",
    "Competition",
    "County FA",
    "Registration",
    "Transfer",
    "Affiliation",
    "Discipline",
    "Safeguarding",
    "Governance",
    "Eligibility",
    "Licence",
]

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert in FA governance and data modelling. You have access to the FA Handbook,
which is the authoritative source for all FA rules, regulations, and definitions.

When extracting entities and terms:
- Only include terms that are explicitly defined or formally described in the FA Handbook.
- Do not invent or infer terms not present in the source.
- Use the exact wording of definitions where available.
- Cite the relevant section or rule number where possible."""

# ---------------------------------------------------------------------------
# Query templates
# ---------------------------------------------------------------------------

_ENTITY_QUERY = """\
In the FA Handbook, what entities, roles, organisations, and concepts are formally defined
or described in relation to '{topic}'?

For each one, provide:
TERM: [exact name as used in the Handbook]
DEFINITION: [definition or description from the Handbook]
CATEGORY: [one of: role / organisation / document / event / rule / process / data_entity]
GOVERNANCE: [any specific rules, obligations, or regulatory requirements that apply]

List every distinct term you can find. If a term appears in multiple contexts, give the
primary definition. Only include terms that are explicitly present in the Handbook."""

_RELATIONSHIP_QUERY = """\
According to the FA Handbook, how does '{entity_a}' relate to '{entity_b}'?

Describe:
RELATIONSHIP: [how they are connected — e.g. "A Club must register each Player"]
DIRECTION: [which governs or depends on the other, if applicable]
RULES: [any FA Handbook rules that govern this relationship]

If no relationship is described in the Handbook between these two entities, respond with:
RELATIONSHIP: Not documented"""

_TOR_QUERY = """\
Provide a consolidated Terms of Reference entry for the FA term '{term}'.

Draw on all relevant sections of the FA Handbook to provide:
FORMAL_DEFINITION: [the most precise definition available]
CATEGORY: [role / organisation / document / event / rule / process / data_entity]
GOVERNANCE_RULES: [key obligations, requirements, and regulatory context]
RELATED_TERMS: [other FA Handbook terms that are directly connected to this one]

If this term is not formally defined in the FA Handbook, state 'Not documented' for
FORMAL_DEFINITION."""

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def load_checkpoint(out_path: Path) -> set[str]:
    """Return set of terms already written to the output JSON."""
    if not out_path.exists():
        return set()
    done: set[str] = set()
    with open(out_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        for row in data:
            term = (row.get("term") or row.get("entity_a") or "").strip()
            if term:
                done.add(term.lower())
    print(f"  Resuming — {len(done)} rows already written to {out_path.name}")
    return done


def run_query(query: str, collections: list[str], rag_config: RagConfig) -> str:
    """Query and return the synthesised response text."""
    try:
        result = query_collections(collections, query, rag_config)
        return result.response.strip()
    except Exception as e:
        return f"[Query failed: {e}]"


def parse_entity_response(response: str, topic: str) -> list[dict]:
    """Parse structured entity response into list of dicts."""
    entities: list[dict] = []
    current: dict = {}

    for line in response.splitlines():
        line = line.strip()
        if not line:
            if current.get("term"):
                entities.append(current)
                current = {}
            continue
        for key in ("TERM", "DEFINITION", "CATEGORY", "GOVERNANCE"):
            if line.startswith(f"{key}:"):
                current[key.lower()] = line[len(key) + 1:].strip()
                break

    if current.get("term"):
        entities.append(current)

    # Attach source topic
    for e in entities:
        e["source_topic"] = topic

    return entities


def parse_tor_response(response: str) -> dict:
    """Parse structured ToR response into a dict."""
    result: dict = {}
    for line in response.splitlines():
        line = line.strip()
        for key in ("FORMAL_DEFINITION", "CATEGORY", "GOVERNANCE_RULES", "RELATED_TERMS"):
            if line.startswith(f"{key}:"):
                result[key.lower()] = line[len(key) + 1:].strip()
                break
    return result


# ---------------------------------------------------------------------------
# Pass 1 — Entity extraction
# ---------------------------------------------------------------------------


def run_pass1(
    topics: list[str],
    collections: list[str],
    rag_config: RagConfig,
    output_dir: Path,
    resume: bool,
) -> list[dict]:
    """Query each topic area and collect candidate entities."""
    out_path = output_dir / "fa_handbook_candidate_entities.json"
    done = load_checkpoint(out_path) if resume else set()

    all_entities: list[dict] = []
    model = rag_config.ollama.llm_model

    # Load existing entities for resume mode
    if resume and out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            all_entities = json.load(f)
        print(f"  Loaded {len(all_entities)} existing entities from checkpoint")

    print("\n=== Pass 1: Entity Extraction ===")

    for i, topic in enumerate(topics, 1):
        if topic.lower() in done:
            print(f"  [{i}/{len(topics)}] {topic} — skipped (resume)")
            continue

        print(f"  [{i}/{len(topics)}] {topic}…", end=" ", flush=True)
        response = run_query(_ENTITY_QUERY.format(topic=topic), collections, rag_config)
        entities = parse_entity_response(response, topic)
        print(f"{len(entities)} entities found")

        for entity in entities:
            entity["model_used"] = model
            all_entities.append(entity)

        # Write checkpoint after each topic
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_entities, f, indent=2, ensure_ascii=False)

    print(f"\n  Entities → {out_path}")
    return all_entities


# ---------------------------------------------------------------------------
# Pass 2 — Relationship extraction
# ---------------------------------------------------------------------------


def run_pass2(
    entities: list[dict],
    collections: list[str],
    rag_config: RagConfig,
    output_dir: Path,
) -> None:
    """For pairs of entities from the same topic, infer relationships."""
    out_path = output_dir / "fa_handbook_candidate_relationships.json"

    # Group entities by source_topic
    by_topic: dict[str, list[str]] = {}
    for e in entities:
        topic = e.get("source_topic", "")
        term = e.get("term", "").strip()
        if topic and term:
            by_topic.setdefault(topic, []).append(term)

    # Build unique pairs within same topic (limit to 3 per topic to avoid explosion)
    pairs: list[tuple[str, str]] = []
    seen: set[frozenset] = set()
    for topic_terms in by_topic.values():
        for a, b in combinations(topic_terms[:5], 2):  # cap at first 5 terms per topic
            key = frozenset([a.lower(), b.lower()])
            if key not in seen:
                seen.add(key)
                pairs.append((a, b))

    model = rag_config.ollama.llm_model
    total = len(pairs)
    all_relationships: list[dict] = []

    print(f"\n=== Pass 2: Relationship Extraction ({total} pairs) ===")

    for i, (a, b) in enumerate(pairs, 1):
        print(f"  [{i}/{total}] {a} ↔ {b}…", end=" ", flush=True)
        response = run_query(
            _RELATIONSHIP_QUERY.format(entity_a=a, entity_b=b),
            collections,
            rag_config,
        )
        row: dict = {"entity_a": a, "entity_b": b, "model_used": model}
        for line in response.splitlines():
            for key in ("RELATIONSHIP", "DIRECTION", "RULES"):
                if line.strip().startswith(f"{key}:"):
                    row[key.lower()] = line.strip()[len(key) + 1:].strip()
                    break
        all_relationships.append(row)
        print("done")

        # Write checkpoint after each relationship
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_relationships, f, indent=2, ensure_ascii=False)

    print(f"\n  Relationships → {out_path}")


# ---------------------------------------------------------------------------
# Pass 3 — Terms of Reference consolidation
# ---------------------------------------------------------------------------


def run_pass3(
    entities: list[dict],
    collections: list[str],
    rag_config: RagConfig,
    output_dir: Path,
    resume: bool,
) -> None:
    """Build a consolidated ToR entry for each unique discovered term."""
    out_path = output_dir / "fa_handbook_terms_of_reference.json"

    # Deduplicate terms (keep first occurrence per term name)
    seen_terms: dict[str, dict] = {}
    for e in entities:
        term = e.get("term", "").strip()
        if term and term.lower() not in {k.lower() for k in seen_terms}:
            seen_terms[term] = e

    done = load_checkpoint(out_path) if resume else set()
    total = len(seen_terms)
    model = rag_config.ollama.llm_model

    # Load existing ToR for resume mode
    all_tor: list[dict] = []
    if resume and out_path.exists():
        with open(out_path, "r", encoding="utf-8") as f:
            all_tor = json.load(f)
        print(f"  Loaded {len(all_tor)} existing ToR entries from checkpoint")

    print(f"\n=== Pass 3: Terms of Reference ({total} unique terms) ===")

    for i, (term, entity) in enumerate(seen_terms.items(), 1):
        if term.lower() in done:
            print(f"  [{i}/{total}] {term} — skipped (resume)")
            continue

        print(f"  [{i}/{total}] {term}…", end=" ", flush=True)
        response = run_query(_TOR_QUERY.format(term=term), collections, rag_config)
        tor = parse_tor_response(response)

        tor_row = {
            "term": term,
            "category": tor.get("category") or entity.get("category", ""),
            "formal_definition": tor.get("formal_definition") or entity.get("definition", ""),
            "governance_rules": tor.get("governance_rules") or entity.get("governance", ""),
            "related_terms": tor.get("related_terms", ""),
            "source_topic": entity.get("source_topic", ""),
            "model_used": model,
        }
        all_tor.append(tor_row)

        # Write checkpoint after each term
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_tor, f, indent=2, ensure_ascii=False)

        print("done")

    print(f"\n  Terms of Reference → {out_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build candidate conceptual model and ToR from FA Handbook only",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, "
            "llama3.1:8b, granite3.1-dense:8b, michaelborck/refuled\n"
            "Resume:  RESUME=1 elt-llm-consumer-handbook-model\n"
            "Output:  JSON format (not CSV) for multi-line content support"
        ),
    )
    parser.add_argument(
        "--model", default=None,
        help="Override LLM model (default: from rag_config.yaml)",
    )
    parser.add_argument(
        "--topics", nargs="+", default=None,
        help=f"Seed topics to query (default: all {len(_DEFAULT_TOPICS)})",
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_RAG_CONFIG,
        help=f"Path to rag_config.yaml (default: {_DEFAULT_RAG_CONFIG})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    resume = os.environ.get("RESUME", "0") == "1"

    topics = args.topics or _DEFAULT_TOPICS
    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    if args.model:
        rag_config.ollama.llm_model = args.model
        print(f"  Model override: {args.model}")

    rag_config.query.system_prompt = _SYSTEM_PROMPT
    print(f"  LLM:    {rag_config.ollama.llm_model}")
    print(f"  Topics: {len(topics)}")
    if resume:
        print("  Mode:   RESUME")

    collections = ["fa_handbook"]
    print(f"  Collections: {collections}")

    entities = run_pass1(topics, collections, rag_config, output_dir, resume)
    if not entities:
        # If resuming and all Pass 1 done, reload from JSON
        p1_path = output_dir / "fa_handbook_candidate_entities.json"
        if p1_path.exists():
            with open(p1_path, "r", encoding="utf-8") as f:
                entities = json.load(f)
            print(f"\n  Loaded {len(entities)} entities from {p1_path.name} for Pass 2/3")

    if entities:
        run_pass2(entities, collections, rag_config, output_dir)
        run_pass3(entities, collections, rag_config, output_dir, resume)

    print("\n=== Complete ===")
    print(f"  Entities       → {output_dir / 'fa_handbook_candidate_entities.json'}")
    print(f"  Relationships  → {output_dir / 'fa_handbook_candidate_relationships.json'}")
    print(f"  ToR            → {output_dir / 'fa_handbook_terms_of_reference.json'}")
