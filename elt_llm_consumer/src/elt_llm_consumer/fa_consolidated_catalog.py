"""FA Consolidated Catalog generator.

Pure RAG+LLM implementation — no direct file parsing, no dependencies on other consumers.

Prerequisites (via ingestion only):
  1. LeanIX Conceptual Model → fa_leanix_dat_enterprise_conceptual_model_* collections
  2. LeanIX Global Inventory → fa_leanix_global_inventory_* collections
  3. FA Handbook → fa_handbook collection

All data extraction is performed via RAG queries to ChromaDB collections.
No bespoke parsers. No direct XML/Excel reading. No inter-consumer dependencies.

Process:
  Step 1: Extract all conceptual model entities via RAG query
          → Queries fa_leanix_dat_enterprise_conceptual_model_* collections
          → LLM extracts: entity_name, domain, fact_sheet_id, relationships

  Step 2: Extract inventory descriptions via RAG query
          → Queries fa_leanix_global_inventory_* collections
          → LLM extracts: descriptions per fact_sheet_id

  Step 3: Extract Handbook defined terms via docstore markers
          → Reads fa_handbook docstore definition markers
          → Extracts: term, definition, category, governance

  Step 4: Map Handbook terms → Conceptual Model entities via RAG
          → For each Handbook term, query conceptual model collections
          → LLM determines: mapped entity, confidence, rationale

  Step 5: Extract relationships from all sources via RAG
          → Conceptual model relationships
          → Handbook co-occurrence relationships
          → Inventory system dependencies

  Step 6: Consolidate and classify entities
          → BOTH: In both conceptual model and Handbook
          → LEANIX_ONLY: Only in conceptual model
          → HANDBOOK_ONLY: Only in Handbook (candidate for model addition)

  Step 7: Output structured JSON + CSV for Purview import

Outputs (~/.tmp/elt_llm_consumer/ or project .tmp/):
  fa_consolidated_catalog.json      ← Merged catalog with all 7 requirements
  fa_consolidated_catalog.csv       ← CSV export for Purview import
  fa_consolidated_relationships.json ← Relationships with source attribution

Usage:
    # Full consolidation (pure RAG — no other consumers required)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

    # With specific model override
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --model qwen2.5:14b

    # Skip relationship extraction (faster, ~5 min)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --skip-relationships

    # CSV export only (after JSON already generated)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --csv-only

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled

Runtime:
  - Full run (entities + descriptions + Handbook mapping + relationships): ~30-60 min
  - Skip relationships: ~15-30 min
  - CSV-only: ~5 seconds
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_ENTITY_EXTRACTION_PROMPT = """\
Extract all entities from the FA Enterprise Conceptual Data Model.

For each entity, provide:
- entity_name: The exact entity name (e.g., "Club", "Player", "Competition")
- domain: The domain group (e.g., PARTY, AGREEMENT, PRODUCT, TRANSACTION AND EVENTS, LOCATION, REFERENCE DATA)
- fact_sheet_id: The LeanIX fact sheet ID (numeric identifier)
- hierarchy_level: The level in the hierarchy (e.g., "Level 1", "Level 2", or "Not specified")

Return your response as a JSON array with this exact structure:
[
  {
    "entity_name": "Club",
    "domain": "PARTY",
    "fact_sheet_id": "12345",
    "hierarchy_level": "Level 1"
  },
  ...
]

If a field is not found in the retrieved content, use "Not documented" as the value.
Do not include any text outside the JSON array."""

_INVENTORY_DESCRIPTION_PROMPT = """\
Find the LeanIX inventory description for the entity with fact_sheet_id '{fact_sheet_id}' (entity: {entity_name}).

Provide:
- description: The exact description from the LeanIX inventory
- level: The hierarchy level if available
- status: The status if available
- system_name: The system/application name if this is an application or data object

Return as JSON:
{{
  "description": "...",
  "level": "...",
  "status": "...",
  "system_name": "..."
}}

If not found, return all fields as "Not documented"."""

_HANDBOOK_TERM_MAPPING_PROMPT = """\
The FA Handbook defines the term '{term}' as:
"{definition}"

Which entity in the FA Enterprise Conceptual Data Model (LeanIX) does this correspond to?

