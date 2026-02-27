#!/usr/bin/env python3
"""Generate the FA Business Glossary / Catalogue CSV.

Joins three sources:
  1. LeanIX Conceptual Model (draw.io XML) — entity names, domains, relationships,
     factSheetIds
  2. LeanIX Inventory CSV — business definitions per entity (where available)
  3. FA Handbook (via RAG) — SME context retrieved per entity

Outputs two CSVs:
  - fa_business_glossary_dataobjects.csv  (229 DataObject entities)
  - fa_business_glossary_interfaces.csv   (271 Interface data flows)

Usage:
    uv run python scripts/generate_business_glossary.py

Progress is printed to stdout. The script checkpoints every 10 rows so it
can be resumed if interrupted (set RESUME=1 to skip already-written rows).

Runtime estimate: ~500 Ollama queries × ~8–15 s each ≈ 60–90 minutes.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
REPO_ROOT = _HERE.parent.parent

RAG_CONFIG_PATH = REPO_ROOT / "elt_llm_ingest" / "config" / "rag_config.yaml"
XML_PATH = Path("~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml").expanduser()
INVENTORY_DATAOBJECTS_CSV = REPO_ROOT / ".tmp" / "leanix_exports" / "20260227_085903_data_objects_glossary.csv"
INVENTORY_INTERFACES_CSV  = REPO_ROOT / ".tmp" / "leanix_exports" / "20260227_085903_interfaces_dataflows.csv"

OUTPUT_DIR = Path("~/Documents/__data/resources/thefa/").expanduser()
OUT_DATAOBJECTS = OUTPUT_DIR / "fa_business_glossary_dataobjects.csv"
OUT_INTERFACES  = OUTPUT_DIR / "fa_business_glossary_interfaces.csv"

# Add repo packages to path so script works without full uv install
for pkg in ("elt_llm_core", "elt_llm_ingest", "elt_llm_query"):
    p = REPO_ROOT / pkg / "src"
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# ---------------------------------------------------------------------------
# Imports (deferred so path manipulation above takes effect)
# ---------------------------------------------------------------------------

from elt_llm_core.config import RagConfig                           # noqa: E402
from elt_llm_ingest.doc_leanix_parser import LeanIXExtractor        # noqa: E402
from elt_llm_query.query import query_collection                     # noqa: E402

# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_conceptual_model(xml_path: Path) -> dict:
    """Parse draw.io XML → asset dict keyed by fact_sheet_id.

    Returns:
        {fact_sheet_id: {"name", "domain", "related_domains"}}
    """
    extractor = LeanIXExtractor(str(xml_path))
    extractor.parse_xml()
    extractor.extract_all()

    # Build domain → related-domain set from relationships
    related: dict[str, set[str]] = defaultdict(set)
    for rel in extractor.relationships:
        if rel.source_label and rel.target_label:
            related[rel.source_label].add(rel.target_label)
            related[rel.target_label].add(rel.source_label)

    result = {}
    for asset in extractor.assets.values():
        fsid = asset.fact_sheet_id
        if not fsid:
            continue
        domain = asset.parent_group or ""
        result[fsid] = {
            "name": asset.label,
            "domain": domain,
            "related_domains": "; ".join(sorted(related.get(domain, set()))),
        }
    return result


def load_inventory_dataobjects(csv_path: Path) -> dict:
    """Read DataObjects inventory CSV → dict keyed by fact_sheet_id."""
    result = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fsid = row.get("fact_sheet_id", "").strip()
            if fsid:
                result[fsid] = {
                    "definition": (row.get("definition") or "").strip(),
                    "hierarchy_level": (row.get("hierarchy_level") or "").strip(),
                    "domain_group": (row.get("domain_group") or "").strip(),
                    "entity_name": (row.get("entity_name") or "").strip(),
                }
    return result


def load_inventory_interfaces(csv_path: Path) -> list[dict]:
    """Read Interfaces inventory CSV → list of interface dicts."""
    with open(csv_path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# RAG query helpers
# ---------------------------------------------------------------------------

_DATAOBJECT_PROMPT = (
    "In the context of The Football Association (The FA), what does the FA Handbook say about "
    "'{name}'? Provide any relevant definitions, governance requirements, regulatory context, "
    "data management obligations, or compliance rules. If the handbook does not mention this "
    "entity directly, describe the closest relevant governance content."
)

_INTERFACE_PROMPT = (
    "In the context of The Football Association (The FA), does the FA Handbook contain any "
    "governance, compliance, or data management rules that apply to the data flow from "
    "'{source}' to '{target}' ({name})? "
    "Describe any relevant regulatory requirements, data sharing obligations, or data "
    "protection considerations."
)


def query_handbook(query: str, rag_config: RagConfig) -> str:
    """Query the fa_handbook collection and return the response text."""
    try:
        result = query_collection("fa_handbook", query, rag_config)
        return result.response.strip()
    except Exception as e:
        return f"[Query failed: {e}]"


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
            fsid = row.get("fact_sheet_id", "").strip()
            if fsid:
                done.add(fsid)
    print(f"  Resuming — {len(done)} rows already written to {out_path.name}")
    return done


# ---------------------------------------------------------------------------
# Main generation routines
# ---------------------------------------------------------------------------

def generate_dataobjects_glossary(rag_config: RagConfig, resume: bool = False) -> None:
    print("\n=== DataObjects Glossary ===")

    print("Loading LeanIX conceptual model (draw.io XML)…")
    model = load_conceptual_model(XML_PATH)
    print(f"  {len(model)} assets with factSheetId")

    print("Loading LeanIX inventory CSV…")
    inventory = load_inventory_dataobjects(INVENTORY_DATAOBJECTS_CSV)
    print(f"  {len(inventory)} inventory rows")

    # Merge: for every inventory row, enrich with domain/relationships from model
    entities = []
    for fsid, inv in inventory.items():
        mdl = model.get(fsid, {})
        entities.append({
            "fact_sheet_id": fsid,
            "entity_name": inv["entity_name"] or mdl.get("name", ""),
            "domain": mdl.get("domain", ""),
            "hierarchy_level": inv["hierarchy_level"],
            "leanix_description": inv["definition"],
            "related_domains": mdl.get("related_domains", ""),
            "description_source": (
                "Both" if (inv["definition"] and mdl.get("name"))
                else "LeanIX only" if inv["definition"]
                else "Model only"
            ),
        })

    # Also add model-only entities (in draw.io but not in inventory CSV)
    inv_fsids = set(inventory.keys())
    for fsid, mdl in model.items():
        if fsid not in inv_fsids:
            entities.append({
                "fact_sheet_id": fsid,
                "entity_name": mdl["name"],
                "domain": mdl["domain"],
                "hierarchy_level": "",
                "leanix_description": "",
                "related_domains": mdl["related_domains"],
                "description_source": "Model only",
            })

    done = load_checkpoint(OUT_DATAOBJECTS) if resume else set()

    fieldnames = [
        "fact_sheet_id", "entity_name", "domain", "hierarchy_level",
        "leanix_description", "handbook_context", "related_domains", "description_source",
    ]

    mode = "a" if resume and OUT_DATAOBJECTS.exists() else "w"
    total = len(entities)
    written = 0

    with open(OUT_DATAOBJECTS, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()

        for i, entity in enumerate(entities, 1):
            fsid = entity["fact_sheet_id"]
            if fsid in done:
                continue

            name = entity["entity_name"]
            leanix_desc = entity["leanix_description"]

            print(f"  [{i}/{total}] Querying FA Handbook for: {name}…", flush=True)
            query = _DATAOBJECT_PROMPT.format(name=name)
            handbook_context = query_handbook(query, rag_config)

            writer.writerow({**entity, "handbook_context": handbook_context})
            f.flush()  # checkpoint after every row
            written += 1

    print(f"\n✅ DataObjects glossary written → {OUT_DATAOBJECTS}  ({written} new rows)")


def generate_interfaces_glossary(rag_config: RagConfig, resume: bool = False) -> None:
    print("\n=== Interfaces Glossary ===")

    print("Loading LeanIX interfaces CSV…")
    interfaces = load_inventory_interfaces(INVENTORY_INTERFACES_CSV)
    print(f"  {len(interfaces)} interface rows")

    done = load_checkpoint(OUT_INTERFACES) if resume else set()

    fieldnames = [
        "fact_sheet_id", "interface_name", "source_system", "target_system",
        "flow_description", "handbook_context",
    ]

    mode = "a" if resume and OUT_INTERFACES.exists() else "w"
    total = len(interfaces)
    written = 0

    with open(OUT_INTERFACES, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()

        for i, row in enumerate(interfaces, 1):
            fsid = row.get("fact_sheet_id", "").strip()
            if fsid in done:
                continue

            name = row.get("interface_name") or row.get("display_name", "Unknown")
            source = row.get("source_system", "Unknown")
            target = row.get("target_system", "Unknown")
            flow_desc = (row.get("flow_description") or "").strip()

            print(f"  [{i}/{total}] Querying FA Handbook for interface: {name}…", flush=True)
            query = _INTERFACE_PROMPT.format(name=name, source=source, target=target)
            handbook_context = query_handbook(query, rag_config)

            writer.writerow({
                "fact_sheet_id": fsid,
                "interface_name": name,
                "source_system": source,
                "target_system": target,
                "flow_description": flow_desc,
                "handbook_context": handbook_context,
            })
            f.flush()
            written += 1

    print(f"\n✅ Interfaces glossary written → {OUT_INTERFACES}  ({written} new rows)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    resume = os.environ.get("RESUME", "0") == "1"

    if not XML_PATH.exists():
        print(f"❌ XML file not found: {XML_PATH}", file=sys.stderr)
        sys.exit(1)
    if not INVENTORY_DATAOBJECTS_CSV.exists():
        print(f"❌ DataObjects CSV not found: {INVENTORY_DATAOBJECTS_CSV}", file=sys.stderr)
        sys.exit(1)
    if not INVENTORY_INTERFACES_CSV.exists():
        print(f"❌ Interfaces CSV not found: {INVENTORY_INTERFACES_CSV}", file=sys.stderr)
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(RAG_CONFIG_PATH)

    if resume:
        print("RESUME mode: skipping already-written rows.")

    generate_dataobjects_glossary(rag_config, resume=resume)
    generate_interfaces_glossary(rag_config, resume=resume)

    print("\n=== Complete ===")
    print(f"  DataObjects → {OUT_DATAOBJECTS}")
    print(f"  Interfaces  → {OUT_INTERFACES}")


if __name__ == "__main__":
    main()
