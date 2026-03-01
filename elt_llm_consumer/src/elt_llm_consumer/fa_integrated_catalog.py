"""FA Integrated Catalog generator.

The direct implementation of: "the conceptual model is the frame, the handbook
providing the SME content."

Three-source join:
  1. LeanIX Conceptual Model (draw.io XML) — canonical entity frame: domain,
     hierarchy, relationships between entities.
  2. LeanIX Global Inventory (Excel) — direct description lookup by fact_sheet_id.
     Joined in-memory, NOT queried via RAG, for precision.
  3. FA Handbook (RAG) — governance rules, obligations, regulatory context per entity.

The conceptual model XML drives the entity list. Every entity in the model gets a
catalog entry regardless of whether it appears in the inventory.

Outputs (~/Documents/__data/resources/thefa/):
  fa_terms_of_reference.csv  ← structured ToR: definition + domain + governance
  fa_integrated_catalog.csv  ← combined catalog_entry column for bulk use

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog

    uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog \\
        --model qwen2.5:14b

    RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled

Runtime: ~217 conceptual model entities × 10–20 s ≈ 35–70 min (varies by model)
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_query.query import query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_EXCEL = Path(
    "~/Documents/__data/resources/thefa/20260227_085233_UtvKD_inventory.xlsx"
).expanduser()

_DEFAULT_XML = Path(
    "~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path("~/Documents/__data/resources/thefa/").expanduser()

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert FA Enterprise Architect and Data Management consultant.
You have access to two FA-specific knowledge sources:

1. FA Handbook - governance rules, committees, competition structures, club regulations,
   player eligibility, disciplinary procedures, and all FA regulatory obligations.
2. FA Enterprise Conceptual Data Model (LeanIX) - entity types across domains including
   Party, Channel, Account, Asset, Agreement, Campaign, and Product entities,
   with domain-level relationships and LeanIX fact sheet IDs.

When answering:
- Ground every answer in the retrieved content. Do not invent facts.
- Cite which source you are drawing from where relevant.
- If information is not available in any source, state 'Not documented'."""

# ---------------------------------------------------------------------------
# Per-entity query template
# ---------------------------------------------------------------------------

_INTEGRATED_QUERY = """\
Provide a terms of reference entry for the FA data entity '{name}' in the {domain} domain.

Context from LeanIX:
- LeanIX inventory description: {leanix_description}
- Related entities (from conceptual model): {related_entities}
- Hierarchy level: {hierarchy}

Structure your response as:

FORMAL_DEFINITION: [What is this entity? Combine the LeanIX description with any Handbook definition.]
DOMAIN_CONTEXT: [What role does it play within the {domain} domain? How does it relate to {related_entities}?]
GOVERNANCE: [What FA Handbook rules, obligations, or regulatory requirements apply to this entity?]"""

# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------