Provide:
- mapped_entity: Exact entity name from the model, or "Not mapped" if no match
- domain: Domain the entity belongs to (e.g., PARTY, AGREEMENT, PRODUCT)
- fact_sheet_id: LeanIX fact sheet ID if shown in retrieved content
- mapping_confidence: high / medium / low
- mapping_rationale: One sentence explaining the mapping decision

Return as JSON:
{{
  "mapped_entity": "...",
  "domain": "...",
  "fact_sheet_id": "...",
  "mapping_confidence": "...",
  "mapping_rationale": "..."
}}

If the term is operational/procedural and not represented as a distinct entity, use "Not mapped"."""

_RELATIONSHIP_EXTRACTION_PROMPT = """\
Extract all relationships for the entity '{entity_name}' from the FA Enterprise Conceptual Data Model.

For each relationship, provide:
- target_entity: The entity it relates to
- relationship_type: The type of relationship (e.g., "participates_in", "employs", "owns")
- cardinality: If specified (e.g., "1..*", "0..1", "many-to-many")
- direction: "unidirectional" or "bidirectional"

Return as JSON array:
[
  {{
    "target_entity": "...",
    "relationship_type": "...",
    "cardinality": "...",
    "direction": "..."
  }},
  ...
]

If no relationships are documented, return an empty array []."""

# ---------------------------------------------------------------------------
# Definition marker extraction from docstore
# ---------------------------------------------------------------------------

_DEF_MARKER = "**FA Handbook defined term**"
_DEF_LINE_PAT = re.compile(
    r"\*\*FA Handbook defined term\*\* \[source: (\w+)\]: (.+?) means (.+)",
)


def extract_handbook_terms_from_docstore(rag_config: RagConfig) -> list[dict]:
    """Extract defined terms from fa_handbook docstore.

    Uses definition markers produced by RegulatoryPDFPreprocessor during ingestion.
    This is NOT direct file parsing — it's querying the already-built index.
    """
    from llama_index.core import StorageContext

    docstore_path = get_docstore_path(rag_config.chroma, "fa_handbook")
    if not docstore_path.exists():
        print(
            f"ERROR: Docstore not found at {docstore_path}.\n"
            "Run ingestion first: uv run python -m elt_llm_ingest.runner ingest ingest_fa_handbook",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Loading fa_handbook docstore: {docstore_path}")
    storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
    nodes = list(storage.docstore.docs.values())
    print(f"  {len(nodes)} nodes in fa_handbook docstore")

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
            terms.append({
                "term": term,
                "definition": defn,
                "definition_source": source,
            })

    terms.sort(key=lambda x: x["term"].lower())
    print(f"  {len(terms)} unique defined terms extracted from docstore")
    return terms


# ---------------------------------------------------------------------------
# RAG-based extraction functions
# ---------------------------------------------------------------------------


def extract_entities_via_rag(collections: list[str], rag_config: RagConfig) -> list[dict]:
    """Extract all conceptual model entities via RAG query.

    Queries fa_leanix_dat_enterprise_conceptual_model_* collections.
    LLM extracts structured entity list from retrieved chunks.
    """
    print("  Querying conceptual model collections for all entities…")

    result = query_collections(collections, _ENTITY_EXTRACTION_PROMPT, rag_config)
    response = result.response.strip()

    # Parse JSON from response
    try:
        # Try to extract JSON array from response
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
        if json_match:
            entities = json.loads(json_match.group())
        else:
            # Try parsing entire response as JSON
            entities = json.loads(response)
        print(f"  {len(entities)} entities extracted via RAG")
        return entities
    except json.JSONDecodeError as e:
        print(f"  WARNING: JSON parsing failed: {e}")
        print(f"  Response preview: {response[:200]}...")
        # Return empty list — will fall back to retrieval-based extraction
        return []


def extract_inventory_description(
    fact_sheet_id: str,
    entity_name: str,
    collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Extract inventory description for a specific fact_sheet_id via RAG."""
    query = _INVENTORY_DESCRIPTION_PROMPT.format(
        fact_sheet_id=fact_sheet_id,
        entity_name=entity_name,
    )

    try:
        result = query_collections(collections, query, rag_config)
        response = result.response.strip()

        # Parse JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {"description": "Not documented", "level": "", "status": "", "system_name": ""}
    except Exception as e:
        return {"description": f"[Error: {e}]", "level": "", "status": "", "system_name": ""}


