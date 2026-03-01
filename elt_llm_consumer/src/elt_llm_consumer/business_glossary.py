"""FA Business Catalog generator.

Batch-drives the LLM+RAG infrastructure to produce a structured business
catalog CSV for every LeanIX entity (DataObjects and Interfaces).

Sources queried per entity (fa_enterprise_architecture scope):
  - fa_handbook              — governance, regulations, compliance rules
  - fa_data_architecture     — FA reference data architecture
  - fa_leanix_*              — LeanIX conceptual model + global inventory

Usage:
    # Via uv workspace entry point
    uv run --package elt-llm-consumer elt-llm-consumer-glossary

    # With options
    uv run --package elt-llm-consumer elt-llm-consumer-glossary \\
        --model mistral-nemo:12b --type dataobjects

    # Resume after interruption
    RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-glossary

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled

Runtime: ~500 entities × 10–20 s each ≈ 90–180 min (varies by model and hardware)
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

_DEFAULT_OUTPUT_DIR = Path("~/Documents/__data/resources/thefa/").expanduser()

# ---------------------------------------------------------------------------
# System prompt — mirrors fa_enterprise_architecture.yaml
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are an expert FA Enterprise Architect and Data Management consultant.
You have access to four FA-specific knowledge sources:

1. FA Handbook - governance rules, committees, competition structures, club regulations.
2. FA Reference Data Architecture - target data architecture for The Football Association.
3. FA Enterprise Conceptual Data Model (LeanIX) - entity types across domains including
   Party, Channel, Account, Asset, Agreement, Campaign, and Product entities,
   with domain-level relationships and LeanIX fact sheet IDs.
4. LeanIX Global Inventory - fact sheets for DataObjects, Interfaces, Applications,
   Business Capabilities, Organizations, and more, including descriptions and LeanIX IDs.

When answering:
- Ground every answer in the retrieved content. Do not invent facts.
- Cite which source you are drawing from where relevant.
- Combine model context (domain/relationships) with inventory context (descriptions) where both exist.
- If information is not available in any source, state 'Not documented'."""

# ---------------------------------------------------------------------------
# Per-entity query templates
# ---------------------------------------------------------------------------

_DATAOBJECT_QUERY = """\
Provide a business catalog entry for the FA data entity '{name}' (LeanIX ID: {fsid}).

Structure your response as:

DEFINITION: [What is this entity? Use the LeanIX inventory description if available.]
DOMAIN: [What domain or subdomain does it belong to, and how does it relate to other entities?]
GOVERNANCE: [What FA Handbook rules, obligations, or regulatory requirements apply?]"""

_INTERFACE_QUERY = """\
Provide a business catalog entry for the FA data interface '{name}'.
Source system: {source}. Target system: {target}.

Structure your response as:

DESCRIPTION: [What data does this interface transmit? Use the LeanIX description if available.]
GOVERNANCE: [What FA Handbook rules or data sharing obligations apply to this flow?]"""

