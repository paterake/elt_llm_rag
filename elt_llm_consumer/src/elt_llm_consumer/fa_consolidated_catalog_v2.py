"""FA Consolidated Catalog Generator v2 — AI-Native Architecture.

This v2 implementation prioritizes RAG+LLM for intelligence and inference,
with deterministic extraction as a fallback for quality and completeness.

Architecture Philosophy:
  - AI-NATIVE for: definition lookup, context synthesis, governance extraction,
                   term mapping, domain inference
  - DETERMINISTIC for: entity enumeration (completeness), relationship structure
                       (explicit in source), docstore scanning (structured markers)

Key Differences from v1:
  - RAG-first for formal definitions, with docstore lookup as fallback
  - Improved governance extraction via targeted prompting
  - Cleaner separation between deterministic and AI-native components
  - Entity-level filtering for targeted runs

Prerequisites (via ingestion only):
  1. LeanIX Conceptual Model → fa_leanix_dat_enterprise_conceptual_model_* collections
  2. LeanIX Global Inventory → fa_leanix_global_inventory_* collections
  3. FA Handbook → fa_handbook collection

Usage:
    # Full consolidation
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog-v2

    # Domain-scoped run
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog-v2 \\
        --domain PARTY

    # Single entity (for debugging/iteration)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog-v2 \\
        --domain PARTY --entity "Player"

    # Skip handbook (faster, LeanIX only)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog-v2 \\
        --domain PARTY --skip-handbook

    # Skip relationships (faster, ~30-45 min)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog-v2 \\
        --domain PARTY --skip-relationships
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from elt_llm_core.config import RagConfig
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

# ---------------------------------------------------------------------------
# Data Classes — Structured Results
# ---------------------------------------------------------------------------


@dataclass
class EntityRecord:
    """A consolidated entity record for the catalog."""
    fact_sheet_id: str
    entity_name: str
    domain: str
    subgroup: str
    hierarchy_level: str
    source: str  # LEANIX_ONLY, BOTH, HANDBOOK_ONLY
    leanix_description: str = ""
    formal_definition: str = ""
    domain_context: str = ""
    governance_rules: str = ""
    handbook_term: str | None = None
    mapping_confidence: str = ""
    mapping_rationale: str = ""
    review_status: str = "PENDING"
    review_notes: str = ""
    relationships: list[dict] = field(default_factory=list)


@dataclass
class HandbookTerm:
    """A defined term extracted from the FA Handbook."""
    term: str
    definition: str
    definition_source: str


@dataclass
class TermMapping:
    """Mapping from a handbook term to a conceptual model entity."""
    term: str
    mapped_entity: str
    domain: str
    fact_sheet_id: str
    mapping_confidence: str
    mapping_rationale: str


# ---------------------------------------------------------------------------
# DETERMINISTIC EXTRACTORS
# These use structured parsing for completeness and reproducibility.
# ---------------------------------------------------------------------------

_DEF_MARKER = "**FA Handbook defined term**"
_DEF_LINE_PAT = re.compile(
    r"\*\*FA Handbook defined term\*\* \[source: (\w+)\]: (.+?) means (.+)",
)

_ARTIFACT_TERM_FRAGMENTS = (
    "CONTENTS PAGE",
    "DEFINITION INTERPRETATION",
)


def _is_artifact_term(term: str) -> bool:
    """Return True if the term is a PDF navigation or header artifact."""
    if any(frag in term for frag in _ARTIFACT_TERM_FRAGMENTS):
        return True
    if term.endswith(" -"):
        return True
    return False


def _normalize(name: str) -> str:
    """Normalize entity/term name for matching."""
    return " ".join(name.lower().split())


def extract_handbook_terms_from_docstore(rag_config: RagConfig) -> list[HandbookTerm]:
    """Extract defined terms from fa_handbook docstore (deterministic).
    
    Uses definition markers produced during ingestion.
    This is a DETERMINISTIC extractor — structured format, exact match.
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
    
    terms: list[HandbookTerm] = []
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
            
            if _is_artifact_term(term):
                continue
            
            defn = m.group(3).strip().rstrip(".")
            key = term.lower()
            if key in seen:
                continue
            seen.add(key)
            terms.append(HandbookTerm(term=term, definition=defn, definition_source=source))
    
    terms.sort(key=lambda x: x.term.lower())
    print(f"  {len(terms)} unique defined terms extracted from docstore")
    return terms


