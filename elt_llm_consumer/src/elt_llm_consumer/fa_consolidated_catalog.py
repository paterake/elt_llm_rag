"""FA Consolidated Catalog generator.

Merges LeanIX Conceptual Model entities with Handbook-discovered entities into a
single unified catalog for stakeholder review.

Three-source consolidation:
  1. LeanIX Conceptual Model (XML) — canonical entities with domain, hierarchy, relationships
  2. LeanIX Inventory (Excel) — descriptions joined by fact_sheet_id
  3. FA Handbook (RAG + JSON outputs) — definitions, governance, candidate entities

Entity classification:
  - BOTH: Entity exists in LeanIX CM and Handbook (matched by name)
  - LEANIX_ONLY: Entity in LeanIX CM but not discussed in Handbook
  - HANDBOOK_ONLY: Entity discovered in Handbook but missing from LeanIX CM

Review status tracking:
  - PENDING: Awaiting stakeholder review
  - APPROVED: Reviewed and approved for Purview import
  - REJECTED: Reviewed and rejected (with reason)
  - NEEDS_CLARIFICATION: Requires SME input before approval

Relationships are kept separate by source for lineage tracking:
  - leanix_relationships: From LeanIX conceptual model
  - handbook_relationships: From Handbook co-occurrence inference

Outputs (~/.tmp/elt_llm_consumer/):
  fa_consolidated_catalog.json      ← Merged catalog with source classification
  fa_consolidated_catalog.csv       ← CSV export for Purview import
  fa_consolidated_relationships.json ← Merged relationships with source attribution

Usage:
    # Full consolidation (requires all upstream outputs)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

    # With specific model override
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --model qwen2.5:14b

    # Re-run enrichment for HANDBOOK_ONLY entities (they lack RAG enrichment)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --enrich-handbook-only

    # Export CSV only (after JSON already generated)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --csv-only

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled

Runtime:
  - Merge only: ~5-10 seconds
  - Enrichment (HANDBOOK_ONLY entities): ~10-20s per entity via RAG
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_query.query import query_collections

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

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

# Upstream outputs (from other consumer scripts)
_DEFAULT_INTEGRATED_CATALOG = Path(
    "~/.tmp/elt_llm_consumer/fa_integrated_catalog.json"
).expanduser()

_DEFAULT_HANDBOOK_ENTITIES = Path(
    "~/.tmp/elt_llm_consumer/fa_handbook_candidate_entities.json"
).expanduser()

_DEFAULT_HANDBOOK_RELATIONSHIPS = Path(
    "~/.tmp/elt_llm_consumer/fa_handbook_candidate_relationships.json"
).expanduser()

_DEFAULT_COVERAGE_REPORT = Path(
    "~/.tmp/elt_llm_consumer/fa_coverage_report.json"
).expanduser()

_DEFAULT_GAP_ANALYSIS = Path(
    "~/.tmp/elt_llm_consumer/fa_gap_analysis.json"
).expanduser()

# ---------------------------------------------------------------------------
# System prompt for Handbook-only entity enrichment
# ---------------------------------------------------------------------------

_ENRICHMENT_PROMPT = """\
You are an expert FA Enterprise Architect and Data Management consultant.
You have access to the FA Handbook — the authoritative source for governance,
definitions, and regulatory obligations.

Provide a terms of reference entry for the FA concept '{name}'.

Structure your response using exactly these three headings:

FORMAL_DEFINITION:
[What is this concept? Provide a formal definition based on the FA Handbook.
If an exact definition exists, quote it verbatim with the source section.]

DOMAIN_CONTEXT:
[What role does this concept play in FA governance/operations?
What related concepts or entities should be considered?]

