"""FA Consolidated Catalog generator.

RAG+LLM implementation using elt_llm_query infrastructure.
No direct source file parsing. No dependencies on other consumers.

Architecture:
  1. INGESTION (elt_llm_ingest)
     - FA Handbook PDF → fa_handbook collection
     - LeanIX XML → fa_leanix_dat_enterprise_conceptual_model_* collections
     - LeanIX Excel → fa_leanix_global_inventory_* collections
     Output: ChromaDB collections + DocStores

  2. CONSUMER (this script)
     - Resolves collections via RAG profiles or direct prefixes
     - Queries via query_collections() → LLM+RAG synthesis
     - Consolidates responses → JSON for stakeholder review

Strategy:
  - Use RAG for synthesis/enrichment (Handbook context, term mapping)
  - Use docstore scan for structured metadata (entities, relationships)
  - Balance scalability with quality

Prerequisites (via ingestion only):
  1. LeanIX Conceptual Model → fa_leanix_dat_enterprise_conceptual_model_* collections
  2. LeanIX Global Inventory → fa_leanix_global_inventory_* collections
  3. FA Handbook → fa_handbook collection

Outputs (~/.tmp/elt_llm_consumer/ or project .tmp/):
  fa_consolidated_catalog.json      ← Merged catalog with all 7 requirements
  fa_consolidated_relationships.json ← Relationships with source attribution

Usage:
    # Full consolidation
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

    # With specific model override
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --model qwen2.5:14b

    # Skip relationship extraction (faster, ~5 min)
    uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog \\
        --skip-relationships

Available models:
    qwen2.5:14b (default), mistral-nemo:12b, llama3.1:8b,
    granite3.1-dense:8b, michaelborck/refuled

Runtime:
  - Full run: ~3-4 hr (num_queries=3) / ~45-60 min (num_queries=1)
  - Skip relationships: ~2-3 hr (num_queries=3) / ~30-45 min (num_queries=1)
"""
from __future__ import annotations

import argparse
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

_HANDBOOK_CONTEXT_PROMPT = """\
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

_ENTITY_RELATIONSHIP_PROMPT = """\
You are analysing the FA (The Football Association) Handbook to identify \
entity-to-entity relationships.

Source domain: {source_domain}
Source entities (sample): {source_entities}

Target domain: {target_domain}
Target entities (sample): {target_entities}

Domain-level relationship: {source_domain} {domain_cardinality} {target_domain}

Task: Identify all specific entity-to-entity relationships between the source \
and target entity lists as described in the FA Handbook. For every relationship \
found, return BOTH the forward and inverse directions as separate records.

Return a JSON array. Each item must have exactly these fields:
- source_entity:         name of the source entity (must be from source entities list)
- source_domain:         source domain name
- target_entity:         name of the target entity (must be from target entities list)
- target_domain:         target domain name
- relationship:          verb phrase for the forward direction (e.g. "is registered with")
- inverse_relationship:  verb phrase for the inverse direction (e.g. "has registered players")
- cardinality:           forward cardinality — one of: "1:1", "1:many", "many:1", "many:many"
- inverse_cardinality:   inverse cardinality — one of: "1:1", "1:many", "many:1", "many:many"
- inferred:              true if inferred from context, false if explicitly stated
- evidence:              brief quote or paraphrase from the Handbook (max 30 words)

Rules:
- Only include relationships supported by the FA Handbook content.
- Do not invent relationships. If none are found, return [].
- Both the forward and inverse record must reference each other via \
  inverse_relationship / relationship fields.

Return only the JSON array, no other text."""

_DOMAIN_INFERENCE_PROMPT = """\
You are classifying a business entity into the FA (The Football Association) \
data architecture taxonomy.

The current known domains and subgroups are:
{taxonomy_context}

Entity name: {entity_name}
FA Handbook definition: {handbook_definition}

Follow this DECISION PROCESS in priority order:

TIER 1 — Map to existing taxonomy (strongly preferred):
  If the entity clearly belongs to an existing domain/subgroup, assign it there.
  Set inference_tier: "existing"

