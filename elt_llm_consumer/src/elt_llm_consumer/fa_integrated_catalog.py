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
  fa_terms_of_reference.json  ← structured ToR: definition + domain + governance
  fa_integrated_catalog.json  ← combined catalog_entry column for bulk use

Output format: JSON (not CSV) to properly support multi-line content,
hierarchical structures, and nested fields from combined data sources.

Usage:
    uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog

    uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog \\
        --model qwen2.5:14b

    RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog

    # Targeted re-run for specific entities (merges with existing output):
    uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog \\
        --entities 'Club,Player,Referee,Competition,Match'

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled

Runtime: ~217 conceptual model entities × 10–20 s ≈ 35–70 min (varies by model)
"""
from __future__ import annotations

import argparse
import json
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

_DEFAULT_OUTPUT_DIR = Path("~/.tmp/elt_llm_consumer").expanduser()

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

Structure your response using exactly these three headings on their own lines, each followed by one or more paragraphs:

FORMAL_DEFINITION:
[What is this entity? Combine the LeanIX description with any FA Handbook definition. Quote the exact FA Handbook definition if one exists, including the defined term (e.g. 'Club means any club which plays the game of football in England and is recognised as such by The Association').]

DOMAIN_CONTEXT:
[What role does it play within the {domain} domain? How does it relate to {related_entities}?]

GOVERNANCE:
[What specific FA Handbook rules, obligations, or regulatory requirements apply to this entity? Cite the section and rule number where possible (e.g. Rule A3.1, Section C Player Status Rules, Section 23 Referees). If the FA Handbook contains a formal definition or regulation for this entity, quote it directly. If no handbook rules apply to this entity, state 'Not documented in FA Handbook — outside governance scope'.]"""

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
                "lx_state": str(row.get("lxState") or "").strip(),
            }
    print(f"  {len(inventory)} inventory entries loaded")
    return inventory


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