GOVERNANCE:
[What specific FA Handbook rules, obligations, or regulatory requirements apply?
Cite section and rule numbers where possible (e.g. Rule A3.1, Section C).
If no handbook rules apply, state 'Not documented in FA Handbook — outside governance scope'.]"""

# ---------------------------------------------------------------------------
# Source loading
# ---------------------------------------------------------------------------


def load_conceptual_model(xml_path: Path) -> tuple[list[dict], dict[str, list[str]]]:
    """Parse draw.io XML → list of entity dicts + relationship index.
    
    Returns:
        entities: List of entity dicts with fact_sheet_id, entity_name, domain
        relationships: Dict mapping entity_name → list of related entity names
    """
    try:
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

    # Build relationship index
    rel_index: dict[str, list[str]] = {}
    for rel in extractor.relationships:
        if rel.source_label and rel.target_label:
            rel_index.setdefault(rel.source_label, []).append(rel.target_label)
            rel_index.setdefault(rel.target_label, []).append(rel.source_label)

    entities: list[dict] = []
    for asset_id, asset in extractor.assets.items():
        if not asset.label or not asset.fact_sheet_id:
            continue
        entities.append({
            "fact_sheet_id": asset.fact_sheet_id,
            "entity_name": asset.label,
            "domain": asset.parent_group or "UNKNOWN",
            "xml_id": asset_id,
        })

    print(f"  {len(entities)} entities loaded from conceptual model")
    return entities, rel_index


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
                "lx_state": str(row.get("lx_state") or "").strip(),
            }
    print(f"  {len(inventory)} inventory entries loaded")
    return inventory


def load_integrated_catalog(path: Path) -> dict[str, dict]:
    """Load integrated catalog (from fa_integrated_catalog.py) → dict by entity_name."""
    if not path.exists():
        return {}
    
    print(f"  Loading integrated catalog: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    catalog: dict[str, dict] = {}
    for row in data:
        name = (row.get("entity_name") or "").strip()
        if name:
            catalog[name.lower()] = row
    
    print(f"  {len(catalog)} entries loaded from integrated catalog")
    return catalog


def load_handbook_entities(path: Path) -> dict[str, dict]:
    """Load Handbook-discovered entities → dict by normalized name."""
    if not path.exists():
        return {}
    
    print(f"  Loading Handbook candidate entities: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    entities: dict[str, dict] = {}
    for row in data:
        term = (row.get("term") or row.get("entity_name") or "").strip()
        if term:
            entities[term.lower()] = {
                "term": term,
                "definition": row.get("definition", ""),
                "category": row.get("category", ""),
                "governance": row.get("governance", ""),
                "source_topic": row.get("source_topic", ""),
            }
    
    print(f"  {len(entities)} Handbook entities loaded")
    return entities


def load_handbook_relationships(path: Path) -> list[dict]:
    """Load Handbook-discovered relationships."""
    if not path.exists():
        return []
    
    print(f"  Loading Handbook candidate relationships: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    print(f"  {len(data)} relationships loaded")
    return data


def load_coverage_report(path: Path) -> dict[str, dict]:
    """Load coverage report → dict by entity_name."""
    if not path.exists():
        return {}
    
    print(f"  Loading coverage report: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    coverage: dict[str, dict] = {}
    for row in data:
        name = (row.get("entity_name") or "").strip()
        if name:
            coverage[name.lower()] = {
                "verdict": row.get("verdict", ""),
                "top_score": row.get("top_score", 0),
                "chunks_found": row.get("chunks_found", 0),
            }
    
    print(f"  {len(coverage)} coverage entries loaded")
    return coverage


def load_gap_analysis(path: Path) -> dict[str, dict]:
    """Load gap analysis → dict by normalized_name."""
    if not path.exists():
        return {}
    
    print(f"  Loading gap analysis: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    gaps: dict[str, dict] = {}
    for row in data:
        norm_name = (row.get("normalized_name") or "").strip()
        if norm_name:
            gaps[norm_name] = {
                "model_name": row.get("model_name", ""),
                "handbook_name": row.get("handbook_name", ""),
                "status": row.get("status", ""),
            }
    
    print(f"  {len(gaps)} gap analysis entries loaded")
    return gaps


# ---------------------------------------------------------------------------
# Consolidation logic
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Normalize entity name for matching."""
    return " ".join(name.lower().split())


