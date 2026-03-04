"""FA LeanIX Model Validator.

Fast, LLM-free diagnostic that validates the pre-parsed conceptual model JSON
produced by LeanIXPreprocessor (output_format='csv').  Runs in milliseconds.

Validates:
  - Entity counts per domain
  - fact_sheet_id coverage
  - Subgroup (subtype) field distribution
  - Domain-level relationship counts

Use this BEFORE running the full consolidated catalog consumer to catch
preprocessing or ingestion regressions early.

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-leanix-validate
    uv run --package elt-llm-consumer elt-llm-consumer-leanix-validate --skip-relationships
    uv run --package elt-llm-consumer elt-llm-consumer-leanix-validate \\
        --model-json ~/path/to/model.json
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from elt_llm_consumer.fa_consolidated_catalog import (
    load_entities_from_json,
    load_relationships_from_json,
)

_DEFAULT_MODEL_JSON = Path(
    "~/Documents/__data/resources/thefa/"
    "DAT_V00.01_FA Enterprise Conceptual Data Model_model.json"
).expanduser()


def _fmt_row(label: str, total: int, with_id: int, no_id: int, subgroup: int) -> str:
    id_pct = f"{100 * with_id // total:>3}%" if total else "  — "
    sg_pct = f"{100 * subgroup // total:>3}%" if total else "  — "
    return (
        f"  {label:<32} {total:>5}   {with_id:>5} ({id_pct})   "
        f"{no_id:>5}   {subgroup:>5} ({sg_pct})"
    )


def run_validation(
    model_json: Path,
    skip_relationships: bool,
) -> None:
    # ── Entity loading from JSON ──────────────────────────────────────────────
    print("\n=== Step 1: Load Conceptual Model Entities ===")
    entities = load_entities_from_json(model_json)

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

    if total_with_id == len(entities):
        print(f"  ✓ All {len(entities)} entities have fact_sheet_id")
    elif total_with_id == 0:
        issues.append(f"  ✗ No entities have fact_sheet_id — check JSON generation")
    else:
        issues.append(
            f"  ⚠ {total_with_id}/{len(entities)} entities have fact_sheet_id — partial"
        )

    if len(entities) >= 150:
        print(f"  ✓ Entity count: {len(entities)} (≥ 150 expected)")
    else:
        issues.append(f"  ✗ Entity count: {len(entities)} (expected ≥ 150)")

    if total_subgrp == 0:
        print("  — Subgroup field: empty on all entities (no subtypes defined)")
    elif total_subgrp >= 100:
        print(f"  ✓ Subgroup field: {total_subgrp} entities have subtype")
    else:
        issues.append(f"  ⚠ Subgroup field: only {total_subgrp} entities have subtype")

    if issues:
        print("\n  Issues found:")
        for iss in issues:
            print(iss)
    else:
        print("\n  All checks passed.")

    # ── Relationship loading ──────────────────────────────────────────────────
    if not skip_relationships:
        print("\n=== Step 2: Load Relationships ===")
        relationships = load_relationships_from_json(model_json)
        total_rels = sum(len(v) for v in relationships.values())
        print(f"  {total_rels} relationships across {len(relationships)} source domains")
        if total_rels > 0:
            print("  Sample relationships:")
            for src, rels in list(relationships.items())[:3]:
                for rel in rels[:2]:
                    print(f"    {src} → {rel['target_entity']}  [{rel.get('cardinality', '')}]")
    else:
        print("\n  Skipping relationship loading (--skip-relationships)")

    print(f"\n  Source: {model_json}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fast LeanIX conceptual model validation — "
            "reads pre-parsed model JSON, no ChromaDB or LLM calls, runs in milliseconds"
        )
    )
    parser.add_argument(
        "--model-json", type=Path, default=_DEFAULT_MODEL_JSON,
        help=f"Path to LeanIX model JSON (default: {_DEFAULT_MODEL_JSON})",
    )
    parser.add_argument(
        "--skip-relationships", action="store_true",
        help="Skip relationship loading step",
    )
    args = parser.parse_args()

    run_validation(
        model_json=args.model_json.expanduser(),
        skip_relationships=args.skip_relationships,
    )