TIER 2 — Propose new taxonomy:
  If the entity does not fit any existing domain/subgroup, but the entity context
  provides enough information to propose a meaningful new Domain and/or Subgroup,
  propose sensible names that follow the same naming conventions as the existing taxonomy.
  Set inference_tier: "new_proposed"
  Note: prefer this over Tier 3 whenever possible.

TIER 3 — Unknown (last resort):
  Only if there is genuinely insufficient context to classify the entity.
  Set inference_tier: "unknown"

Return a JSON object with exactly these fields:
- entity_domain:       domain name (existing, proposed new name, or "unknown")
- entity_subgroup:     subgroup name (existing, proposed new name, "" if none, or "unknown")
- inference_tier:      "existing" | "new_proposed" | "unknown"
- inference_confidence: "high" | "medium" | "low"
  - high:   clear semantic match, only one plausible option
  - medium: plausible but two or more options could apply
  - low:    genuinely ambiguous
- inference_reasoning: one or two sentences explaining the assignment
- alternative_domain:  next most likely domain if confidence is not "high", else ""

For Tier 1, use domain and subgroup names EXACTLY as listed in the taxonomy.
For Tier 2, follow the same Title Case naming conventions as existing entries.
Return only the JSON object, no other text."""

# ---------------------------------------------------------------------------
# Definition marker extraction from docstore
# ---------------------------------------------------------------------------

_DEF_MARKER = "**FA Handbook defined term**"
_DEF_LINE_PAT = re.compile(
    r"\*\*FA Handbook defined term\*\* \[source: (\w+)\]: (.+?) means (.+)",
)

# Matches entity list lines from doc_leanix_parser domain sections:
#   - **Club** *(LeanIX ID: `abc123-uuid`)*
#   - **Club**   (no ID variant)
_ENTITY_LINE_PAT = re.compile(
    r"^- \*\*([^*]+)\*\*(?:\s+\*\(LeanIX ID: `([^`]*)`\)\*)?$"
)

# Matches relationship lines from doc_leanix_parser.
# Domain sections write:     - **PARTY** relates to (cardinality) **ACCOUNTS**
# Relationships collection:    **PARTY** relates to (cardinality) **ACCOUNTS**.
# Pattern handles both: optional leading '- ' and optional trailing '.'
_REL_LINE_PAT = re.compile(
    r"^(?:- )?\*\*([^*]+)\*\*\s+(.+?)\s+\*\*([^*]+)\*\*\.?$"
)

# Matches subgroup heading lines emitted by to_section_files() after Enhancement 1b:
#   ## Individual Subgroup
_SUBGROUP_HEADING_PAT = re.compile(r"^## (.+?) Subgroup$")

# Matches paragraph-format entity group lines in the additional_entities collection:
#   **Party Types (28 entities):** Club, Player, Individual, …
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


def extract_handbook_terms_from_docstore(rag_config: RagConfig) -> list[dict]:
    """Extract defined terms from fa_handbook docstore.

    Uses definition markers produced by RegulatoryPDFPreprocessor during ingestion.
    This queries the already-built index — NOT direct file parsing.
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
# Entity extraction from conceptual model docstores
# ---------------------------------------------------------------------------


def extract_entities_from_conceptual_model(
    rag_config: RagConfig,
    model_collections: list[str],
) -> list[dict]:
    """Extract all entities from conceptual model docstores.

    Scans fa_leanix_dat_enterprise_conceptual_model_* docstores.
    This queries the already-built index — NOT direct XML parsing.
    """
    from llama_index.core import StorageContext

    entities: list[dict] = []
    seen: set[str] = set()

    print(f"  Scanning {len(model_collections)} conceptual model collections…")

    for coll_name in model_collections:
        docstore_path = get_docstore_path(rag_config.chroma, coll_name)
        if not docstore_path.exists():
            continue

        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = list(storage.docstore.docs.values())

        domain = coll_name.replace(
            "fa_leanix_dat_enterprise_conceptual_model_", ""
        ).upper()

        for node in nodes:
            text = getattr(node, "text", "") or ""
            current_subgroup = ""  # reset per chunk — headings and entities co-locate in chunks
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue

                # Subgroup heading: ## Individual Subgroup
                m = _SUBGROUP_HEADING_PAT.match(line)
                if m:
                    current_subgroup = m.group(1).strip()
                    continue

                # Non-subgroup ## heading (e.g. ## PARTY Domain Relationships) — reset
                if line.startswith("## ") and not _SUBGROUP_HEADING_PAT.match(line):
                    current_subgroup = ""
                    continue

                # Bullet-list format: - **Entity Name** *(LeanIX ID: `uuid`)*
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

                # Paragraph format from additional_entities collection:
                # **Party Types (28 entities):** Club, Player, …
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