def consolidate_catalog(
    leanix_entities: list[dict],
    leanix_relationships: dict[str, list[str]],
    inventory: dict[str, dict],
    integrated_catalog: dict[str, dict],
    handbook_entities: dict[str, dict],
    handbook_relationships: list[dict],
    coverage: dict[str, dict],
    gap_analysis: dict[str, dict],
) -> tuple[list[dict], list[dict]]:
    """Merge LeanIX + Handbook entities into unified catalog.
    
    Returns:
        consolidated_entities: List of merged entity records
        consolidated_relationships: List of merged relationship records with source attribution
    """
    consolidated_entities: list[dict] = []
    seen_names: set[str] = set()
    
    # Track which Handbook entities have been matched
    matched_handbook_names: set[str] = set()
    
    print("\n=== Consolidating Entities ===")
    
    # Step 1: Process all LeanIX entities
    for entity in leanix_entities:
        name = entity["entity_name"]
        name_lower = name.lower()
        norm_name = _normalize(name)
        fsid = entity["fact_sheet_id"]
        domain = entity["domain"]
        
        seen_names.add(name_lower)
        
        # Determine source classification
        if name_lower in handbook_entities:
            source = "BOTH"
            matched_handbook_names.add(name_lower)
        else:
            # Check gap analysis for fuzzy match
            gap_info = gap_analysis.get(norm_name, {})
            if gap_info.get("status") == "MATCHED":
                source = "BOTH"
                # Find the matched handbook name
                hb_name = gap_info.get("handbook_name", "").lower()
                if hb_name:
                    matched_handbook_names.add(hb_name)
            else:
                source = "LEANIX_ONLY"
        
        # Get inventory description
        inv = inventory.get(fsid, {})
        leanix_description = inv.get("description") or "Not documented"
        hierarchy_level = inv.get("level") or ""
        lx_state = inv.get("lx_state") or ""
        
        # Get integrated catalog enrichment (if available)
        integrated = integrated_catalog.get(name_lower, {})
        
        # Get coverage info
        cov = coverage.get(name_lower, {})
        
        # Build consolidated record
        record = {
            "fact_sheet_id": fsid,
            "entity_name": name,
            "domain": domain,
            "hierarchy_level": hierarchy_level,
            "lx_state": lx_state,
            "source": source,
            "leanix_description": leanix_description,
            "formal_definition": integrated.get("formal_definition", ""),
            "domain_context": integrated.get("domain_context", ""),
            "governance_rules": integrated.get("governance_rules", ""),
            "handbook_category": handbook_entities.get(name_lower, {}).get("category", ""),
            "coverage_verdict": cov.get("verdict", ""),
            "coverage_score": cov.get("top_score", 0),
            "review_status": "PENDING",
            "review_notes": "",
            "leanix_relationships": leanix_relationships.get(name, []),
            "handbook_relationships": [],
        }
        
        # Add Handbook relationships for this entity
        for rel in handbook_relationships:
            entity_a = rel.get("entity_a", "").lower()
            entity_b = rel.get("entity_b", "").lower()
            if entity_a == name_lower or entity_b == name_lower:
                record["handbook_relationships"].append({
                    "entity_a": rel.get("entity_a", ""),
                    "entity_b": rel.get("entity_b", ""),
                    "relationship": rel.get("relationship", ""),
                    "direction": rel.get("direction", ""),
                    "rules": rel.get("rules", ""),
                })
        
        consolidated_entities.append(record)
    
    # Step 2: Add HANDBOOK_ONLY entities
    handbook_only_count = 0
    for name_lower, hb_entity in handbook_entities.items():
        if name_lower in seen_names:
            continue
        
        # Check gap analysis
        gap_info = gap_analysis.get(_normalize(hb_entity["term"]), {})
        if gap_info.get("status") not in ("HANDBOOK_ONLY", "MATCHED"):
            # Not a Handbook-only entity, skip
            # But still check if it's truly unmatched
            if name_lower not in {k.lower() for k in integrated_catalog}:
                pass  # Continue to add it
            else:
                continue
        
        handbook_only_count += 1
        term = hb_entity["term"]
        
        record = {
            "fact_sheet_id": "",  # No LeanIX fact sheet ID
            "entity_name": term,
            "domain": "HANDBOOK_DISCOVERED",
            "hierarchy_level": "",
            "lx_state": "",
            "source": "HANDBOOK_ONLY",
            "leanix_description": "Not documented in LeanIX — candidate for conceptual model addition",
            "formal_definition": hb_entity.get("definition", ""),
            "domain_context": "",
            "governance_rules": hb_entity.get("governance", ""),
            "handbook_category": hb_entity.get("category", ""),
            "coverage_verdict": "",
            "coverage_score": 0,
            "review_status": "PENDING",
            "review_notes": f"Discovered from Handbook topic: {hb_entity.get('source_topic', '')}",
            "leanix_relationships": [],
            "handbook_relationships": [],
        }
        
        # Add Handbook relationships for this entity
        for rel in handbook_relationships:
            entity_a = rel.get("entity_a", "").lower()
            entity_b = rel.get("entity_b", "").lower()
            if entity_a == name_lower or entity_b == name_lower:
                record["handbook_relationships"].append({
                    "entity_a": rel.get("entity_a", ""),
                    "entity_b": rel.get("entity_b", ""),
                    "relationship": rel.get("relationship", ""),
                    "direction": rel.get("direction", ""),
                    "rules": rel.get("rules", ""),
                })
        
        consolidated_entities.append(record)
    
    print(f"  LeanIX entities: {len(leanix_entities)}")
    print(f"  Handbook-only entities added: {handbook_only_count}")
    print(f"  Total consolidated: {len(consolidated_entities)}")
    
    # Step 3: Consolidate relationships with source attribution
    consolidated_relationships: list[dict] = []
    seen_rels: set[tuple] = set()
    
    # Add LeanIX relationships
    for source_entity, targets in leanix_relationships.items():
        for target in targets:
            key = tuple(sorted([source_entity.lower(), target.lower()]))
            if key not in seen_rels:
                seen_rels.add(key)
                consolidated_relationships.append({
                    "entity_a": source_entity,
                    "entity_b": target,
                    "relationship": "Related to (from LeanIX conceptual model)",
                    "source": "LEANIX",
                    "direction": "Bidirectional",
                    "rules": "",
                })
    
    # Add Handbook relationships
    for rel in handbook_relationships:
        entity_a = rel.get("entity_a", "")
        entity_b = rel.get("entity_b", "")
        key = tuple(sorted([entity_a.lower(), entity_b.lower()]))
        if key not in seen_rels:
            seen_rels.add(key)
            consolidated_relationships.append({
                "entity_a": entity_a,
                "entity_b": entity_b,
                "relationship": rel.get("relationship", ""),
                "source": "HANDBOOK",
                "direction": rel.get("direction", ""),
                "rules": rel.get("rules", ""),
            })
    
    print(f"  Total consolidated relationships: {len(consolidated_relationships)}")
    
    return consolidated_entities, consolidated_relationships