def extract_entities_from_conceptual_model(
    rag_config: RagConfig,
    model_collections: list[str],
) -> list[dict]:
    """Extract all entities from conceptual model docstores (deterministic).
    
    Scans fa_leanix_dat_enterprise_conceptual_model_* docstores.
    This is a DETERMINISTIC extractor — completeness is critical.
    """
    from llama_index.core import StorageContext
    
    entities: list[dict] = []
    seen: set[str] = set()
    
    print(f"  Scanning {len(model_collections)} conceptual model collections…")
    
    _ENTITY_LINE_PAT = re.compile(
        r"^(?:- )?\*\*([^*]+)\*\*(?:\s+\*\(LeanIX ID: `([^`]*)`\)\*)?$"
    )
    _SUBGROUP_HEADING_PAT = re.compile(r"^## (.+?) Subgroup$")
    _ENTITY_GROUP_PAT = re.compile(
        r"^\*\*([^(]+?)\s*\(\d+\s+entities\):\*\*\s+(.+)"
    )
    _CATEGORY_DOMAIN: dict[str, str] = {
        "Party Types": "PARTY",
        "Channel Types": "CHANNEL",
        "Account Types": "ACCOUNTS",
        "Asset Types": "ASSETS",
        "Other Entities": "ADDITIONAL",
    }
    
    for coll_name in model_collections:
        docstore_path = get_docstore_path(rag_config.chroma, coll_name)
        if not docstore_path.exists():
            continue
        
        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = sorted(
            storage.docstore.docs.values(),
            key=lambda n: getattr(n, "start_char_idx", 0) or 0,
        )
        
        domain = coll_name.replace(
            "fa_leanix_dat_enterprise_conceptual_model_", ""
        ).upper()
        
        current_subgroup = ""
        for node in nodes:
            text = getattr(node, "text", "") or ""
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                
                m = _SUBGROUP_HEADING_PAT.match(line)
                if m:
                    current_subgroup = m.group(1).strip()
                    continue
                
                if line.startswith("## ") and not _SUBGROUP_HEADING_PAT.match(line):
                    current_subgroup = ""
                    continue
                
                m = _ENTITY_LINE_PAT.match(line)
                if m:
                    name = m.group(1).strip()
                    fsid = (m.group(2) or "").strip()
                    if not name or len(name) > 100:
                        continue
                    key = name.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    entities.append({
                        "entity_name": name,
                        "domain": domain,
                        "fact_sheet_id": fsid,
                        "hierarchy_level": "",
                        "subgroup": current_subgroup,
                    })
                    continue
                
                m = _ENTITY_GROUP_PAT.match(line)
                if not m:
                    continue
                category = m.group(1).strip()
                entity_domain = _CATEGORY_DOMAIN.get(category, "PARTY")
                for ename in m.group(2).strip().rstrip(".").split(","):
                    ename = ename.strip().rstrip(".")
                    if not ename or len(ename) > 100:
                        continue
                    key = ename.lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    entities.append({
                        "entity_name": ename,
                        "domain": entity_domain,
                        "fact_sheet_id": "",
                        "hierarchy_level": "",
                    })
    
    print(f"  {len(entities)} unique entities extracted from conceptual model")
    return entities