def load_checkpoint(out_path: Path) -> set[str]:
    """Return set of fact_sheet_ids already written to the output JSON."""
    if not out_path.exists():
        return set()
    done: set[str] = set()
    with open(out_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        for row in data:
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
    """Extract FORMAL_DEFINITION, DOMAIN_CONTEXT, GOVERNANCE from response.

    Captures full multi-paragraph content for each section, not just the first line.
    The GOVERNANCE section maps to the 'governance_rules' key used by the ToR writer.
    """
    import re

    keys = ("FORMAL_DEFINITION", "DOMAIN_CONTEXT", "GOVERNANCE")
    # Map each raw key to the output dict key expected by the CSV writer
    key_map = {
        "FORMAL_DEFINITION": "formal_definition",
        "DOMAIN_CONTEXT": "domain_context",
        "GOVERNANCE": "governance_rules",
    }

    positions: dict[str, tuple[int, int]] = {}
    for key in keys:
        m = re.search(rf"^{key}:\s*", response, re.MULTILINE)
        if m:
            positions[key] = (m.start(), m.end())

    parsed: dict[str, str] = {}
    sorted_keys = sorted(positions.items(), key=lambda x: x[1][0])
    for idx, (key, (kstart, content_start)) in enumerate(sorted_keys):
        end = sorted_keys[idx + 1][1][0] if idx + 1 < len(sorted_keys) else len(response)
        text = response[content_start:end].strip()
        parsed[key_map[key]] = text

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
    only_entities: set[str] | None = None,
) -> None:
    """Generate (or partially update) the integrated catalog JSON files.

    Args:
        only_entities: When provided, only regenerate rows for these entity
            names (case-insensitive). Existing rows for other entities are
            preserved. The output JSON files are rewritten atomically so that
            in-place updates don't corrupt the checkpoint state.
    """
    tor_path = output_dir / "fa_terms_of_reference.json"
    catalog_path = output_dir / "fa_integrated_catalog.json"

    # When targeting specific entities, load existing rows first so we can
    # merge new results in-place rather than appending.
    if only_entities:
        only_lower = {n.lower() for n in only_entities}
        existing_tor: dict[str, dict] = {}
        existing_cat: dict[str, dict] = {}
        if tor_path.exists():
            with open(tor_path, "r", encoding="utf-8") as f:
                tor_data = json.load(f)
                existing_tor = {row["fact_sheet_id"]: row for row in tor_data}
        if catalog_path.exists():
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat_data = json.load(f)
                existing_cat = {row["fact_sheet_id"]: row for row in cat_data}
        resume = False  # force full rewrite of both files after merging

    done = load_checkpoint(tor_path) if resume else set()

    total = len(entities)
    written = 0
    model = rag_config.ollama.llm_model

    mode_label = "TARGETED" if only_entities else ("RESUME" if resume else "FULL")
    print(f"\n=== Integrated Catalog ({total} entities, mode={mode_label}) ===")
    if only_entities:
        print(f"  Targeting {len(only_entities)} entities: {', '.join(sorted(only_entities))}")

    # --- First pass: process (or skip) each entity ---
    new_tor_rows: dict[str, dict] = {}
    new_cat_rows: dict[str, dict] = {}

    for i, entity in enumerate(entities, 1):
        fsid = entity["fact_sheet_id"]
        name = entity["entity_name"]

        # Skip if not in the targeted set
        if only_entities and name.lower() not in only_lower:
            continue
        if fsid in done:
            continue

        domain = entity["domain"]
        related = entity["related_entities"]

        # Direct join from inventory (no RAG for inventory descriptions)
        inv = inventory.get(fsid, {})
        leanix_description = inv.get("description") or "Not documented"
        hierarchy_level = inv.get("level") or ""
        lx_state = inv.get("lx_state") or ""

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

        new_tor_rows[fsid] = {
            "fact_sheet_id": fsid,
            "entity_name": name,
            "domain": domain,
            "hierarchy_level": hierarchy_level,
            "lx_state": lx_state,
            "related_entities": related,
            "leanix_description": leanix_description,
            "formal_definition": parsed.get("formal_definition", ""),
            "domain_context": parsed.get("domain_context", ""),
            "governance_rules": parsed.get("governance_rules", ""),
            "model_used": model,
        }
        new_cat_rows[fsid] = {
            "fact_sheet_id": fsid,
            "entity_name": name,
            "domain": domain,
            "hierarchy_level": hierarchy_level,
            "lx_state": lx_state,
            "leanix_description": leanix_description,
            "catalog_entry": response,
            "model_used": model,
        }
        written += 1

    # --- Second pass: write output (merge for targeted mode, append for resume/full) ---
    if only_entities:
        # Merge: existing rows + new rows (new rows take precedence)
        merged_tor = {**existing_tor, **new_tor_rows}
        merged_cat = {**existing_cat, **new_cat_rows}
        # Preserve original entity order from the entity list
        ordered_fsids = [e["fact_sheet_id"] for e in entities]

        tor_list = [merged_tor[fsid] for fsid in ordered_fsids if fsid in merged_tor]
        cat_list = [merged_cat[fsid] for fsid in ordered_fsids if fsid in merged_cat]

        with open(tor_path, "w", encoding="utf-8") as tor_f:
            json.dump(tor_list, tor_f, indent=2, ensure_ascii=False)

        with open(catalog_path, "w", encoding="utf-8") as cat_f:
            json.dump(cat_list, cat_f, indent=2, ensure_ascii=False)
    else:
        # Load existing data for resume mode
        tor_list: list[dict] = []
        cat_list: list[dict] = []
        if resume and tor_path.exists():
            with open(tor_path, "r", encoding="utf-8") as f:
                tor_list = json.load(f)
        if resume and catalog_path.exists():
            with open(catalog_path, "r", encoding="utf-8") as f:
                cat_list = json.load(f)

        # Append new rows
        tor_list.extend(new_tor_rows.values())
        cat_list.extend(new_cat_rows.values())

        with open(tor_path, "w", encoding="utf-8") as tor_f:
            json.dump(tor_list, tor_f, indent=2, ensure_ascii=False)

        with open(catalog_path, "w", encoding="utf-8") as cat_f:
            json.dump(cat_list, cat_f, indent=2, ensure_ascii=False)

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
            "Resume:  RESUME=1 elt-llm-consumer-integrated-catalog\n"
            "Targeted re-run: --entities 'Club,Player,Referee'\n"
            "Output:  JSON format (not CSV) for multi-line content support"
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
    parser.add_argument(
        "--entities", default=None,
        help=(
            "Comma-separated list of entity names to re-process (case-insensitive). "
            "Other entities are preserved unchanged. Useful for targeted re-runs "
            "after prompt improvements. Example: --entities 'Club,Player,Referee'"
        ),
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

    only_entities: set[str] | None = None
    if args.entities:
        only_entities = {e.strip() for e in args.entities.split(",") if e.strip()}
        print(f"  Targeting {len(only_entities)} entities: {', '.join(sorted(only_entities))}")

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

    generate_integrated_catalog(
        entities, inventory, collections, rag_config, output_dir, resume,
        only_entities=only_entities,
    )

    print("\n=== Complete ===")
    print(f"  Terms of Reference → {output_dir / 'fa_terms_of_reference.json'}")
    print(f"  Integrated Catalog → {output_dir / 'fa_integrated_catalog.json'}")