# ---------------------------------------------------------------------------
# RAG enrichment for HANDBOOK_ONLY entities
# ---------------------------------------------------------------------------


def enrich_handbook_only_entities(
    entities: list[dict],
    collections: list[str],
    rag_config: RagConfig,
) -> None:
    """Enrich HANDBOOK_ONLY entities with RAG queries for formal definitions.
    
    This adds domain context and governance rules that may not have been
    captured in the initial Handbook model building pass.
    """
    handbook_only = [e for e in entities if e["source"] == "HANDBOOK_ONLY"]
    
    if not handbook_only:
        print("  No HANDBOOK_ONLY entities to enrich")
        return
    
    print(f"\n=== Enriching {len(handbook_only)} HANDBOOK_ONLY entities ===")
    
    for i, entity in enumerate(handbook_only, 1):
        name = entity["entity_name"]
        print(f"  [{i}/{len(handbook_only)}] {name}…", end=" ", flush=True)
        
        query = _ENRICHMENT_PROMPT.format(name=name)
        try:
            from elt_llm_query.query import query_collections
            result = query_collections(collections, query, rag_config)
            response = result.response.strip()
            
            # Parse response
            for line in response.splitlines():
                line = line.strip()
                if line.startswith("FORMAL_DEFINITION:"):
                    entity["formal_definition"] = line[len("FORMAL_DEFINITION:"):].strip()
                elif line.startswith("DOMAIN_CONTEXT:"):
                    entity["domain_context"] = line[len("DOMAIN_CONTEXT:"):].strip()
                elif line.startswith("GOVERNANCE:"):
                    entity["governance_rules"] = line[len("GOVERNANCE:"):].strip()
            
            print("done")
        except Exception as e:
            print(f"error: {e}")
            entity["review_notes"] += f" | Enrichment failed: {e}"


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_to_csv(entities: list[dict], output_path: Path) -> None:
    """Export consolidated catalog to CSV for Purview import.
    
    CSV columns aligned with Purview business glossary import format:
    - term: Business term name
    - description: Business description/definition
    - steward: Data steward (placeholder)
    - domain: Business domain
    - related_terms: Related entity names
    - source_system: Source (LeanIX / Handbook)
    - status: Review status
    """
    fieldnames = [
        "term",
        "description",
        "steward",
        "domain",
        "related_terms",
        "source_system",
        "status",
        "formal_definition",
        "governance_rules",
        "leanix_fact_sheet_id",
        "leanix_description",
        "coverage_verdict",
        "review_notes",
    ]
    
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for entity in entities:
            # Combine definitions for description
            description = (
                entity.get("formal_definition")
                or entity.get("leanix_description")
                or ""
            )
            
            # Combine relationships
            all_rels = set(entity.get("leanix_relationships", []))
            for rel in entity.get("handbook_relationships", []):
                other = rel.get("entity_b") if rel.get("entity_a", "").lower() == entity.get("entity_name", "").lower() else rel.get("entity_a")
                if other:
                    all_rels.add(other)
            
            row = {
                "term": entity.get("entity_name", ""),
                "description": description.replace("\n", " ").replace("\r", ""),
                "steward": "",  # Placeholder — to be filled during review
                "domain": entity.get("domain", ""),
                "related_terms": "; ".join(sorted(all_rels)) if all_rels else "",
                "source_system": entity.get("source", ""),
                "status": entity.get("review_status", ""),
                "formal_definition": entity.get("formal_definition", "").replace("\n", " | ").replace("\r", ""),
                "governance_rules": entity.get("governance_rules", "").replace("\n", " | ").replace("\r", ""),
                "leanix_fact_sheet_id": entity.get("fact_sheet_id", ""),
                "leanix_description": entity.get("leanix_description", ""),
                "coverage_verdict": entity.get("coverage_verdict", ""),
                "review_notes": entity.get("review_notes", ""),
            }
            writer.writerow(row)
    
    print(f"  CSV exported → {output_path}")


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