# ---------------------------------------------------------------------------
# Inventory description extraction via RAG
# ---------------------------------------------------------------------------


def get_inventory_description_for_entity(
    entity_name: str,
    inventory_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Get inventory description for an entity via RAG query."""
    if not inventory_collections:
        return {"description": "Not documented", "level": "", "status": "", "system_name": ""}

    query = f"Find the LeanIX inventory description for '{entity_name}'. Provide description, level, status."

    try:
        result = query_collections(inventory_collections, query, rag_config)
        response = result.response.strip()

        # Extract structured fields from response
        return {
            "description": response[:500] if response else "Not documented",
            "level": "",
            "status": "",
            "system_name": "",
        }
    except Exception as e:
        return {"description": f"[Error: {e}]", "level": "", "status": "", "system_name": ""}


# ---------------------------------------------------------------------------
# Handbook term mapping via RAG
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Handbook context enrichment via RAG
# ---------------------------------------------------------------------------


def get_handbook_context_for_entity(
    entity_name: str,
    domain: str,
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Get FA Handbook context (definition, governance, domain context) for an entity."""
    query = _HANDBOOK_CONTEXT_PROMPT.format(entity_name=entity_name, domain=domain)

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
# Relationship extraction from conceptual model docstores
# ---------------------------------------------------------------------------


def extract_relationships_from_conceptual_model(
    rag_config: RagConfig,
    model_collections: list[str],
) -> dict[str, list[dict]]:
    """Extract relationships from conceptual model docstores.

    Scans fa_leanix_dat_enterprise_conceptual_model_relationships collection.
    This queries the already-built index — NOT direct XML parsing.
    """
    from llama_index.core import StorageContext

    relationships: dict[str, list[dict]] = {}

    # Focus on relationships collection
    rel_collections = [c for c in model_collections if 'relationship' in c.lower()]
    if not rel_collections:
        rel_collections = model_collections  # Fall back to all collections

    print(f"  Scanning {len(rel_collections)} collections for relationships…")

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


def extract_entity_relationships_from_handbook(
    domain_relationships: dict[str, list[dict]],
    conceptual_entities: list[dict],
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> list[dict]:
    """Extract entity-to-entity relationships from FA Handbook via RAG.

    One query per unique domain pair (bounded by ~17 domain relationships).
    """
    domain_entities: dict[str, list[str]] = {}
    for e in conceptual_entities:
        d = e.get("domain", "").upper()
        domain_entities.setdefault(d, []).append(e["entity_name"])

    entity_relationships: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    for source_domain_lower, rels in domain_relationships.items():
        source_domain = source_domain_lower.upper()
        source_entities = domain_entities.get(source_domain, [])
        if not source_entities:
            continue

        for rel in rels:
            target_domain = rel.get("target_entity", "").upper()
            target_entities = domain_entities.get(target_domain, [])
            if not target_entities:
                continue

            pair_key = tuple(sorted([source_domain, target_domain]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            query = _ENTITY_RELATIONSHIP_PROMPT.format(
                source_domain=source_domain,
                source_entities=", ".join(source_entities[:20]),
                target_domain=target_domain,
                target_entities=", ".join(target_entities[:20]),
                domain_cardinality=rel.get("cardinality", "relates to"),
            )

            print(f"  Querying {source_domain} ↔ {target_domain}…", end="\r", flush=True)
            try:
                result = query_collections(handbook_collections, query, rag_config)
                response = result.response.strip()
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    records = json.loads(json_match.group())
                    entity_relationships.extend(records)
            except Exception as exc:
                print(f"  [warn] {source_domain}↔{target_domain}: {exc}")

    return entity_relationships


def build_taxonomy_context(conceptual_entities: list[dict]) -> str:
    """Build a JSON taxonomy string from known entities for use in inference prompts."""
    taxonomy: dict[str, dict[str, list[str]]] = {}
    for e in conceptual_entities:
        domain = e.get("domain", "")
        subgroup = e.get("subgroup", "")
        name = e.get("entity_name", "")
        if not domain:
            continue
        taxonomy.setdefault(domain, {})
        taxonomy[domain].setdefault(subgroup or "_entities", []).append(name)

    output: dict[str, dict[str, list[str]]] = {}
    for domain, subgroups in sorted(taxonomy.items()):
        output[domain] = {}
        for sg, entities in sorted(subgroups.items()):
            key = sg if sg != "_entities" else "entities"
            output[domain][key] = sorted(entities)[:10]

    return json.dumps(output, indent=2)


def infer_domain_for_handbook_entity(
    entity_name: str,
    handbook_definition: str,
    taxonomy_context: str,
    model_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Use LLM to infer domain and subgroup for a HANDBOOK_ONLY entity (three-tier)."""
    query = _DOMAIN_INFERENCE_PROMPT.format(
        taxonomy_context=taxonomy_context,
        entity_name=entity_name,
        handbook_definition=handbook_definition,
    )
    try:
        result = query_collections(model_collections, query, rag_config)
        response = result.response.strip()
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            tier = parsed.get("inference_tier", "unknown")
            confidence = parsed.get("inference_confidence", "low")
            if tier == "existing" and confidence == "high":
                parsed["review_status"] = "PENDING"
            elif tier == "new_proposed":
                parsed["review_status"] = "PROPOSED_NEW_TAXONOMY"
            else:
                parsed["review_status"] = "NEEDS_CLARIFICATION"
            return parsed
    except Exception:
        pass
    return {
        "entity_domain": "unknown",
        "entity_subgroup": "",
        "inference_tier": "unknown",
        "inference_confidence": "low",
        "inference_reasoning": "LLM inference failed",
        "alternative_domain": "",
        "review_status": "NEEDS_CLARIFICATION",
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
    model_collections: list[str],
    rag_config: RagConfig,
    skip_handbook_only: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Merge conceptual model + Handbook entities into unified catalog.

    Returns:
        consolidated_entities: List of merged entity records
        consolidated_relationships: List of relationship records with source attribution
    """
    consolidated: list[dict] = []
    seen_names: set[str] = set()

    print("\n=== Consolidating Entities ===")

    # Build reverse mapping: normalised entity name → (term_lower, mapping_dict)
    # handbook_mappings is keyed by term (e.g. "club") but we need to look up by
    # entity name (e.g. "Club") — a term "Competition Rules" may map to entity "Competition".
    entity_to_mapping: dict[str, tuple[str, dict]] = {}
    for term_lower, mapping in handbook_mappings.items():
        mapped_entity = _normalize(mapping.get("mapped_entity", ""))
        if mapped_entity and mapped_entity not in ("not mapped", "none"):
            entity_to_mapping[mapped_entity] = (term_lower, mapping)

    # Original casing lookup: term_lower → term string as extracted from Handbook
    term_casing: dict[str, str] = {
        t["term"].lower(): t["term"] for t in handbook_terms
    }

    # Step 1: Process all conceptual model entities
    for entity in conceptual_entities:
        name = entity.get("entity_name", "")
        name_norm = _normalize(name)
        fsid = entity.get("fact_sheet_id", "")
        domain = entity.get("domain", "UNKNOWN")

        seen_names.add(name_norm)

        # Determine source classification using reverse mapping
        term_match = entity_to_mapping.get(name_norm)
        if term_match:
            source = "BOTH"
            term_lower, mapped = term_match
            handbook_term_name: str | None = term_casing.get(term_lower, term_lower)
        else:
            source = "LEANIX_ONLY"
            mapped = {}
            handbook_term_name = None

        # Get inventory description
        inv = inventory_descriptions.get(name_norm, {})
        leanix_description = inv.get("description", "Not documented")

        # Get handbook context
        hb_context = handbook_context.get(name_norm, {})

        # Get relationships
        entity_rels = relationships.get(name_norm, [])

        record = {
            "fact_sheet_id": fsid,
            "entity_name": name,
            "domain": domain,
            "subgroup": entity.get("subgroup", ""),
            "hierarchy_level": entity.get("hierarchy_level", ""),
            "source": source,
            "leanix_description": leanix_description,
            "formal_definition": hb_context.get("formal_definition", ""),
            "domain_context": hb_context.get("domain_context", ""),
            "governance_rules": hb_context.get("governance_rules", ""),
            "handbook_term": handbook_term_name,
            "mapping_confidence": mapped.get("mapping_confidence", ""),
            "mapping_rationale": mapped.get("mapping_rationale", ""),
            "review_status": "PENDING",
            "review_notes": "",
            "relationships": entity_rels,
        }

        consolidated.append(record)

    # Step 2: Add HANDBOOK_ONLY entities (with LLM domain/subgroup inference)
    # Skipped for domain-scoped runs — full taxonomy context is required for inference.
    if skip_handbook_only:
        print("\n  Skipping HANDBOOK_ONLY inference (domain-scoped run)")
    taxonomy_context = build_taxonomy_context(conceptual_entities)
    handbook_only_count = 0
    for term_entry in ([] if skip_handbook_only else handbook_terms):
        term = term_entry["term"]
        term_norm = _normalize(term)

        if term_norm in seen_names:
            continue

        mapped = handbook_mappings.get(term.lower(), {})
        if mapped.get("mapped_entity", "").lower() not in ("not mapped", ""):
            continue

        handbook_only_count += 1
        print(
            f"  [handbook-only {handbook_only_count}] Inferring domain for '{term[:40]}'…",
            end="\r", flush=True,
        )

        # Get handbook context for this term
        hb_context = handbook_context.get(term_norm, {})

        inferred = infer_domain_for_handbook_entity(
            entity_name=term,
            handbook_definition=term_entry.get("definition", ""),
            taxonomy_context=taxonomy_context,
            model_collections=model_collections,
            rag_config=rag_config,
        )

        record = {
            "fact_sheet_id": "",
            "entity_name": term,
            "domain": inferred.get("entity_domain", "HANDBOOK_DISCOVERED"),
            "subgroup": inferred.get("entity_subgroup", ""),
            "hierarchy_level": "",
            "source": "HANDBOOK_ONLY",
            "leanix_description": "Not documented in LeanIX — candidate for conceptual model addition",
            "formal_definition": term_entry.get("definition", ""),
            "domain_context": hb_context.get("domain_context", ""),
            "governance_rules": hb_context.get("governance_rules", ""),
            "handbook_term": term,
            "mapping_confidence": "low",
            "mapping_rationale": "Discovered in Handbook but not mapped to conceptual model",
            "inferred": True,
            "inference_tier": inferred.get("inference_tier", "unknown"),
            "inference_confidence": inferred.get("inference_confidence", "low"),
            "inference_reasoning": inferred.get("inference_reasoning", ""),
            "alternative_domain": inferred.get("alternative_domain", ""),
            "review_status": inferred.get("review_status", "NEEDS_CLARIFICATION"),
            "review_notes": "Handbook term awaiting SME review for model inclusion",
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
# Main generation
# ---------------------------------------------------------------------------


def generate_consolidated_catalog(
    rag_config: RagConfig,
    model_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    output_dir: Path,
    skip_relationships: bool,
    domain_filter: str | None = None,
) -> None:
    """Generate consolidated catalog via RAG+LLM queries."""

    if domain_filter:
        domain_filter = domain_filter.upper()
        suffix = f"_{domain_filter.lower()}"
        model_collections = [c for c in model_collections if c.endswith(suffix)]
        if not model_collections:
            print(f"\nERROR: No collection found for domain '{domain_filter}'.", file=sys.stderr)
            print(f"  Expected a collection ending with '{suffix}'.", file=sys.stderr)
            sys.exit(1)
        catalog_json_path = output_dir / f"fa_consolidated_catalog_{domain_filter.lower()}.json"
        relationships_json_path = output_dir / f"fa_consolidated_relationships_{domain_filter.lower()}.json"
        print(f"\n  Domain filter: {domain_filter} ({len(model_collections)} collection(s))")
    else:
        catalog_json_path = output_dir / "fa_consolidated_catalog.json"
        relationships_json_path = output_dir / "fa_consolidated_relationships.json"

    print("\n=== FA Consolidated Catalog (RAG+LLM) ===")
    print(f"  Model: {rag_config.ollama.llm_model}")
    print(f"  Collections:")
    print(f"    - Conceptual Model ({len(model_collections)})")
    print(f"    - Inventory ({len(inventory_collections)})")
    print(f"    - Handbook ({len(handbook_collections)})")

    # Step 1: Extract entities from conceptual model docstores
    print("\n=== Step 1: Extract Conceptual Model Entities ===")
    conceptual_entities = extract_entities_from_conceptual_model(rag_config, model_collections)
    if domain_filter:
        conceptual_entities = [
            e for e in conceptual_entities
            if e.get("domain", "").upper() == domain_filter
        ]
        print(f"  After domain filter ({domain_filter}): {len(conceptual_entities)} entities")

    # Step 2: Get inventory descriptions via RAG
    print("\n=== Step 2: Extract Inventory Descriptions ===")
    inventory_descriptions: dict[str, dict] = {}
    total = len(conceptual_entities)
    for i, entity in enumerate(conceptual_entities, 1):
        name = entity.get("entity_name", "")
        print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)
        inv = get_inventory_description_for_entity(name, inventory_collections, rag_config)
        inventory_descriptions[_normalize(name)] = inv
    print(f"  {len(inventory_descriptions)} inventory descriptions extracted      ")

    # Step 3: Extract Handbook defined terms from docstore
    print("\n=== Step 3: Extract Handbook Defined Terms ===")
    handbook_terms = extract_handbook_terms_from_docstore(rag_config)

    # Step 4: Map Handbook terms to conceptual model entities via RAG
    print("\n=== Step 4: Map Handbook Terms to Conceptual Model ===")
    handbook_mappings: dict[str, dict] = {}
    total = len(handbook_terms)
    for i, term_entry in enumerate(handbook_terms, 1):
        term = term_entry["term"]
        definition = term_entry["definition"]
        print(f"  [{i:>3}/{total}] {term[:50]:<50}", end="\r", flush=True)
        mapping = map_handbook_term_to_entity(term, definition, model_collections, rag_config)
        handbook_mappings[term.lower()] = mapping
    print(f"  {len(handbook_mappings)} handbook terms mapped                              ")

    # Step 5: Get handbook context for all entities
    print("\n=== Step 5: Extract Handbook Context ===")
    handbook_context: dict[str, dict] = {}
    total = len(conceptual_entities)
    for i, entity in enumerate(conceptual_entities, 1):
        name = entity.get("entity_name", "")
        domain = entity.get("domain", "UNKNOWN")
        print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)
        context = get_handbook_context_for_entity(name, domain, handbook_collections, rag_config)
        handbook_context[_normalize(name)] = context
    print(f"  {len(handbook_context)} entities enriched with Handbook context      ")

    # Step 6: Extract relationships from conceptual model
    print("\n=== Step 6: Extract Relationships ===")
    relationships: dict[str, list[dict]] = {}

    if skip_relationships:
        print("  Skipping relationship extraction (--skip-relationships)")
    else:
        relationships = extract_relationships_from_conceptual_model(rag_config, model_collections)

    # Step 6b: Entity-to-entity relationships from Handbook
    print("\n=== Step 6b: Extract Entity-to-Entity Relationships from Handbook ===")
    entity_relationships: list[dict] = []
    if not skip_relationships and relationships:
        entity_relationships = extract_entity_relationships_from_handbook(
            domain_relationships=relationships,
            conceptual_entities=conceptual_entities,
            handbook_collections=handbook_collections,
            rag_config=rag_config,
        )
        entity_rel_path = output_dir / "fa_entity_relationships.json"
        with open(entity_rel_path, "w", encoding="utf-8") as f:
            json.dump(entity_relationships, f, indent=2, ensure_ascii=False)
        print(f"  {len(entity_relationships)} entity relationships → {entity_rel_path}")
    else:
        print("  Skipping (--skip-relationships or no domain relationships found)")

    # Step 7: Consolidate
    print("\n=== Step 7: Consolidating ===")
    consolidated_entities, consolidated_relationships = consolidate_catalog(
        conceptual_entities,
        handbook_terms,
        handbook_mappings,
        inventory_descriptions,
        handbook_context,
        relationships,
        model_collections=model_collections,
        rag_config=rag_config,
        skip_handbook_only=domain_filter is not None,
    )

    # Write JSON outputs
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_entities, f, indent=2, ensure_ascii=False)

    with open(relationships_json_path, "w", encoding="utf-8") as f:
        json.dump(consolidated_relationships, f, indent=2, ensure_ascii=False)

    print(f"\n  Consolidated catalog (JSON) → {catalog_json_path}")
    print(f"  Consolidated relationships → {relationships_json_path}")

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
            "Generate FA Consolidated Catalog via RAG+LLM queries — "
            "uses elt_llm_query infrastructure, no direct file parsing"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Models: qwen2.5:14b (default), mistral-nemo:12b, "
            "llama3.1:8b, granite3.1-dense:8b, michaelborck/refuled\n\n"
            "Output:  JSON for stakeholder review\n\n"
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
        help="Skip relationship extraction (saves a few seconds — relationships are domain-level only)",
    )
    parser.add_argument(
        "--num-queries", type=int, default=None,
        help="Override num_queries (1=fastest, 3=best recall; default: from rag_config.yaml)",
    )
    parser.add_argument(
        "--domain", default=None, metavar="DOMAIN",
        help=(
            "Restrict to a single domain (e.g. PARTY, AGREEMENTS). "
            "Filters to the matching collection, skips HANDBOOK_ONLY inference, "
            "and writes to fa_consolidated_catalog_{domain}.json."
        ),
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Full consolidation
    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    if args.model:
        rag_config.ollama.llm_model = args.model
        print(f"  Model override: {args.model}")

    if args.num_queries is not None:
        rag_config.query.num_queries = args.num_queries
        print(f"  num_queries override: {args.num_queries}")

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

    if not model_collections:
        print(
            "\nERROR: No conceptual model collections found.\n"
            "Run: uv run python -m elt_llm_ingest.runner ingest "
            "ingest_fa_leanix_dat_enterprise_conceptual_model",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Conceptual Model ({len(model_collections)})")
    print(f"  Inventory ({len(inventory_collections)})")
    print(f"  Handbook: fa_handbook")

    generate_consolidated_catalog(
        rag_config=rag_config,
        model_collections=model_collections,
        inventory_collections=inventory_collections,
        handbook_collections=handbook_collections,
        output_dir=output_dir,
        skip_relationships=args.skip_relationships,
        domain_filter=args.domain,
    )

    domain_suffix = f"_{args.domain.lower()}" if args.domain else ""
    print("\n=== Complete ===")
    print(f"  Consolidated catalog (JSON) → {output_dir / f'fa_consolidated_catalog{domain_suffix}.json'}")
    print(f"  Consolidated relationships  → {output_dir / f'fa_consolidated_relationships{domain_suffix}.json'}")
    print("\nNext steps:")
    print("  1. Review fa_consolidated_catalog.json with Data Architects")
    print("  2. Update review_status fields (APPROVED/REJECTED/NEEDS_CLARIFICATION)")
    print("  3. Import to Purview or downstream systems")


if __name__ == "__main__":
    main()