_LEVEL_MAP = {1: "ENTERPRISE_DOMAIN", 2: "SUB_DOMAIN", 3: "ENTITY_GROUP", 4: "ENTITY_TYPE"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_collections(rag_config: RagConfig) -> list[str]:
    """Resolve all FA collections: handbook + data architecture + all fa_leanix_* prefixed."""
    fixed = ["fa_handbook", "fa_data_architecture"]
    prefixed = resolve_collection_prefixes(["fa_leanix"], rag_config)
    all_cols = fixed + prefixed
    print(f"  Collections ({len(all_cols)}): {', '.join(all_cols)}")
    return all_cols


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
    """Query across all FA collections and return the synthesised response."""
    try:
        result = query_collections(collections, query, rag_config)
        return result.response.strip()
    except Exception as e:
        return f"[Query failed: {e}]"


# ---------------------------------------------------------------------------
# DataObjects
# ---------------------------------------------------------------------------


def generate_dataobjects(
    rag_config: RagConfig,
    collections: list[str],
    excel_path: Path,
    output_dir: Path,
    resume: bool,
) -> None:
    import pandas as pd

    out_path = output_dir / "fa_business_catalog_dataobjects.csv"

    print("\n=== DataObjects Catalog ===")
    print(f"  Reading from: {excel_path}")

    df = pd.read_excel(excel_path)
    objs = df[df["type"] == "DataObject"][["id", "name", "description", "level", "lxState"]].copy()
    objs.columns = ["fact_sheet_id", "entity_name", "leanix_description", "hierarchy_level", "lx_state"]
    objs["domain_group"] = objs["hierarchy_level"].map(_LEVEL_MAP)
    entities = objs.to_dict("records")
    print(f"  {len(entities)} DataObjects loaded")

    done = load_checkpoint(out_path) if resume else set()

    fieldnames = [
        "fact_sheet_id", "entity_name", "domain_group", "hierarchy_level",
        "lx_state", "leanix_description", "catalog_entry", "model_used",
    ]
    mode = "a" if resume and out_path.exists() else "w"
    total = len(entities)
    written = 0

    with open(out_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()

        for i, entity in enumerate(entities, 1):
            fsid = str(entity["fact_sheet_id"]).strip()
            if fsid in done:
                continue

            name = entity["entity_name"]
            print(f"  [{i}/{total}] {name}…", end=" ", flush=True)

            catalog_entry = run_query(
                _DATAOBJECT_QUERY.format(name=name, fsid=fsid),
                collections,
                rag_config,
            )
            print("done")

            writer.writerow({
                "fact_sheet_id": fsid,
                "entity_name": name,
                "domain_group": entity.get("domain_group", ""),
                "hierarchy_level": entity.get("hierarchy_level", ""),
                "lx_state": entity.get("lx_state", ""),
                "leanix_description": (entity.get("leanix_description") or "").strip(),
                "catalog_entry": catalog_entry,
                "model_used": rag_config.ollama.llm_model,
            })
            f.flush()
            written += 1

    print(f"\n  DataObjects catalog → {out_path}  ({written} new rows)")


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


def _split_source_target(name: str) -> tuple[str, str]:
    """Infer source and target from 'X to Y' interface naming convention."""
    if " to " in name:
        parts = name.split(" to ", 1)
        return parts[0].strip(), parts[1].strip()
    return "", ""


def generate_interfaces(
    rag_config: RagConfig,
    collections: list[str],
    excel_path: Path,
    output_dir: Path,
    resume: bool,
) -> None:
    import pandas as pd

    out_path = output_dir / "fa_business_catalog_interfaces.csv"

    print("\n=== Interfaces Catalog ===")
    print(f"  Reading from: {excel_path}")

    df = pd.read_excel(excel_path)
    ifaces = df[df["type"] == "Interface"][["id", "name", "description"]].copy()
    ifaces.columns = ["fact_sheet_id", "interface_name", "flow_description"]
    ifaces[["source_system", "target_system"]] = ifaces["interface_name"].apply(
        lambda n: pd.Series(_split_source_target(str(n)))
    )
    interfaces = ifaces.to_dict("records")
    print(f"  {len(interfaces)} Interfaces loaded")

    done = load_checkpoint(out_path) if resume else set()

    fieldnames = [
        "fact_sheet_id", "interface_name", "source_system", "target_system",
        "flow_description", "catalog_entry", "model_used",
    ]
    mode = "a" if resume and out_path.exists() else "w"
    total = len(interfaces)
    written = 0

    with open(out_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if mode == "w":
            writer.writeheader()

        for i, row in enumerate(interfaces, 1):
            fsid = str(row["fact_sheet_id"]).strip()
            if fsid in done:
                continue

            name = row["interface_name"]
            source = row["source_system"] or "Unknown"
            target = row["target_system"] or "Unknown"
            print(f"  [{i}/{total}] {name}…", end=" ", flush=True)

            catalog_entry = run_query(
                _INTERFACE_QUERY.format(name=name, source=source, target=target),
                collections,
                rag_config,
            )
            print("done")

            writer.writerow({
                "fact_sheet_id": fsid,
                "interface_name": name,
                "source_system": source,
                "target_system": target,
                "flow_description": (row.get("flow_description") or "").strip(),
                "catalog_entry": catalog_entry,
                "model_used": rag_config.ollama.llm_model,
            })
            f.flush()
            written += 1

    print(f"\n  Interfaces catalog → {out_path}  ({written} new rows)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate FA Business Catalog from RAG collections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, "
            "llama3.1:8b, granite3.1-dense:8b, michaelborck/refuled\n"
            "Resume:  RESUME=1 elt-llm-consumer-glossary"
        ),
    )
    parser.add_argument(
        "--model", default=None,
        help="Override LLM model (default: from rag_config.yaml)",
    )
    parser.add_argument(
        "--type", choices=["dataobjects", "interfaces", "both"], default="both",
        help="Which catalog to generate (default: both)",
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_RAG_CONFIG,
        help=f"Path to rag_config.yaml (default: {_DEFAULT_RAG_CONFIG})",
    )
    parser.add_argument(
        "--excel", type=Path, default=_DEFAULT_EXCEL,
        help=f"Path to LeanIX inventory Excel file (default: {_DEFAULT_EXCEL})",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=_DEFAULT_OUTPUT_DIR,
        help=f"Output directory for catalog CSVs (default: {_DEFAULT_OUTPUT_DIR})",
    )
    args = parser.parse_args()
    resume = os.environ.get("RESUME", "0") == "1"

    excel_path = args.excel.expanduser()
    output_dir = args.output_dir.expanduser()

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
    print(f"  Top-k:  {rag_config.query.similarity_top_k}")

    if resume:
        print("  Mode:   RESUME (skipping already-written rows)")

    print("\nResolving collections…")
    collections = get_collections(rag_config)

    if not collections:
        print("ERROR: No collections found. Run ingestion first.", file=sys.stderr)
        sys.exit(1)

    if args.type in ("dataobjects", "both"):
        generate_dataobjects(rag_config, collections, excel_path, output_dir, resume)

    if args.type in ("interfaces", "both"):
        generate_interfaces(rag_config, collections, excel_path, output_dir, resume)

    print("\n=== Complete ===")
    if args.type in ("dataobjects", "both"):
        print(f"  DataObjects → {output_dir / 'fa_business_catalog_dataobjects.csv'}")
    if args.type in ("interfaces", "both"):
        print(f"  Interfaces  → {output_dir / 'fa_business_catalog_interfaces.csv'}")