def generate_consolidated_catalog(
    leanix_entities: list[dict],
    leanix_relationships: dict[str, list[str]],
    inventory: dict[str, dict],
    integrated_catalog: dict[str, dict],
    handbook_entities: dict[str, dict],
    handbook_relationships: list[dict],
    coverage: dict[str, dict],
    gap_analysis: dict[str, dict],
    rag_config: RagConfig | None,
    collections: list[str],
    output_dir: Path,
    enrich_handbook_only: bool,
    csv_only: bool,
) -> None:
    """Generate consolidated catalog JSON and CSV."""
    
    catalog_json_path = output_dir / "fa_consolidated_catalog.json"
    catalog_csv_path = output_dir / "fa_consolidated_catalog.csv"
    relationships_json_path = output_dir / "fa_consolidated_relationships.json"
    
    # CSV-only mode (use existing JSON)
    if csv_only:
        if not catalog_json_path.exists():
            print("ERROR: fa_consolidated_catalog.json not found. Run without --csv-only first.")
            return
        
        with open(catalog_json_path, "r", encoding="utf-8") as f:
            entities = json.load(f)
        
        export_to_csv(entities, catalog_csv_path)
        return
    
    # Full consolidation
    print("\n=== FA Consolidated Catalog Generation ===")
    
    entities, relationships = consolidate_catalog(
        leanix_entities,
        leanix_relationships,
        inventory,
        integrated_catalog,
        handbook_entities,
        handbook_relationships,
        coverage,
        gap_analysis,
    )
    
    # Enrich HANDBOOK_ONLY entities if requested
    if enrich_handbook_only and rag_config:
        enrich_handbook_only_entities(entities, collections, rag_config)
    
    # Write JSON outputs
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump(entities, f, indent=2, ensure_ascii=False)
    
    with open(relationships_json_path, "w", encoding="utf-8") as f:
        json.dump(relationships, f, indent=2, ensure_ascii=False)
    
    print(f"\n  Consolidated catalog → {catalog_json_path}")
    print(f"  Consolidated relationships → {relationships_json_path}")
    
    # Export CSV
    export_to_csv(entities, catalog_csv_path)
    
    # Summary by source
    source_counts: dict[str, int] = {}
    for e in entities:
        src = e.get("source", "UNKNOWN")
        source_counts[src] = source_counts.get(src, 0) + 1
    
    print("\n=== Summary by Source ===")
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")
    
    # Summary by review status
    status_counts: dict[str, int] = {}
    for e in entities:
        status = e.get("review_status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\n=== Summary by Review Status ===")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate FA Consolidated Catalog: merge LeanIX Conceptual Model + "
            "Handbook-discovered entities with source attribution for stakeholder review"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, "
            "llama3.1:8b, granite3.1-dense:8b, michaelborck/refuled\n\n"
            "Output:  JSON + CSV format for Purview import\n\n"
            "Prerequisites:\n"
            "  Run these before consolidation:\n"
            "    1. elt-llm-consumer-integrated-catalog\n"
            "    2. elt-llm-consumer-handbook-model\n"
            "    3. elt-llm-consumer-coverage-validator --gap-analysis"
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
        "--enrich-handbook-only", action="store_true",
        help="Run RAG enrichment for HANDBOOK_ONLY entities (adds ~10-20s per entity)",
    )
    parser.add_argument(
        "--csv-only", action="store_true",
        help="Only export CSV (assumes JSON already generated)",
    )
    args = parser.parse_args()
    
    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # CSV-only mode
    if args.csv_only:
        generate_consolidated_catalog(
            leanix_entities=[],
            leanix_relationships={},
            inventory={},
            integrated_catalog={},
            handbook_entities={},
            handbook_relationships=[],
            coverage={},
            gap_analysis={},
            rag_config=None,
            collections=[],
            output_dir=output_dir,
            enrich_handbook_only=False,
            csv_only=True,
        )
        return
    
    # Full consolidation
    xml_path = args.xml.expanduser()
    excel_path = args.excel.expanduser()
    
    if not xml_path.exists():
        print(f"ERROR: XML file not found: {xml_path}", file=sys.stderr)
        sys.exit(1)
    if not excel_path.exists():
        print(f"ERROR: Excel file not found: {excel_path}", file=sys.stderr)
        sys.exit(1)
    
    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)
    
    if args.model:
        rag_config.ollama.llm_model = args.model
        print(f"  Model override: {args.model}")
    
    print(f"  LLM: {rag_config.ollama.llm_model}")
    
    # Resolve collections for enrichment
    from elt_llm_query.query import resolve_collection_prefixes
    collections = ["fa_handbook"] + resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    print(f"  Collections: {collections}")
    
    print("\nLoading sources…")
    leanix_entities, leanix_relationships = load_conceptual_model(xml_path)
    inventory = load_inventory_descriptions(excel_path)
    integrated_catalog = load_integrated_catalog(_DEFAULT_INTEGRATED_CATALOG)
    handbook_entities = load_handbook_entities(_DEFAULT_HANDBOOK_ENTITIES)
    handbook_relationships = load_handbook_relationships(_DEFAULT_HANDBOOK_RELATIONSHIPS)
    coverage = load_coverage_report(_DEFAULT_COVERAGE_REPORT)
    gap_analysis = load_gap_analysis(_DEFAULT_GAP_ANALYSIS)
    
    if not integrated_catalog:
        print("\n  WARNING: fa_integrated_catalog.json not found.")
        print("  Run: uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog")
    
    if not handbook_entities:
        print("\n  WARNING: fa_handbook_candidate_entities.json not found.")
        print("  Run: uv run --package elt-llm-consumer elt-llm-consumer-handbook-model")
    
    generate_consolidated_catalog(
        leanix_entities=leanix_entities,
        leanix_relationships=leanix_relationships,
        inventory=inventory,
        integrated_catalog=integrated_catalog,
        handbook_entities=handbook_entities,
        handbook_relationships=handbook_relationships,
        coverage=coverage,
        gap_analysis=gap_analysis,
        rag_config=rag_config if args.enrich_handbook_only else None,
        collections=collections,
        output_dir=output_dir,
        enrich_handbook_only=args.enrich_handbook_only,
        csv_only=False,
    )
    
    print("\n=== Complete ===")
    print(f"  Consolidated catalog (JSON) → {output_dir / 'fa_consolidated_catalog.json'}")
    print(f"  Consolidated catalog (CSV)  → {output_dir / 'fa_consolidated_catalog.csv'}")
    print(f"  Consolidated relationships  → {output_dir / 'fa_consolidated_relationships.json'}")
    print("\nNext steps:")
    print("  1. Review fa_consolidated_catalog.json with stakeholders")
    print("  2. Update review_status fields (APPROVED/REJECTED/NEEDS_CLARIFICATION)")
    print("  3. Re-export CSV: --csv-only")
    print("  4. Import to Purview")


if __name__ == "__main__":
    main()