def map_handbook_term_to_entity(
    term: str,
    definition: str,
    model_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Map a Handbook defined term to a conceptual model entity via RAG."""
    query = _HANDBOOK_TERM_MAPPING_PROMPT.format(term=term, definition=definition)

    try:
        result = query_collections(model_collections, query, rag_config)
        response = result.response.strip()

        # Parse JSON
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return {
            "mapped_entity": "Not mapped",
            "domain": "",
            "fact_sheet_id": "",
            "mapping_confidence": "low",
            "mapping_rationale": "",
        }
    except Exception as e:
        return {
            "mapped_entity": "Not mapped",
            "domain": "",
            "fact_sheet_id": "",
            "mapping_confidence": "low",
            "mapping_rationale": f"[Error: {e}]",
        }


def extract_relationships_via_rag(
    entity_name: str,
    model_collections: list[str],
    rag_config: RagConfig,
) -> list[dict]:
    """Extract relationships for an entity via RAG query."""
    query = _RELATIONSHIP_EXTRACTION_PROMPT.format(entity_name=entity_name)

    try:
        result = query_collections(model_collections, query, rag_config)
        response = result.response.strip()

        # Parse JSON array
        json_match = re.search(r'\[\s*\{.*\}\s*\]', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return []
    except Exception as e:
        return []


# ---------------------------------------------------------------------------
# Handbook context enrichment
# ---------------------------------------------------------------------------


def get_handbook_context_for_entity(
    entity_name: str,
    domain: str,
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Get FA Handbook context (definition, governance, domain context) for an entity."""
    query = f"""
Provide a terms of reference entry for the FA entity '{entity_name}' in the {domain} domain.

Structure your response with these three sections:

FORMAL_DEFINITION:
[What is this entity? Provide a formal definition. Quote exact FA Handbook definition if one exists.]

DOMAIN_CONTEXT:
[What role does it play within the {domain} domain? What related concepts should be considered?]

GOVERNANCE:
[What specific FA Handbook rules, obligations, or regulatory requirements apply?
Cite section and rule numbers where possible (e.g. Rule A3.1, Section C).
If no handbook rules apply, state 'Not documented in FA Handbook — outside governance scope'.]
"""

    try:
        result = query_collections(handbook_collections, query, rag_config)
        response = result.response.strip()

        # Parse sections
        sections = {}
        for key in ("FORMAL_DEFINITION", "DOMAIN_CONTEXT", "GOVERNANCE"):
            match = re.search(rf"{key}:\s*(.*?)(?=\n[A-Z]+:|\Z)", response, re.DOTALL)
            if match:
                sections[key.lower()] = match.group(1).strip()
            else:
                sections[key.lower()] = ""

        return sections
    except Exception as e:
        return {
            "formal_definition": f"[Error: {e}]",
            "domain_context": "",
            "governance_rules": "",
        }


# ---------------------------------------------------------------------------
# Consolidation logic
# ---------------------------------------------------------------------------


def _normalize(name: str) -> str:
    """Normalize entity name for matching."""
    return " ".join(name.lower().split())


def consolidate_catalog(
    conceptual_entities: list[dict],
    handbook_terms: list[dict],
    handbook_mappings: dict[str, dict],
    inventory_descriptions: dict[str, dict],
    handbook_context: dict[str, dict],
    relationships: dict[str, list[dict]],
) -> tuple[list[dict], list[dict]]:
    """Merge conceptual model + Handbook entities into unified catalog.

    Returns:
        consolidated_entities: List of merged entity records
        consolidated_relationships: List of relationship records with source attribution
    """
    consolidated: list[dict] = []
    seen_names: set[str] = set()

    print("\n=== Consolidating Entities ===")

    # Step 1: Process all conceptual model entities
    for entity in conceptual_entities:
        name = entity.get("entity_name", "")
        name_lower = name.lower()
        fsid = entity.get("fact_sheet_id", "")
        domain = entity.get("domain", "UNKNOWN")

        seen_names.add(name_lower)

        # Determine source classification
        mapped = handbook_mappings.get(name_lower, {})
        if mapped.get("mapped_entity", "").lower() not in ("not mapped", ""):
            source = "BOTH"
        else:
            source = "LEANIX_ONLY"

        # Get inventory description
        inv = inventory_descriptions.get(fsid, {})
        leanix_description = inv.get("description", "Not documented")

        # Get handbook context
        hb_context = handbook_context.get(name_lower, {})

        # Get relationships
        entity_rels = relationships.get(name_lower, [])

        record = {
            "fact_sheet_id": fsid,
            "entity_name": name,
            "domain": domain,
            "hierarchy_level": entity.get("hierarchy_level", ""),
            "source": source,
            "leanix_description": leanix_description,
            "formal_definition": hb_context.get("formal_definition", ""),
            "domain_context": hb_context.get("domain_context", ""),
            "governance_rules": hb_context.get("governance_rules", ""),
            "handbook_term": None,  # Will be set if this maps to a Handbook term
            "mapping_confidence": mapped.get("mapping_confidence", ""),
            "mapping_rationale": mapped.get("mapping_rationale", ""),
            "review_status": "PENDING",
            "review_notes": "",
            "relationships": entity_rels,
        }

        consolidated.append(record)

    # Step 2: Add HANDBOOK_ONLY entities
    handbook_only_count = 0
    for term_entry in handbook_terms:
        term = term_entry["term"]
        term_lower = term.lower()

        if term_lower in seen_names:
            continue

        mapped = handbook_mappings.get(term_lower, {})
        if mapped.get("mapped_entity", "").lower() not in ("not mapped", ""):
            # Already matched to a conceptual entity
            continue

        handbook_only_count += 1

        # Get handbook context for this term
        hb_context = handbook_context.get(term_lower, {})

        record = {
            "fact_sheet_id": "",
            "entity_name": term,
            "domain": "HANDBOOK_DISCOVERED",
            "hierarchy_level": "",
            "source": "HANDBOOK_ONLY",
            "leanix_description": "Not documented in LeanIX — candidate for conceptual model addition",
            "formal_definition": term_entry.get("definition", ""),
            "domain_context": hb_context.get("domain_context", ""),
            "governance_rules": hb_context.get("governance_rules", ""),
            "handbook_term": term,
            "mapping_confidence": "low",
            "mapping_rationale": "Discovered in Handbook but not mapped to conceptual model",
            "review_status": "PENDING",
            "review_notes": f"Handbook term awaiting SME review for model inclusion",
            "relationships": [],
        }

        consolidated.append(record)

    print(f"  Conceptual model entities: {len(conceptual_entities)}")
    print(f"  Handbook-only entities added: {handbook_only_count}")
    print(f"  Total consolidated: {len(consolidated)}")

    # Step 3: Build consolidated relationships
    consolidated_relationships: list[dict] = []
    seen_rels: set[tuple] = set()

    for entity_name, rels in relationships.items():
        for rel in rels:
            target = rel.get("target_entity", "")
            key = tuple(sorted([entity_name.lower(), target.lower()]))
            if key not in seen_rels:
                seen_rels.add(key)
                consolidated_relationships.append({
                    "entity_a": entity_name,
                    "entity_b": target,
                    "relationship_type": rel.get("relationship_type", ""),
                    "cardinality": rel.get("cardinality", ""),
                    "direction": rel.get("direction", "bidirectional"),
                    "source": "LEANIX_CONCEPTUAL_MODEL",
                })

    print(f"  Total consolidated relationships: {len(consolidated_relationships)}")

    return consolidated, consolidated_relationships


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_to_csv(entities: list[dict], output_path: Path) -> None:
    """Export consolidated catalog to CSV for Purview import.

    CSV columns aligned with Purview business glossary import format.
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
        "review_notes",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for entity in entities:
            description = (
                entity.get("formal_definition")
                or entity.get("leanix_description")
                or ""
            )

            # Extract related terms from relationships
            all_rels = set()
            for rel in entity.get("relationships", []):
                target = rel.get("target_entity", "")
                if target:
                    all_rels.add(target)

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
                "review_notes": entity.get("review_notes", ""),
            }
            writer.writerow(row)

    print(f"  CSV exported → {output_path}")


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


def generate_consolidated_catalog(
    rag_config: RagConfig,
    model_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    output_dir: Path,
    skip_relationships: bool,
    csv_only: bool,
) -> None:
    """Generate consolidated catalog via pure RAG queries."""

    catalog_json_path = output_dir / "fa_consolidated_catalog.json"
    catalog_csv_path = output_dir / "fa_consolidated_catalog.csv"
    relationships_json_path = output_dir / "fa_consolidated_relationships.json"

    # CSV-only mode
    if csv_only:
        if not catalog_json_path.exists():
            print("ERROR: fa_consolidated_catalog.json not found. Run without --csv-only first.")
            return

        with open(catalog_json_path, "r", encoding="utf-8") as f:
            entities = json.load(f)

        export_to_csv(entities, catalog_csv_path)
        return

    print("\n=== FA Consolidated Catalog (Pure RAG+LLM) ===")
    print(f"  Model: {rag_config.ollama.llm_model}")
    print(f"  Collections:")
    print(f"    - Conceptual Model ({len(model_collections)}): {', '.join(model_collections)}")
    print(f"    - Inventory ({len(inventory_collections)}): {', '.join(inventory_collections)}")
    print(f"    - Handbook ({len(handbook_collections)}): {', '.join(handbook_collections)}")

    # Step 1: Extract conceptual model entities via RAG
    print("\n=== Step 1: Extract Conceptual Model Entities ===")
    conceptual_entities = extract_entities_via_rag(model_collections, rag_config)

    if not conceptual_entities:
        print("  WARNING: RAG entity extraction returned empty list.")
        print("  This may indicate the conceptual model collections need re-ingestion.")
        conceptual_entities = []

    # Step 2: Extract inventory descriptions via RAG
    print("\n=== Step 2: Extract Inventory Descriptions ===")
    inventory_descriptions: dict[str, dict] = {}
    for entity in conceptual_entities:
        fsid = entity.get("fact_sheet_id", "")
        name = entity.get("entity_name", "")
        if fsid and inventory_collections:
            inv = extract_inventory_description(fsid, name, inventory_collections, rag_config)
            inventory_descriptions[fsid] = inv

    print(f"  {len(inventory_descriptions)} inventory descriptions extracted")

    # Step 3: Extract Handbook defined terms from docstore
    print("\n=== Step 3: Extract Handbook Defined Terms ===")
    handbook_terms = extract_handbook_terms_from_docstore(rag_config)

    # Step 4: Map Handbook terms to conceptual model entities via RAG
    print("\n=== Step 4: Map Handbook Terms to Conceptual Model ===")
    handbook_mappings: dict[str, dict] = {}
    for i, term_entry in enumerate(handbook_terms, 1):
        term = term_entry["term"]
        definition = term_entry["definition"]
        print(f"  [{i}/{len(handbook_terms)}] {term}…", end=" ", flush=True)

        mapping = map_handbook_term_to_entity(term, definition, model_collections, rag_config)
        handbook_mappings[term.lower()] = mapping

        mapped_entity = mapping.get("mapped_entity", "Not mapped")
        print(f"→ {mapped_entity}" if mapped_entity.lower() != "not mapped" else "→ not mapped")

    # Step 5: Get handbook context for all entities
    print("\n=== Step 5: Extract Handbook Context ===")
    handbook_context: dict[str, dict] = {}

    # Context for conceptual model entities
    for entity in conceptual_entities:
        name = entity.get("entity_name", "")
        domain = entity.get("domain", "UNKNOWN")
        print(f"  {name}…", end=" ", flush=True)

        context = get_handbook_context_for_entity(name, domain, handbook_collections, rag_config)
        handbook_context[name.lower()] = context
        print("done")

    # Context for Handbook-only terms (for enrichment)
    for term_entry in handbook_terms:
        term = term_entry["term"]
        if term.lower() not in handbook_context:
            print(f"  {term} (Handbook term)…", end=" ", flush=True)
            context = get_handbook_context_for_entity(term, "HANDBOOK", handbook_collections, rag_config)
            handbook_context[term.lower()] = context
            print("done")

    # Step 6: Extract relationships via RAG (optional)
    print("\n=== Step 6: Extract Relationships ===")
    relationships: dict[str, list[dict]] = {}

    if skip_relationships:
        print("  Skipping relationship extraction (--skip-relationships)")
    else:
        for entity in conceptual_entities:
            name = entity.get("entity_name", "")
            print(f"  {name}…", end=" ", flush=True)

            rels = extract_relationships_via_rag(name, model_collections, rag_config)
            relationships[name.lower()] = rels
            print(f"{len(rels)} relationships")

    # Step 7: Consolidate
    print("\n=== Step 7: Consolidating ===")
    consolidated_entities, consolidated_relationships = consolidate_catalog(
        conceptual_entities,
        handbook_terms,
        handbook_mappings,
        inventory_descriptions,
        handbook_context,
        relationships,
    )

    # Write outputs
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_entities, f, indent=2, ensure_ascii=False)

    with open(relationships_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_relationships, f, indent=2, ensure_ascii=False)

    print(f"\n  Consolidated catalog (JSON) → {catalog_json_path}")
    print(f"  Consolidated relationships → {relationships_json_path}")

    # Export CSV
    export_to_csv(consolidated_entities, catalog_csv_path)

    # Summary
    source_counts: dict[str, int] = {}
    for e in consolidated_entities:
        src = e.get("source", "UNKNOWN")
        source_counts[src] = source_counts.get(src, 0) + 1

    print("\n=== Summary by Source ===")
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")

    status_counts: dict[str, int] = {}
    for e in consolidated_entities:
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
            "Generate FA Consolidated Catalog via pure RAG+LLM queries — "
            "no direct file parsing, no dependencies on other consumers"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, "
            "llama3.1:8b, granite3.1-dense:8b, michaelborck/refuled\n\n"
            "Output:  JSON + CSV format for Purview import\n\n"
            "Prerequisites (ingestion only):\n"
            "  - LeanIX Conceptual Model ingested to fa_leanix_dat_enterprise_conceptual_model_*\n"
            "  - LeanIX Inventory ingested to fa_leanix_global_inventory_*\n"
            "  - FA Handbook ingested to fa_handbook"
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
        "--skip-relationships", action="store_true",
        help="Skip relationship extraction (faster, ~5 min)",
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
            rag_config=None,
            model_collections=[],
            inventory_collections=[],
            handbook_collections=[],
            output_dir=output_dir,
            skip_relationships=False,
            csv_only=True,
        )
        return

    # Full consolidation
    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    if args.model:
        rag_config.ollama.llm_model = args.model
        print(f"  Model override: {args.model}")

    print(f"  LLM: {rag_config.ollama.llm_model}")

    # Resolve collections
    print("\nResolving collections…")
    model_collections = resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    inventory_collections = resolve_collection_prefixes(
        ["fa_leanix_global_inventory"], rag_config
    )
    handbook_collections = ["fa_handbook"]

    if not model_collections:
        print(
            "\nERROR: No conceptual model collections found.\n"
            "Run: uv run python -m elt_llm_ingest.runner ingest "
            "ingest_fa_leanix_dat_enterprise_conceptual_model",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Conceptual Model ({len(model_collections)}): {', '.join(model_collections)}")
    print(f"  Inventory ({len(inventory_collections)}): {', '.join(inventory_collections) if inventory_collections else 'None found'}")
    print(f"  Handbook: fa_handbook")

    generate_consolidated_catalog(
        rag_config=rag_config,
        model_collections=model_collections,
        inventory_collections=inventory_collections,
        handbook_collections=handbook_collections,
        output_dir=output_dir,
        skip_relationships=args.skip_relationships,
        csv_only=False,
    )

    print("\n=== Complete ===")
    print(f"  Consolidated catalog (JSON) → {output_dir / 'fa_consolidated_catalog.json'}")
    print(f"  Consolidated catalog (CSV)  → {output_dir / 'fa_consolidated_catalog.csv'}")
    print(f"  Consolidated relationships  → {output_dir / 'fa_consolidated_relationships.json'}")
    print("\nNext steps:")
    print("  1. Review fa_consolidated_catalog.json with Data Architects")
    print("  2. Update review_status fields (APPROVED/REJECTED/NEEDS_CLARIFICATION)")
    print("  3. Re-export CSV: --csv-only")
    print("  4. Import to Purview")


if __name__ == "__main__":
    main()