def extract_relationships_from_conceptual_model(
    rag_config: RagConfig,
    model_collections: list[str],
) -> dict[str, list[dict]]:
    """Extract relationships from conceptual model docstores (deterministic).
    
    Scans fa_leanix_dat_enterprise_conceptual_model_relationships collection.
    This is a DETERMINISTIC extractor — explicit structure in source.
    """
    from llama_index.core import StorageContext
    
    relationships: dict[str, list[dict]] = {}
    
    rel_collections = [c for c in model_collections if 'relationship' in c.lower()]
    if not rel_collections:
        rel_collections = model_collections
    
    print(f"  Scanning {len(rel_collections)} collections for relationships…")
    
    _REL_LINE_PAT = re.compile(
        r"^(?:- )?\*\*([^*]+)\*\*\s+(.+?)\s+\*\*([^*]+)\*\*\.?$"
    )
    
    for coll_name in rel_collections:
        docstore_path = get_docstore_path(rag_config.chroma, coll_name)
        if not docstore_path.exists():
            continue
        
        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = list(storage.docstore.docs.values())
        
        for node in nodes:
            text = getattr(node, "text", "") or ""
            for line in text.splitlines():
                line = line.strip()
                m = _REL_LINE_PAT.match(line)
                if not m:
                    continue
                source = m.group(1).strip()
                cardinality_desc = m.group(2).strip()
                target = m.group(3).strip()
                card_m = re.search(r'\(([^)]+)\)', cardinality_desc)
                cardinality = card_m.group(1) if card_m else ""
                relationships.setdefault(source.lower(), []).append({
                    "target_entity": target,
                    "relationship_type": "relates to",
                    "cardinality": cardinality,
                    "direction": "unidirectional",
                })
    
    rel_count = sum(len(v) for v in relationships.values())
    print(f"  {rel_count} relationships extracted from conceptual model")
    return relationships


# ---------------------------------------------------------------------------
# AI-NATIVE EXTRACTORS
# These use RAG+LLM for intelligence, inference, and synthesis.
# ---------------------------------------------------------------------------

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

_HANDBOOK_DEFINITION_PROMPT = """\
Find the formal definition of '{entity_name}' in the FA Handbook.

Instructions:
1. Search for an exact definition in the format "{entity_name} means..." or similar
2. If found, quote the exact definition verbatim
3. If no exact definition exists, state "Not explicitly defined in the FA Handbook"
4. Do NOT invent or paraphrase — only return what is explicitly stated

Return as JSON:
{{
  "formal_definition": "exact quote or 'Not explicitly defined in the FA Handbook'",
  "definition_source": "section/page reference if available, otherwise ''"
}}"""

_HANDBOOK_CONTEXT_PROMPT = """\
Provide a terms of reference entry for the FA entity '{entity_name}' in the {domain} domain.

Structure your response with these three sections:

FORMAL_DEFINITION:
[What is this entity? Provide a formal definition. Quote exact FA Handbook definition if one exists.
If no exact definition exists, state "Not explicitly defined in the FA Handbook".]

DOMAIN_CONTEXT:
[What role does it play within the {domain} domain? What related concepts should be considered?
Be specific about relationships to other entities in the domain.]

GOVERNANCE:
[What specific FA Handbook rules, obligations, or regulatory requirements apply to this entity?
Cite section and rule numbers where possible (e.g. Rule A3.1, Section C).
Search for: eligibility criteria, registration requirements, compliance obligations, restrictions.
If no handbook rules apply, state "Not documented in FA Handbook — outside governance scope".]
"""

_GOVERNANCE_EXTRACTION_PROMPT = """\
Find all FA Handbook rules, regulations, and governance requirements that apply to '{entity_name}'.

Search for:
- Registration or affiliation requirements
- Eligibility criteria
- Compliance obligations
- Restrictions or prohibitions
- Reporting requirements
- Disciplinary provisions

Cite specific section numbers, rule numbers, and page references where possible.

Return as JSON array:
[
  {{
    "rule_type": "registration | eligibility | compliance | restriction | reporting | disciplinary",
    "citation": "Section X, Rule Y or page reference",
    "requirement": "summary of the requirement"
  }}
]

If no governance rules are found, return an empty array []."""


def map_handbook_term_to_entity(
    term: str,
    definition: str,
    model_collections: list[str],
    rag_config: RagConfig,
) -> TermMapping:
    """Map a Handbook defined term to a conceptual model entity via RAG (AI-native)."""
    query = _HANDBOOK_TERM_MAPPING_PROMPT.format(term=term, definition=definition)
    
    try:
        result = query_collections(model_collections, query, rag_config)
        response = result.response.strip()
        
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return TermMapping(
                term=term,
                mapped_entity=data.get("mapped_entity", "Not mapped"),
                domain=data.get("domain", ""),
                fact_sheet_id=data.get("fact_sheet_id", ""),
                mapping_confidence=data.get("mapping_confidence", "low"),
                mapping_rationale=data.get("mapping_rationale", ""),
            )
    except Exception:
        pass
    
    return TermMapping(
        term=term,
        mapped_entity="Not mapped",
        domain="",
        fact_sheet_id="",
        mapping_confidence="low",
        mapping_rationale="",
    )