def load_conceptual_model(xml_path: Path) -> list[dict]:
    """Parse draw.io XML → list of entity dicts with domain + relationships."""
    # Import here so the module is only required at runtime (elt_llm_ingest dependency)
    try:
        import sys as _sys
        # elt_llm_ingest is a workspace package; it is always available in uv workspace
        from elt_llm_ingest.doc_leanix_parser import LeanIXExtractor
    except ImportError:
        print(
            "ERROR: elt_llm_ingest is not available. "
            "Run: uv sync --all-packages",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Parsing conceptual model XML: {xml_path}")
    extractor = LeanIXExtractor(str(xml_path))
    extractor.parse_xml()
    extractor.extract_all()

    # Build relationship index: asset_id → list of related entity labels
    rel_index: dict[str, list[str]] = {}
    for rel in extractor.relationships:
        if rel.source_label and rel.target_label:
            rel_index.setdefault(rel.source_id, []).append(rel.target_label)
            rel_index.setdefault(rel.target_id, []).append(rel.source_label)

    entities: list[dict] = []
    for asset_id, asset in extractor.assets.items():
        if not asset.label or not asset.fact_sheet_id:
            continue
        related = rel_index.get(asset_id, [])
        entities.append({
            "fact_sheet_id": asset.fact_sheet_id,
            "entity_name": asset.label,
            "domain": asset.parent_group or "UNKNOWN",
            "xml_id": asset_id,
            "related_entities": ", ".join(sorted(set(related))) if related else "None documented",
        })

    print(f"  {len(entities)} entities loaded from conceptual model")
    return entities


def load_inventory_descriptions(excel_path: Path) -> dict[str, dict]:
    """Read LeanIX inventory Excel → dict keyed by fact_sheet_id."""
    import pandas as pd

    print(f"  Loading inventory descriptions: {excel_path}")
    df = pd.read_excel(excel_path)
    inventory: dict[str, dict] = {}
    for _, row in df.iterrows():
        fsid = str(row.get("id") or "").strip()
        if fsid:
            inventory[fsid] = {
                "description": str(row.get("description") or "").strip(),
                "level": row.get("level"),
                "status": str(row.get("status") or "").strip(),
            }
    print(f"  {len(inventory)} inventory entries loaded")
    return inventory


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def load_checkpoint(out_path: Path) -> set[str]:
    """Return set of fact_sheet_ids already written to the output CSV."""
    if not out_path.exists():
        return set()
    done: set[str] = set()
    with open(out_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fsid = (row.get("fact_sheet_id") or "").strip()
            if fsid:
                done.add(fsid)
    print(f"  Resuming — {len(done)} rows already written to {out_path.name}")
    return done


def run_query(query: str, collections: list[str], rag_config: RagConfig) -> str:
    """Query collections and return synthesised response."""
    try:
        result = query_collections(collections, query, rag_config)
        return result.response.strip()
    except Exception as e:
        return f"[Query failed: {e}]"


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_integrated_response(response: str) -> dict[str, str]:
    """Extract FORMAL_DEFINITION, DOMAIN_CONTEXT, GOVERNANCE from response."""
    parsed: dict[str, str] = {}
    for line in response.splitlines():
        line = line.strip()
        for key in ("FORMAL_DEFINITION", "DOMAIN_CONTEXT", "GOVERNANCE"):
            if line.startswith(f"{key}:"):
                parsed[key.lower()] = line[len(key) + 1:].strip()
                break
    return parsed


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


def generate_integrated_catalog(
    entities: list[dict],
    inventory: dict[str, dict],
    collections: list[str],
    rag_config: RagConfig,
    output_dir: Path,
    resume: bool,
) -> None:
    tor_path = output_dir / "fa_terms_of_reference.csv"
    catalog_path = output_dir / "fa_integrated_catalog.csv"

    done = load_checkpoint(tor_path) if resume else set()

    tor_fields = [
        "fact_sheet_id", "entity_name", "domain", "hierarchy_level",
        "related_entities", "leanix_description",
        "formal_definition", "domain_context", "governance_rules",
        "model_used",
    ]
    catalog_fields = [
        "fact_sheet_id", "entity_name", "domain", "hierarchy_level",
        "leanix_description", "catalog_entry", "model_used",
    ]

    tor_mode = "a" if resume and tor_path.exists() else "w"
    cat_mode = "a" if resume and catalog_path.exists() else "w"
    total = len(entities)
    written = 0
    model = rag_config.ollama.llm_model

    print(f"\n=== Integrated Catalog ({total} entities) ===")
    with (
        open(tor_path, tor_mode, newline="", encoding="utf-8") as tor_f,
        open(catalog_path, cat_mode, newline="", encoding="utf-8") as cat_f,
    ):
        tor_writer = csv.DictWriter(tor_f, fieldnames=tor_fields)
        cat_writer = csv.DictWriter(cat_f, fieldnames=catalog_fields)
        if tor_mode == "w":
            tor_writer.writeheader()
        if cat_mode == "w":
            cat_writer.writeheader()

        for i, entity in enumerate(entities, 1):
            fsid = entity["fact_sheet_id"]
            if fsid in done:
                continue

            name = entity["entity_name"]
            domain = entity["domain"]
            related = entity["related_entities"]

            # Direct join from inventory (no RAG for inventory descriptions)
            inv = inventory.get(fsid, {})
            leanix_description = inv.get("description") or "Not documented"
            hierarchy_level = inv.get("level") or ""

            print(f"  [{i}/{total}] {name} ({domain})…", end=" ", flush=True)

            response = run_query(
                _INTEGRATED_QUERY.format(
                    name=name,
                    domain=domain,
                    leanix_description=leanix_description,
                    related_entities=related,
                    hierarchy=hierarchy_level or "Not specified",
                ),
                collections,
                rag_config,
            )
            parsed = parse_integrated_response(response)
            print("done")

            tor_writer.writerow({
                "fact_sheet_id": fsid,
                "entity_name": name,
                "domain": domain,
                "hierarchy_level": hierarchy_level,
                "related_entities": related,
                "leanix_description": leanix_description,
                "formal_definition": parsed.get("formal_definition", ""),
                "domain_context": parsed.get("domain_context", ""),
                "governance_rules": parsed.get("governance_rules", ""),
                "model_used": model,
            })
            cat_writer.writerow({
                "fact_sheet_id": fsid,
                "entity_name": name,
                "domain": domain,
                "hierarchy_level": hierarchy_level,
                "leanix_description": leanix_description,
                "catalog_entry": response,
                "model_used": model,
            })
            tor_f.flush()
            cat_f.flush()
            written += 1

    print(f"\n  Written: {written} new rows")
    print(f"  Terms of Reference → {tor_path}")
    print(f"  Integrated Catalog → {catalog_path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate FA Integrated Catalog: conceptual model as frame, "
            "joined with inventory descriptions and FA Handbook governance content"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, "
            "llama3.1:8b, granite3.1-dense:8b, michaelborck/refuled\n"
            "Resume:  RESUME=1 elt-llm-consumer-integrated-catalog"
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
        "--xml", type=Path, default=_DEFAULT_XML,
        help=f"Path to LeanIX draw.io XML (default: {_DEFAULT_XML})",
    )
    parser.add_argument(
        "--excel", type=Path, default=_DEFAULT_EXCEL,
        help=f"Path to LeanIX inventory Excel (default: {_DEFAULT_EXCEL})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {_DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    resume = os.environ.get("RESUME", "0") == "1"

    xml_path = args.xml.expanduser()
    excel_path = args.excel.expanduser()
    output_dir = args.output_dir.expanduser()

    if not xml_path.exists():
        print(f"ERROR: XML file not found: {xml_path}", file=sys.stderr)
        sys.exit(1)
    if not excel_path.exists():
        print(f"ERROR: Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    if args.model:
        rag_config.ollama.llm_model = args.model
        print(f"  Model override: {args.model}")

    rag_config.query.system_prompt = _SYSTEM_PROMPT
    print(f"  LLM:    {rag_config.ollama.llm_model}")
    if resume:
        print("  Mode:   RESUME (skipping already-written rows)")

    # Resolve collections: FA Handbook + conceptual model only
    # (inventory descriptions joined directly from Excel, not via RAG)
    from elt_llm_query.query import resolve_collection_prefixes
    cm_collections = resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    collections = ["fa_handbook"] + cm_collections
    print(f"\nCollections ({len(collections)}): {', '.join(collections)}")

    if not collections:
        print("ERROR: No collections found. Run ingestion first.", file=sys.stderr)
        sys.exit(1)

    print("\nLoading sources…")
    entities = load_conceptual_model(xml_path)
    inventory = load_inventory_descriptions(excel_path)

    inventory_matched = sum(1 for e in entities if e["fact_sheet_id"] in inventory)
    print(f"  Inventory match: {inventory_matched}/{len(entities)} entities have descriptions")

    generate_integrated_catalog(entities, inventory, collections, rag_config, output_dir, resume)

    print("\n=== Complete ===")
    print(f"  Terms of Reference → {output_dir / 'fa_terms_of_reference.csv'}")
    print(f"  Integrated Catalog → {output_dir / 'fa_integrated_catalog.csv'}")
