"""FA LeanIX Model Validator.

Fast, LLM-free diagnostic that checks what the conceptual model docstores actually
contain after ingestion.  Runs in seconds — no embeddings, no Ollama calls.

Validates:
  - Entity counts per domain
  - fact_sheet_id coverage (key signal for bullet vs paragraph extraction format)
  - Subgroup field distribution (populated only after Enhancement 1b)
  - Domain-level relationship counts

Use this BEFORE running the full consolidated catalog consumer to catch ingestion
or parser regressions early.

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-leanix-validate
    uv run --package elt-llm-consumer elt-llm-consumer-leanix-validate --skip-relationships
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_query.query import resolve_collection_prefixes

from elt_llm_consumer.fa_consolidated_catalog import (
    extract_entities_from_conceptual_model,
    extract_relationships_from_conceptual_model,
)

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

# Expected entity counts per domain after each enhancement milestone.
# Used to flag regressions.  Update when re-ingestion changes expected values.
_EXPECTED_COUNTS: dict[str, dict[str, int]] = {
    # After Enhancement 1a (PARTY gets its own collection, bullet format)
    "post_1a": {
        "AGREEMENTS": 42,
        "CAMPAIGN": 9,
        "LOCATION": 5,
        "PARTY": 27,         # was 27 from paragraph, now from bullet — count unchanged
        "PRODUCT": 42,
        "REFERENCE_DATA": 1,
        "STATIC_DATA": 3,
        "TIME_BOUNDED_GROUPINGS": 2,
        "TRANSACTION_AND_EVENTS": 36,
        # CHANNEL / ACCOUNTS / ASSETS / ADDITIONAL remain from additional_entities
        "CHANNEL": 22,
        "ACCOUNTS": 5,
        "ASSETS": 7,
    },
}


def _fmt_row(label: str, total: int, with_id: int, no_id: int, subgroup: int) -> str:
    id_pct = f"{100 * with_id // total:>3}%" if total else "  — "
    sg_pct = f"{100 * subgroup // total:>3}%" if total else "  — "
    return (
        f"  {label:<32} {total:>5}   {with_id:>5} ({id_pct})   "
        f"{no_id:>5}   {subgroup:>5} ({sg_pct})"
    )


def run_validation(
    rag_config: RagConfig,
    model_collections: list[str],
    skip_relationships: bool,
) -> None:
    # ── Entity extraction (docstore scan — no LLM) ────────────────────────────
    print("\n=== Step 1: Extract Conceptual Model Entities (docstore scan) ===")
    entities = extract_entities_from_conceptual_model(rag_config, model_collections)

    # ── Per-domain breakdown ──────────────────────────────────────────────────
    domain_entities: dict[str, list[dict]] = defaultdict(list)
    for e in entities:
        domain_entities[e["domain"]].append(e)

    total_with_id = sum(1 for e in entities if e.get("fact_sheet_id"))
    total_no_id   = sum(1 for e in entities if not e.get("fact_sheet_id"))
    total_subgrp  = sum(1 for e in entities if e.get("subgroup"))

    header = (
        f"\n  {'Domain':<32} {'Total':>5}   {'With ID':>5} (  %)   "
        f"{'No ID':>5}   {'Subgrp':>5} (  %)"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for domain in sorted(domain_entities):
        grp = domain_entities[domain]
        with_id = sum(1 for e in grp if e.get("fact_sheet_id"))
        no_id   = sum(1 for e in grp if not e.get("fact_sheet_id"))
        subgrp  = sum(1 for e in grp if e.get("subgroup"))
        print(_fmt_row(domain, len(grp), with_id, no_id, subgrp))

    print("  " + "-" * (len(header) - 2))
    print(
        _fmt_row("TOTAL", len(entities), total_with_id, total_no_id, total_subgrp)
    )

    # ── Acceptance checks ─────────────────────────────────────────────────────
    print("\n=== Acceptance Checks ===")
    issues: list[str] = []

    party = domain_entities.get("PARTY", [])
    party_with_id = sum(1 for e in party if e.get("fact_sheet_id"))

    if party:
        if party_with_id == len(party):
            print(f"  ✓ PARTY: all {len(party)} entities have fact_sheet_id (Enhancement 1a complete)")
        elif party_with_id == 0:
            issues.append(
                f"  ✗ PARTY: {len(party)} entities but NONE have fact_sheet_id — "
                "Enhancement 1a not applied or re-ingestion not run"
            )
        else:
            issues.append(
                f"  ⚠ PARTY: {party_with_id}/{len(party)} entities have fact_sheet_id — partial"
            )
    else:
        issues.append("  ✗ PARTY domain missing — Enhancement 1a not applied or re-ingestion not run")

    total_leanix = sum(
        len(v) for k, v in domain_entities.items()
        if k not in ("HANDBOOK_DISCOVERED",)
    )
    # After Enhancement 1b, subgroup container labels are excluded from entity lists
    # (~22 structural labels removed), so expected count drops from 208 to ~186.
    if total_leanix >= 150:
        print(f"  ✓ LeanIX entity count: {total_leanix} (≥ 150 expected)")
    else:
        issues.append(f"  ✗ LeanIX entity count: {total_leanix} (expected ≥ 150)")

    subgrp_count = sum(1 for e in entities if e.get("subgroup"))
    if subgrp_count == 0:
        print(
            "  — Subgroup field: empty on all entities "
            "(Enhancement 1b not yet applied — expected for post-1a state)"
        )
    elif subgrp_count >= 100:
        print(f"  ✓ Subgroup field: {subgrp_count} entities have subgroup (Enhancement 1b complete)")
    else:
        issues.append(f"  ⚠ Subgroup field: only {subgrp_count} entities have subgroup — check Enhancement 1b")

    if issues:
        print("\n  Issues found:")
        for iss in issues:
            print(iss)
    else:
        print("\n  All checks passed.")

    # ── Relationship extraction (docstore scan — no LLM) ─────────────────────
    if not skip_relationships:
        print("\n=== Step 2: Extract Relationships (docstore scan) ===")
        relationships = extract_relationships_from_conceptual_model(rag_config, model_collections)
        total_rels = sum(len(v) for v in relationships.values())
        print(f"  {total_rels} domain-level relationships across {len(relationships)} source domains")
        if total_rels > 0:
            print("  Sample relationships:")
            for src, rels in list(relationships.items())[:3]:
                for rel in rels[:2]:
                    print(f"    {src} → {rel['target_entity']}  [{rel.get('cardinality', '')}]")
    else:
        print("\n  Skipping relationship extraction (--skip-relationships)")

    print(f"\n  Collections scanned: {len(model_collections)}")
    for c in sorted(model_collections):
        print(f"    {c}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fast LeanIX conceptual model validation — "
            "docstore scan only, no LLM calls, runs in seconds"
        )
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_RAG_CONFIG,
        help=f"Path to rag_config.yaml (default: {_DEFAULT_RAG_CONFIG})",
    )
    parser.add_argument(
        "--skip-relationships", action="store_true",
        help="Skip relationship extraction step",
    )
    args = parser.parse_args()

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    print("Resolving collections…")
    model_collections = resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    if not model_collections:
        print(
            "\nERROR: No conceptual model collections found.\n"
            "Run ingestion first: uv run python -m elt_llm_ingest.runner ingest "
            "ingest_fa_leanix_dat_enterprise_conceptual_model",
            file=sys.stderr,
        )
        sys.exit(1)

    run_validation(rag_config, model_collections, args.skip_relationships)