def get_formal_definition_via_rag(
    entity_name: str,
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> tuple[str, str]:
    """Get formal definition via RAG+LLM (AI-native, primary approach).
    
    Returns:
        (formal_definition, definition_source)
    """
    query = _HANDBOOK_DEFINITION_PROMPT.format(entity_name=entity_name)
    
    try:
        result = query_collections(handbook_collections, query, rag_config)
        response = result.response.strip()
        
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return (
                data.get("formal_definition", ""),
                data.get("definition_source", ""),
            )
    except Exception:
        pass
    
    return ("", "")


def get_handbook_context_via_rag(
    entity_name: str,
    domain: str,
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> dict[str, str]:
    """Get handbook context (definition, domain context, governance) via RAG (AI-native)."""
    query = _HANDBOOK_CONTEXT_PROMPT.format(entity_name=entity_name, domain=domain)
    
    try:
        result = query_collections(handbook_collections, query, rag_config)
        response = result.response.strip()
        
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


def extract_governance_rules_via_rag(
    entity_name: str,
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> list[dict]:
    """Extract governance rules via targeted RAG query (AI-native)."""
    query = _GOVERNANCE_EXTRACTION_PROMPT.format(entity_name=entity_name)
    
    try:
        result = query_collections(handbook_collections, query, rag_config)
        response = result.response.strip()
        
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception:
        pass
    
    return []


def get_inventory_description_for_entity(
    entity_name: str,
    inventory_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Get inventory description for an entity via RAG (AI-native)."""
    if not inventory_collections:
        return {"description": "Not documented", "level": "", "status": "", "system_name": ""}
    
    query = f"Find the LeanIX inventory description for '{entity_name}'. Provide description, level, status."
    
    try:
        result = query_collections(inventory_collections, query, rag_config)
        response = result.response.strip()
        
        return {
            "description": response[:500] if response else "Not documented",
            "level": "",
            "status": "",
            "system_name": "",
        }
    except Exception as e:
        return {"description": f"[Error: {e}]", "level": "", "status": "", "system_name": ""}


# ---------------------------------------------------------------------------
# FALLBACK: Deterministic lookup when RAG fails
# ---------------------------------------------------------------------------


def lookup_definition_in_terms(
    entity_name: str,
    handbook_terms: list[HandbookTerm],
    handbook_mappings: dict[str, TermMapping],
) -> str | None:
    """Look up definition from pre-extracted terms (deterministic fallback).
    
    Strategy:
    1. Try direct match on entity name
    2. Try mapped handbook term
    """
    name_norm = _normalize(entity_name)
    
    # Try direct match
    for term in handbook_terms:
        if _normalize(term.term) == name_norm:
            return term.definition
    
    # Try via mapped term
    mapping = handbook_mappings.get(name_norm)
    if mapping:
        for term in handbook_terms:
            if _normalize(term.term) == _normalize(mapping.term):
                return term.definition
    
    return None


# ---------------------------------------------------------------------------
# Consolidation
# ---------------------------------------------------------------------------


def consolidate_catalog(
    conceptual_entities: list[dict],
    handbook_terms: list[HandbookTerm],
    handbook_mappings: dict[str, TermMapping],
    inventory_descriptions: dict[str, dict],
    handbook_context: dict[str, dict],
    relationships: dict[str, list[dict]],
) -> tuple[list[EntityRecord], list[dict]]:
    """Merge conceptual model + Handbook entities into unified catalog."""
    consolidated: list[EntityRecord] = []
    seen_names: set[str] = set()
    
    print("\n=== Consolidating Entities ===")
    
    # Build reverse mapping: normalized entity name → TermMapping
    entity_to_mapping: dict[str, TermMapping] = {}
    for mapping in handbook_mappings.values():
        mapped_entity = _normalize(mapping.mapped_entity)
        if mapped_entity and mapped_entity not in ("not mapped", "none"):
            entity_to_mapping[mapped_entity] = mapping
    
    # Term lookup: normalized name → HandbookTerm
    terms_by_name: dict[str, HandbookTerm] = {
        _normalize(t.term): t for t in handbook_terms
    }
    
    for entity in conceptual_entities:
        name = entity.get("entity_name", "")
        name_norm = _normalize(name)
        fsid = entity.get("fact_sheet_id", "")
        domain = entity.get("domain", "UNKNOWN")
        
        seen_names.add(name_norm)
        
        # Determine source
        mapping = entity_to_mapping.get(name_norm)
        if mapping:
            source = "BOTH"
            handbook_term_name = mapping.term
        else:
            source = "LEANIX_ONLY"
            handbook_term_name = None
        
        # Get inventory description
        inv = inventory_descriptions.get(name_norm, {})
        leanix_description = inv.get("description", "Not documented")
        
        # Get handbook context
        hb_context = handbook_context.get(name_norm, {})
        
        # Fallback: try direct term lookup if RAG didn't find definition
        formal_def = hb_context.get("formal_definition", "")
        if not formal_def or "not explicitly defined" in formal_def.lower():
            fallback_def = lookup_definition_in_terms(name, handbook_terms, handbook_mappings)
            if fallback_def:
                formal_def = fallback_def
        
        # Get relationships
        entity_rels = relationships.get(name_norm, [])
        
        record = EntityRecord(
            fact_sheet_id=fsid,
            entity_name=name,
            domain=domain,
            subgroup=entity.get("subgroup", ""),
            hierarchy_level=entity.get("hierarchy_level", ""),
            source=source,
            leanix_description=leanix_description,
            formal_definition=formal_def,
            domain_context=hb_context.get("domain_context", ""),
            governance_rules=hb_context.get("governance_rules", ""),
            handbook_term=handbook_term_name,
            mapping_confidence=mapping.mapping_confidence if mapping else "",
            mapping_rationale=mapping.mapping_rationale if mapping else "",
            review_status="PENDING",
            review_notes="",
            relationships=entity_rels,
        )
        
        consolidated.append(record)
    
    print(f"  Conceptual model entities: {len(conceptual_entities)}")
    print(f"  Total consolidated: {len(consolidated)}")
    
    # Build consolidated relationships
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
# Main Generation
# ---------------------------------------------------------------------------


def generate_consolidated_catalog_v2(
    rag_config: RagConfig,
    model_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    output_dir: Path,
    skip_relationships: bool,
    domain_filter: str | None = None,
    entity_filter: str | None = None,
    skip_handbook: bool = False,
) -> None:
    """Generate consolidated catalog via RAG+LLM queries (v2 AI-native)."""
    
    if domain_filter:
        domain_filter = domain_filter.upper()
        suffix = f"_{domain_filter.lower()}"
        model_collections = [c for c in model_collections if c.endswith(suffix)]
        if not model_collections:
            print(f"\nERROR: No collection found for domain '{domain_filter}'.", file=sys.stderr)
            print(f"  Expected a collection ending with '{suffix}'.", file=sys.stderr)
            sys.exit(1)
        catalog_json_path = output_dir / f"fa_consolidated_catalog_{domain_filter.lower()}_v2.json"
        relationships_json_path = output_dir / f"fa_consolidated_relationships_{domain_filter.lower()}_v2.json"
        print(f"\n  Domain filter: {domain_filter} ({len(model_collections)} collection(s))")
    else:
        catalog_json_path = output_dir / "fa_consolidated_catalog_v2.json"
        relationships_json_path = output_dir / "fa_consolidated_relationships_v2.json"
    
    if entity_filter:
        print(f"  Entity filter: {entity_filter}")
    
    print("\n=== FA Consolidated Catalog v2 (AI-Native) ===")
    print(f"  Model: {rag_config.ollama.llm_model}")
    print(f"  Collections:")
    print(f"    - Conceptual Model ({len(model_collections)})")
    print(f"    - Inventory ({len(inventory_collections)})")
    print(f"    - Handbook ({len(handbook_collections)})")
    
    # Step 1: Extract entities from conceptual model (DETERMINISTIC)
    print("\n=== Step 1: Extract Conceptual Model Entities ===")
    conceptual_entities = extract_entities_from_conceptual_model(rag_config, model_collections)
    
    if domain_filter:
        conceptual_entities = [
            e for e in conceptual_entities
            if e.get("domain", "").upper() == domain_filter
        ]
        print(f"  After domain filter ({domain_filter}): {len(conceptual_entities)} entities")
    
    if entity_filter:
        conceptual_entities = [
            e for e in conceptual_entities
            if _normalize(e.get("entity_name", "")) == _normalize(entity_filter)
        ]
        if not conceptual_entities:
            print(f"\nERROR: Entity '{entity_filter}' not found in domain '{domain_filter}'.", file=sys.stderr)
            sys.exit(1)
        print(f"  After entity filter: {len(conceptual_entities)} entity")
    
    # Step 2: Get inventory descriptions via RAG (AI-NATIVE)
    print("\n=== Step 2: Extract Inventory Descriptions ===")
    inventory_descriptions: dict[str, dict] = {}
    total = len(conceptual_entities)
    for i, entity in enumerate(conceptual_entities, 1):
        name = entity.get("entity_name", "")
        print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)
        inv = get_inventory_description_for_entity(name, inventory_collections, rag_config)
        inventory_descriptions[_normalize(name)] = inv
    print(f"  {len(inventory_descriptions)} inventory descriptions extracted      ")
    
    # Step 3: Extract Handbook defined terms from docstore (DETERMINISTIC)
    print("\n=== Step 3: Extract Handbook Defined Terms ===")
    if skip_handbook:
        print("  Skipping (--skip-handbook)")
        handbook_terms: list[HandbookTerm] = []
    else:
        handbook_terms = extract_handbook_terms_from_docstore(rag_config)
    
    # Step 4: Map Handbook terms to conceptual model entities via RAG (AI-NATIVE)
    print("\n=== Step 4: Map Handbook Terms to Conceptual Model ===")
    handbook_mappings: dict[str, TermMapping] = {}
    if skip_handbook:
        print("  Skipping (--skip-handbook)")
    else:
        total = len(handbook_terms)
        for i, term_entry in enumerate(handbook_terms, 1):
            term = term_entry.term
            definition = term_entry.definition
            print(f"  [{i:>3}/{total}] {term[:50]:<50}", end="\r", flush=True)
            mapping = map_handbook_term_to_entity(term, definition, model_collections, rag_config)
            handbook_mappings[_normalize(term)] = mapping
        print(f"  {len(handbook_mappings)} handbook terms mapped                              ")
    
    # Step 5: Get handbook context for all entities via RAG (AI-NATIVE)
    print("\n=== Step 5: Extract Handbook Context (RAG+LLM) ===")
    handbook_context: dict[str, dict] = {}
    if skip_handbook:
        print("  Skipping (--skip-handbook)")
    else:
        total = len(conceptual_entities)
        for i, entity in enumerate(conceptual_entities, 1):
            name = entity.get("entity_name", "")
            domain = entity.get("domain", "UNKNOWN")
            name_norm = _normalize(name)
            print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)
            
            # Primary: RAG query for full context
            context = get_handbook_context_via_rag(name, domain, handbook_collections, rag_config)
            
            # Enhancement: If governance is empty, try targeted extraction
            if not context.get("governance_rules"):
                gov_rules = extract_governance_rules_via_rag(name, handbook_collections, rag_config)
                if gov_rules:
                    context["governance_rules"] = json.dumps(gov_rules, indent=2)
            
            handbook_context[name_norm] = context
        print(f"  {len(handbook_context)} entities enriched with Handbook context      ")
    
    # Step 6: Extract relationships from conceptual model (DETERMINISTIC)
    print("\n=== Step 6: Extract Relationships ===")
    relationships: dict[str, list[dict]] = {}
    
    if skip_relationships:
        print("  Skipping relationship extraction (--skip-relationships)")
    else:
        relationships = extract_relationships_from_conceptual_model(rag_config, model_collections)
    
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
    
    # Write JSON outputs
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump([e.__dict__ for e in consolidated_entities], f, indent=2, ensure_ascii=False)
    
    with open(relationships_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_relationships, f, indent=2, ensure_ascii=False)
    
    print(f"\n  Consolidated catalog (JSON) → {catalog_json_path}")
    print(f"  Consolidated relationships → {relationships_json_path}")
    
    # Summary
    source_counts: dict[str, int] = {}
    for e in consolidated_entities:
        src = e.source
        source_counts[src] = source_counts.get(src, 0) + 1
    
    print("\n=== Summary by Source ===")
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")
    
    status_counts: dict[str, int] = {}
    for e in consolidated_entities:
        status = e.review_status
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("\n=== Summary by Review Status ===")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    
    # Quality metrics
    print("\n=== Quality Metrics ===")
    with_definitions = sum(1 for e in consolidated_entities if e.formal_definition)
    with_governance = sum(1 for e in consolidated_entities if e.governance_rules)
    print(f"  Entities with formal definitions: {with_definitions}/{len(consolidated_entities)}")
    print(f"  Entities with governance rules: {with_governance}/{len(consolidated_entities)}")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FA Consolidated Catalog Generator v2 (AI-Native)"
    )
    parser.add_argument(
        "--rag-config",
        type=Path,
        default=_DEFAULT_RAG_CONFIG,
        help="Path to RAG config YAML",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=_DEFAULT_OUTPUT_DIR,
        help="Output directory for JSON files",
    )
    parser.add_argument(
        "--domain",
        type=str,
        help="Filter to specific domain (e.g., PARTY, AGREEMENT)",
    )
    parser.add_argument(
        "--entity",
        type=str,
        help="Filter to specific entity name (for debugging/iteration)",
    )
    parser.add_argument(
        "--skip-relationships",
        action="store_true",
        help="Skip relationship extraction (faster run)",
    )
    parser.add_argument(
        "--skip-handbook",
        action="store_true",
        help="Skip handbook term extraction and context enrichment",
    )
    parser.add_argument(
        "--model",
        type=str,
        help="Override LLM model from RAG config",
    )
    
    args = parser.parse_args()
    
    # Load RAG config
    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.rag_config)
    if args.model:
        rag_config.ollama.llm_model = args.model
    print(f"  LLM: {rag_config.ollama.llm_model}")
    print(f"  num_queries: {rag_config.query.num_queries}")
    
    # Resolve collections
    print("\nResolving collections…")
    model_collections = resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    inventory_collections = resolve_collection_prefixes(
        ["fa_leanix_global_inventory"], rag_config
    )
    handbook_collections = ["fa_handbook"]
    
    print(f"  Conceptual Model ({len(model_collections)})")
    print(f"  Inventory ({len(inventory_collections)})")
    print(f"  Handbook: {'fa_handbook' if handbook_collections else 'NOT FOUND'}")
    
    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate catalog
    generate_consolidated_catalog_v2(
        rag_config=rag_config,
        model_collections=model_collections,
        inventory_collections=inventory_collections,
        handbook_collections=handbook_collections,
        output_dir=args.output_dir,
        skip_relationships=args.skip_relationships,
        domain_filter=args.domain,
        entity_filter=args.entity,
        skip_handbook=args.skip_handbook,
    )
    
    print("\n=== Complete ===")
    print(f"  Consolidated catalog (JSON) → {args.output_dir / 'fa_consolidated_catalog_v2.json'}")
    print(f"  Consolidated relationships → {args.output_dir / 'fa_consolidated_relationships_v2.json'}")
    print("\nNext steps:")
    print("  1. Review fa_consolidated_catalog_v2.json with Data Architects")
    print("  2. Update review_status fields (APPROVED/REJECTED/NEEDS_CLARIFICATION)")
    print("  3. Import to Purview or downstream systems")


if __name__ == "__main__":
    main()
