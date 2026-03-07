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
  - Use model JSON (_model.json) for structured entity/relationship enumeration
  - Use RAG for synthesis/enrichment (Handbook context, term mapping)
  - Use docstore scan only for Handbook defined-term extraction (Step 3)

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
import re
import sys
from pathlib import Path

import yaml

from elt_llm_core.config import RagConfig
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import discover_relevant_sections, query_collections

# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"
_PROMPT_DIR = _CONFIG_DIR / "prompts"


def _load_prompt(filename: str, key: str = "prompt") -> str:
    """Load a prompt string from elt_llm_consumer/config/prompts/."""
    with open(_PROMPT_DIR / filename, encoding="utf-8") as f:
        return yaml.safe_load(f)[key]


def _load_catalog_config() -> dict:
    """Load fa_consolidated_catalog.yaml (entity lists, aliases, thresholds)."""
    with open(_CONFIG_DIR / "fa_consolidated_catalog.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


_catalog_cfg = _load_catalog_config()

# ---------------------------------------------------------------------------
# Entity alias map for Step 4 matching — loaded from config
# ---------------------------------------------------------------------------

_ENTITY_ALIASES: dict[str, list[str]] = _catalog_cfg["entity_aliases"]

# Entities with no handbook coverage — skip RAG calls to prevent hallucination
_NO_HANDBOOK_COVERAGE: frozenset[str] = frozenset(_catalog_cfg["no_handbook_coverage"])

# Entities present in the Handbook but without "X means Y" definitions —
# Step 3 regex never extracts them, so Step 4 can't match them.
# Force source=BOTH so Step 5 RAG queries still run for them.
_FORCED_HANDBOOK_ENTITIES: frozenset[str] = frozenset(
    _catalog_cfg.get("forced_handbook_entities", [])
)

# Section-based retrieval — loaded from handbook_sections block in config
_sections_cfg: dict = _catalog_cfg.get("handbook_sections", {})
_SECTION_PREFIX: str = _sections_cfg.get("section_prefix", "fa_handbook")
_SECTION_THRESHOLD: float = _sections_cfg.get("section_routing_threshold", 0.0)
_SECTION_TOP_N: int | None = _sections_cfg.get("section_routing_top_n", None)
_SECTION_BM25_TOP_K: int = _sections_cfg.get("section_bm25_top_k", 3)

# ---------------------------------------------------------------------------
# Default paths
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

_INGEST_CONFIG_MODEL = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/"
    "ingest_fa_leanix_dat_enterprise_conceptual_model.yaml"
).expanduser()

_INGEST_CONFIG_INVENTORY = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/"
    "ingest_fa_leanix_global_inventory.yaml"
).expanduser()


def _resolve_json_from_ingest_config(config_path: Path, suffix: str) -> Path:
    """Derive a JSON sidecar path from an ingest config's file_paths[0].

    Appends ``suffix`` to the stem of the source file, e.g.:
      source.xml  + "_model.json"      → source_model.json
      source.xlsx + "_inventory.json"  → source_inventory.json
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Ingest config not found: {config_path}\n"
            "Pass the JSON path explicitly via the CLI flag."
        )
    with open(config_path) as f:
        data = yaml.safe_load(f)
    src = Path(data["file_paths"][0]).expanduser()
    return src.parent / f"{src.stem}{suffix}"


_DEFAULT_MODEL_JSON = _resolve_json_from_ingest_config(_INGEST_CONFIG_MODEL, "_model.json")
_DEFAULT_INVENTORY_JSON = _resolve_json_from_ingest_config(_INGEST_CONFIG_INVENTORY, "_inventory.json")

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_HANDBOOK_CONTEXT_PROMPT    = _load_prompt("handbook_context.yaml")
_ENTITY_RELATIONSHIP_PROMPT = _load_prompt("entity_relationship.yaml")
_DOMAIN_INFERENCE_PROMPT    = _load_prompt("domain_inference.yaml")

# ---------------------------------------------------------------------------
# Definition extraction from docstore (pymupdf4llm output)
# ---------------------------------------------------------------------------

# Matches FA Handbook definition patterns as produced by pymupdf4llm:
#   **"Term"** means DEFINITION       (bold + quoted — most common)
#   "Term" means DEFINITION           (quoted only)
#   Term means DEFINITION             (plain — fallback)
_DEF_PAT = re.compile(
    r'\*{0,2}"?([A-Z][A-Za-z0-9\s/()\'\-]{1,60}?)"?\*{0,2}\s+means\s+(.+?)(?:\s*;)?\s*$',
    re.MULTILINE,
)
# Matches markdown table rows from the Definitions/Interpretation table:
#   |Term Name|means Definition text|
#   |Multi<br>Line Term|means Definition text|
_TABLE_DEF_PAT = re.compile(
    r'^\|([A-Z][A-Za-z0-9\s<>/"\'/()\-]{1,100}?)\|means\s+(.+?)\|?\s*$',
    re.MULTILINE,
)



def extract_handbook_terms_from_docstore(rag_config: RagConfig) -> list[dict]:
    """Extract defined terms from handbook section docstores.

    Scans all fa_handbook_sNN docstores (or the legacy monolithic fa_handbook
    docstore as fallback) for two patterns:
    - Plain text: 'TERM means DEFINITION' (inline definitions throughout the handbook)
    - Table rows: '|TERM|means DEFINITION|' (Definitions/Interpretation tables,
      including multi-line terms with <br> separators)
    """
    from llama_index.core import StorageContext
    from elt_llm_core.vector_store import create_chroma_client, list_collections_by_prefix
    import re as _re

    # Prefer section collections (fa_handbook_sNN); fall back to monolithic fa_handbook
    client = create_chroma_client(rag_config.chroma)
    section_pat = _re.compile(rf'^{_re.escape(_SECTION_PREFIX)}_s\d{{2}}$')
    all_cols = list_collections_by_prefix(client, _SECTION_PREFIX)
    section_collections = [c for c in all_cols if section_pat.match(c)]

    if section_collections:
        print(f"  Scanning {len(section_collections)} handbook section docstores for defined terms…")
        all_nodes = []
        for col in sorted(section_collections):
            ds_path = get_docstore_path(rag_config.chroma, col)
            if not ds_path.exists():
                continue
            storage = StorageContext.from_defaults(persist_dir=str(ds_path))
            all_nodes.extend(storage.docstore.docs.values())
        nodes = all_nodes
    else:
        # Legacy fallback: monolithic fa_handbook collection
        docstore_path = get_docstore_path(rag_config.chroma, "fa_handbook")
        if not docstore_path.exists():
            print(
                f"ERROR: No handbook docstores found (tried '{_SECTION_PREFIX}_sNN' and 'fa_handbook').\n"
                "Run: uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook",
                file=sys.stderr,
            )
            sys.exit(1)
        print(f"  Loading fa_handbook docstore (legacy): {docstore_path}")
        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = list(storage.docstore.docs.values())

    print(f"  {len(nodes)} nodes loaded from handbook docstore(s)")

    terms: list[dict] = []
    seen: set[str] = set()

    for node in nodes:
        text = getattr(node, "text", "") or ""
        for pat in (_DEF_PAT, _TABLE_DEF_PAT):
            for m in pat.finditer(text):
                # Normalise term and definition: collapse <br> tags and whitespace
                raw_term = re.sub(r"<br\s*/?>", " ", m.group(1))
                term = " ".join(raw_term.split())
                raw_defn = re.sub(r"<br\s*/?>", " ", m.group(2))
                defn = " ".join(raw_defn.split()).rstrip(";").rstrip(".")
                if len(defn) < 10 or len(defn) > 1500:
                    continue
                key = term.lower()
                if key in seen:
                    continue
                seen.add(key)
                terms.append({"term": term, "definition": defn})

    terms.sort(key=lambda x: x["term"].lower())
    print(f"  {len(terms)} unique defined terms extracted from docstore")
    return terms


# ---------------------------------------------------------------------------
# CSV loaders for conceptual model entities and relationships
# ---------------------------------------------------------------------------


def _load_model_json(json_path: Path) -> dict:
    """Load and parse the model JSON produced by LeanIXPreprocessor."""
    if not json_path.exists():
        print(
            f"ERROR: Model JSON not found at {json_path}.\n"
            "Run ingestion first: uv run python -m elt_llm_ingest.runner ingest "
            "ingest_fa_leanix_dat_enterprise_conceptual_model",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)


def load_entities_from_json(json_path: Path) -> list[dict]:
    """Load conceptual model entities from the pre-parsed model JSON.

    The JSON is produced by LeanIXPreprocessor (output_format='json_md') and
    written next to the source XML.  Each entity has: domain, domain_fact_sheet_id,
    subtype, subtype_fact_sheet_id, entity_name, fact_sheet_id, fact_sheet_type.
    """
    doc = _load_model_json(json_path)
    entities = [
        {
            "entity_name": e["entity_name"],
            "domain": e["domain"].upper(),
            "domain_fact_sheet_id": e.get("domain_fact_sheet_id", ""),
            "subgroup": e.get("subtype", ""),
            "subgroup_fact_sheet_id": e.get("subtype_fact_sheet_id", ""),
            "fact_sheet_id": e.get("fact_sheet_id", ""),
        }
        for e in doc.get("entities", [])
    ]
    print(f"  {len(entities)} entities loaded from {json_path.name}")
    return entities


def load_relationships_from_json(json_path: Path) -> dict[str, list[dict]]:
    """Load domain-level relationships from the pre-parsed model JSON."""
    doc = _load_model_json(json_path)
    relationships: dict[str, list[dict]] = {}
    for row in doc.get("relationships", []):
        source = row["source_entity"]
        relationships.setdefault(source.lower(), []).append({
            "target_entity": row["target_entity"],
            "relationship_type": row.get("relationship_type", "relates to"),
            "cardinality": row.get("cardinality", ""),
            "direction": "unidirectional",
        })
    rel_count = sum(len(v) for v in relationships.values())
    print(f"  {rel_count} relationships loaded from {json_path.name}")
    return relationships


# ---------------------------------------------------------------------------
# Inventory direct JSON lookup
# ---------------------------------------------------------------------------


def load_inventory_from_json(json_path: Path) -> dict[str, dict]:
    """Load LeanIX inventory from _inventory.json, keyed by fact_sheet_id.

    The JSON is produced by LeanIXInventoryPreprocessor during ingestion and
    written next to the source Excel.  Returns a dict for O(1) lookup:
        inventory[fact_sheet_id] → {id, type, name, description, level, status}
    """
    if not json_path.exists():
        print(
            f"WARNING: Inventory JSON not found at {json_path}.\n"
            "Run ingestion first: uv run python -m elt_llm_ingest.runner "
            "--cfg ingest_fa_leanix_global_inventory\n"
            "Inventory descriptions will be empty.",
            file=sys.stderr,
        )
        return {}
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    fact_sheets = data.get("fact_sheets", {})
    print(f"  {len(fact_sheets)} inventory fact sheets loaded from {json_path.name}")
    return fact_sheets


# ---------------------------------------------------------------------------
# Handbook context enrichment via RAG
# ---------------------------------------------------------------------------


def get_handbook_context_for_entity(
    entity_name: str,
    domain: str,
    handbook_collections: list[str],
    rag_config: RagConfig,
    term_definitions: dict[str, str] | None = None,
) -> dict:
    """Get FA Handbook context (definition, governance, domain context) for an entity.

    Args:
        entity_name:          Conceptual model entity name (drives the RAG query).
        domain:               Domain of the entity.
        handbook_collections: Handbook collection names for RAG.
        rag_config:           RAG configuration.
        term_definitions:     Pre-built dict of {term_lower: definition} from Step 3.
                              When the entity name exactly matches a handbook term,
                              its formal definition overrides the RAG-synthesised text.
    """
    query = _HANDBOOK_CONTEXT_PROMPT.format(entity_name=entity_name, domain=domain)

    try:
        result = query_collections(handbook_collections, query, rag_config, iterative=True)
        response = result.response.strip()

        _section_key_map = {
            "FORMAL_DEFINITION": "formal_definition",
            "DOMAIN_CONTEXT": "domain_context",
            "GOVERNANCE": "governance_rules",
        }
        sections = {}
        for prompt_key, output_key in _section_key_map.items():
            match = re.search(rf"{prompt_key}:\s*(.*?)(?=\n+[A-Z_]+:|\Z)", response, re.DOTALL)
            sections[output_key] = match.group(1).strip() if match else ""

        # If entity name directly matches a handbook-defined term, use the exact
        # definition (highest confidence) rather than the LLM synthesis.
        if term_definitions:
            direct_def = term_definitions.get(entity_name.lower())
            if direct_def:
                sections["formal_definition"] = direct_def

        # Preserve per-section raw findings alongside the polished synthesis
        if result.raw_response:
            sections["raw_handbook_sections"] = result.raw_response

        return sections
    except Exception as e:
        return {
            "formal_definition": f"[Error: {e}]",
            "domain_context": "",
            "governance_rules": "",
            "raw_handbook_sections": "",
        }


# ---------------------------------------------------------------------------
# Relationship extraction from conceptual model docstores
# ---------------------------------------------------------------------------




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
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Use LLM to infer domain and subgroup for a HANDBOOK_ONLY entity (three-tier).

    Queries the handbook RAG so the LLM has FA-specific context when inferring
    which domain/subtype the entity belongs to.
    """
    query = _DOMAIN_INFERENCE_PROMPT.format(
        taxonomy_context=taxonomy_context,
        entity_name=entity_name,
        handbook_definition=handbook_definition,
    )
    try:
        result = query_collections(handbook_collections, query, rag_config)
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


def _get_alias_variants(term: str) -> list[str]:
    """Generate normalized term variants including aliases.
    
    For a given term, returns:
    1. The base normalized form
    2. All known aliases from _ENTITY_ALIASES
    3. Common abbreviations (association→assoc, football→fa)
    """
    base = _normalize(term)
    variants: set[str] = {base}
    
    # Add known aliases
    for canonical, aliases in _ENTITY_ALIASES.items():
        if base == canonical:
            variants.update(aliases)
        elif base in aliases:
            variants.add(canonical)
            variants.update(a for a in aliases if a != base)
    
    # Add common abbreviations
    if "association" in base:
        variants.add(base.replace("association", "assoc"))
    if "football" in base:
        variants.add(base.replace("football", "fa"))
    
    return list(variants)


def consolidate_catalog(
    conceptual_entities: list[dict],
    handbook_terms: list[dict],
    handbook_mappings: dict[str, dict],
    inventory_descriptions: dict[str, dict],
    handbook_context: dict[str, dict],
    relationships: dict[str, list[dict]],
    handbook_collections: list[str],
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
            # Prefer direct name matches (term == entity) over indirect matches.
            # Without this, iteration order determines the winner when multiple terms
            # map to the same entity — e.g. "Provisional Suspension" can overwrite
            # the "Player" → Player direct match because it appears later alphabetically.
            existing = entity_to_mapping.get(mapped_entity)
            is_direct = term_lower == mapped_entity
            if existing is None or is_direct:
                entity_to_mapping[mapped_entity] = (term_lower, mapping)

    # Inject forced entries for entities known to be in the Handbook but
    # whose definitions aren't in "X means Y" format (never extracted by Step 3).
    for forced_name in _FORCED_HANDBOOK_ENTITIES:
        forced_norm = _normalize(forced_name)
        if forced_norm not in entity_to_mapping:
            entity_to_mapping[forced_norm] = (
                forced_norm,
                {
                    "mapped_entity": forced_name,
                    "domain": "",
                    "fact_sheet_id": "",
                    "mapping_confidence": "medium",
                    "mapping_rationale": "Forced handbook match — entity present in Handbook without formal definition",
                },
            )

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
            "domain_fact_sheet_id": entity.get("domain_fact_sheet_id", ""),
            "subgroup": entity.get("subgroup", ""),
            "subgroup_fact_sheet_id": entity.get("subgroup_fact_sheet_id", ""),
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
            handbook_collections=handbook_collections,
            rag_config=rag_config,
        )

        record = {
            "fact_sheet_id": "",
            "entity_name": term,
            "domain": inferred.get("entity_domain", "HANDBOOK_DISCOVERED"),
            "domain_fact_sheet_id": "",
            "subgroup": inferred.get("entity_subgroup", ""),
            "subgroup_fact_sheet_id": "",
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
# Hierarchical output builder
# ---------------------------------------------------------------------------


def build_hierarchical_output(
    consolidated_entities: list[dict],
    inventory_lookup: dict[str, dict],
    conceptual_entities: list[dict],
) -> dict:
    """Restructure flat consolidated entity list into Domain → Subtype → Entity hierarchy.

    Domain and subtype descriptions come from the inventory JSON via their own
    fact_sheet_id entries (same O(1) lookup used for entities — no extra LLM calls).

    Output shape:
    {
      "PARTY": {
        "fact_sheet_id": "...",
        "description": "...",        # from inventory
        "subtypes": {
          "Organisation": {
            "fact_sheet_id": "...",
            "description": "...",    # from inventory
            "entities": [...]
          }
        },
        "entities": [...],           # entities with no subtype
        "handbook_only": [...]       # HANDBOOK_ONLY entities inferred to this domain
      }
    }
    """
    # Build domain/subtype metadata from the conceptual entity list (which carries
    # domain_fact_sheet_id and subgroup_fact_sheet_id).
    domain_meta: dict[str, dict] = {}
    subtype_meta: dict[str, dict] = {}  # key: "DOMAIN::Subtype"

    for e in conceptual_entities:
        domain = e.get("domain", "UNKNOWN").upper()
        d_fsid = e.get("domain_fact_sheet_id", "")
        if domain not in domain_meta:
            inv = inventory_lookup.get(d_fsid, {})
            domain_meta[domain] = {
                "fact_sheet_id": d_fsid,
                "description": inv.get("description", ""),
            }

        subgroup = e.get("subgroup", "") or e.get("subtype", "")
        sg_fsid = e.get("subgroup_fact_sheet_id", "")
        if subgroup:
            key = f"{domain}::{subgroup}"
            if key not in subtype_meta:
                inv = inventory_lookup.get(sg_fsid, {})
                subtype_meta[key] = {
                    "fact_sheet_id": sg_fsid,
                    "description": inv.get("description", ""),
                }

    # Group consolidated entities into the hierarchy.
    output: dict[str, dict] = {}

    for record in consolidated_entities:
        domain = record.get("domain", "UNKNOWN").upper()
        subgroup = record.get("subgroup", "") or ""
        source = record.get("source", "")

        if domain not in output:
            meta = domain_meta.get(domain, {"fact_sheet_id": "", "description": ""})
            output[domain] = {
                "fact_sheet_id": meta["fact_sheet_id"],
                "description": meta["description"],
                "subtypes": {},
                "entities": [],
                "handbook_only": [],
            }

        # Strip redundant domain/subgroup keys from entity record (already in hierarchy).
        entity_record = {
            k: v for k, v in record.items()
            if k not in ("domain", "domain_fact_sheet_id", "subgroup", "subgroup_fact_sheet_id")
        }

        if source == "HANDBOOK_ONLY":
            output[domain]["handbook_only"].append(entity_record)
        elif subgroup:
            subtypes = output[domain]["subtypes"]
            if subgroup not in subtypes:
                meta = subtype_meta.get(f"{domain}::{subgroup}", {"fact_sheet_id": "", "description": ""})
                subtypes[subgroup] = {
                    "fact_sheet_id": meta["fact_sheet_id"],
                    "description": meta["description"],
                    "entities": [],
                }
            subtypes[subgroup]["entities"].append(entity_record)
        else:
            output[domain]["entities"].append(entity_record)

    # Sort domains and subtypes alphabetically for stable output.
    return dict(sorted(output.items()))


# ---------------------------------------------------------------------------
# Main generation
# ---------------------------------------------------------------------------


def generate_consolidated_catalog(
    rag_config: RagConfig,
    handbook_collections: list[str],
    output_dir: Path,
    skip_relationships: bool,
    model_json: Path,
    inventory_json: Path,
    domain_filter: str | None = None,
    skip_handbook: bool = False,
    entity_filter: str | None = None,
) -> None:
    """Generate consolidated catalog via RAG+LLM queries."""

    if domain_filter:
        domain_filter = domain_filter.upper()
        catalog_json_path = output_dir / f"fa_consolidated_catalog_{domain_filter.lower()}.json"
        relationships_json_path = output_dir / f"fa_consolidated_relationships_{domain_filter.lower()}.json"
    else:
        catalog_json_path = output_dir / "fa_consolidated_catalog.json"
        relationships_json_path = output_dir / "fa_consolidated_relationships.json"

    print("\n=== FA Consolidated Catalog (RAG+LLM) ===")
    print(f"  Model: {rag_config.ollama.llm_model}")
    print(f"  Handbook: {handbook_collections}")

    # Step 1: Load entities from pre-parsed model JSON
    print("\n=== Step 1: Load Conceptual Model Entities ===")
    all_entities = load_entities_from_json(model_json)
    conceptual_entities = all_entities
    if domain_filter:
        conceptual_entities = [
            e for e in all_entities
            if e.get("domain", "").upper() == domain_filter
        ]
        print(f"  After domain filter ({domain_filter}): {len(conceptual_entities)} entities")

    if entity_filter:
        entity_filter_norm = _normalize(entity_filter)
        matched = [
            e for e in conceptual_entities
            if _normalize(e["entity_name"]) == entity_filter_norm
        ]
        if not matched:
            print(f"\nERROR: Entity '{entity_filter}' not found.", file=sys.stderr)
            avail = ", ".join(e["entity_name"] for e in conceptual_entities)
            print(f"  Available: {avail}", file=sys.stderr)
            sys.exit(1)
        conceptual_entities = matched
        print(f"  Entity filter: '{entity_filter}' (1 entity)")

    # Step 2: Inventory lookup by fact_sheet_id (direct JSON, no RAG)
    print("\n=== Step 2: Load Inventory Descriptions ===")
    inventory_lookup = load_inventory_from_json(inventory_json)
    inventory_descriptions: dict[str, dict] = {}
    matched_count = 0
    for entity in conceptual_entities:
        name = entity.get("entity_name", "")
        fsid = entity.get("fact_sheet_id", "")
        inv = inventory_lookup.get(fsid, {})
        if inv:
            matched_count += 1
        else:
            inv = {"description": "Not documented in LeanIX inventory", "level": "", "status": "", "type": ""}
        inventory_descriptions[_normalize(name)] = inv
    print(f"  {matched_count}/{len(conceptual_entities)} entities matched in inventory")

    # Step 3: Extract Handbook defined terms from docstore
    print("\n=== Step 3: Extract Handbook Defined Terms ===")
    if skip_handbook:
        print("  Skipping (--skip-handbook)")
        handbook_terms: list[dict] = []
    else:
        handbook_terms = extract_handbook_terms_from_docstore(rag_config)

    # Step 4: Match Handbook terms to conceptual model entities by name (no LLM)
    print("\n=== Step 4: Match Handbook Terms to Conceptual Model ===")
    handbook_mappings: dict[str, dict] = {}
    if skip_handbook:
        print("  Skipping (--skip-handbook)")
    else:
        # Match against the full entity list (not domain/entity-filtered subset)
        # so that handbook terms are matched across all domains.
        # Build entity lookup with alias variants for expanded matching.
        entity_name_map: dict[str, dict] = {}
        for e in all_entities:
            # Index by normalized name
            norm_name = _normalize(e["entity_name"])
            entity_name_map[norm_name] = e
            # Also index by alias variants
            for variant in _get_alias_variants(e["entity_name"]):
                if variant != norm_name:
                    entity_name_map[variant] = e
        
        matched_terms = 0
        for term_entry in handbook_terms:
            term = term_entry["term"]
            # Try all alias variants for this term
            matched_entity = None
            match_type = "no match"
            for variant in _get_alias_variants(term):
                if variant in entity_name_map:
                    matched_entity = entity_name_map[variant]
                    if variant == _normalize(term):
                        match_type = "direct"
                    else:
                        match_type = "alias"
                    break
            
            if matched_entity:
                handbook_mappings[term.lower()] = {
                    "mapped_entity": matched_entity["entity_name"],
                    "domain": matched_entity["domain"],
                    "fact_sheet_id": matched_entity["fact_sheet_id"],
                    "mapping_confidence": "high" if match_type == "direct" else "medium",
                    "mapping_rationale": "Direct name match" if match_type == "direct" else f"Alias match via '{term}' → '{matched_entity['entity_name']}'",
                }
                matched_terms += 1
            else:
                handbook_mappings[term.lower()] = {
                    "mapped_entity": "Not mapped",
                    "domain": "",
                    "fact_sheet_id": "",
                    "mapping_confidence": "low",
                    "mapping_rationale": "No matching entity name in conceptual model",
                }
        print(f"  {matched_terms}/{len(handbook_terms)} handbook terms matched by name")

    # Step 5: Get handbook context for all entities (RAG+LLM)
    print("\n=== Step 5: Extract Handbook Context ===")
    handbook_context: dict[str, dict] = {}
    if skip_handbook:
        print("  Skipping (--skip-handbook)")
    else:
        term_definitions: dict[str, str] = {
            t["term"].lower(): t["definition"] for t in handbook_terms
        }
        total = len(conceptual_entities)
        for i, entity in enumerate(conceptual_entities, 1):
            name = entity.get("entity_name", "")
            domain = entity.get("domain", "UNKNOWN")
            print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)
            
            # Fix 1: Skip RAG for entities with no handbook coverage
            if name in _NO_HANDBOOK_COVERAGE:
                handbook_context[_normalize(name)] = {
                    "formal_definition": "",
                    "domain_context": "Not applicable — internal FA business concept outside regulatory scope",
                    "governance_rules": "Not documented in FA Handbook — outside governance scope",
                }
                continue
            
            # Stage 1: BM25 section discovery (no LLM — fast keyword scan)
            relevant_sections = discover_relevant_sections(
                entity_name=name,
                section_prefix=_SECTION_PREFIX,
                rag_config=rag_config,
                threshold=_SECTION_THRESHOLD,
                bm25_top_k=_SECTION_BM25_TOP_K,
            )
            if _SECTION_TOP_N and relevant_sections:
                relevant_sections = relevant_sections[:_SECTION_TOP_N]
            # Fall back to all handbook collections when section routing finds nothing
            target_collections = relevant_sections if relevant_sections else handbook_collections

            # Stage 2: LLM synthesis against targeted sections only
            context = get_handbook_context_for_entity(
                name, domain, target_collections, rag_config,
                term_definitions=term_definitions,
            )
            handbook_context[_normalize(name)] = context
        print(f"  {len(handbook_context)} entities enriched with Handbook context      ")

    # Step 6: Load relationships from pre-parsed model JSON
    print("\n=== Step 6: Load Relationships ===")
    relationships: dict[str, list[dict]] = {}

    if skip_relationships:
        print("  Skipping relationship extraction (--skip-relationships)")
    else:
        relationships = load_relationships_from_json(model_json)

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
        handbook_collections=handbook_collections,
        rag_config=rag_config,
        skip_handbook_only=domain_filter is not None,
    )

    # Write JSON outputs — hierarchical (Domain → Subtype → Entity)
    hierarchical = build_hierarchical_output(
        consolidated_entities, inventory_lookup, conceptual_entities
    )
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump(hierarchical, f, indent=2, ensure_ascii=False)

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

    # Quality metrics — count only real data, not error placeholders or hedged fallbacks.
    def _has_real_definition(e: dict) -> bool:
        v = e.get("formal_definition", "")
        return bool(v) and not v.startswith("[Error:")

    def _has_real_governance(e: dict) -> bool:
        v = e.get("governance_rules", "").strip().lstrip("*").strip()
        _negative = ("not documented", "no specific", "no documented", "no governance", "outside governance scope")
        return bool(v) and not any(v.lower().startswith(n) for n in _negative)

    print("\n=== Quality Metrics ===")
    with_definitions = sum(1 for e in consolidated_entities if _has_real_definition(e))
    with_governance = sum(1 for e in consolidated_entities if _has_real_governance(e))
    print(f"  Entities with formal definitions: {with_definitions}/{len(consolidated_entities)}")
    print(f"  Entities with governance rules: {with_governance}/{len(consolidated_entities)}")


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
            "Prerequisites:\n"
            "  - LeanIX model JSON  (from ingest_fa_leanix_dat_enterprise_conceptual_model)\n"
            "  - LeanIX inventory JSON (from ingest_fa_leanix_global_inventory)\n"
            "  - FA Handbook ingested to fa_handbook (RAG only)"
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
        "--model-json", type=Path, default=_DEFAULT_MODEL_JSON,
        help=f"Path to LeanIX model JSON (default: {_DEFAULT_MODEL_JSON})",
    )
    parser.add_argument(
        "--inventory-json", type=Path, default=_DEFAULT_INVENTORY_JSON,
        help=f"Path to LeanIX inventory JSON (default: {_DEFAULT_INVENTORY_JSON})",
    )
    parser.add_argument(
        "--skip-relationships", action="store_true",
        help="Skip relationship extraction (saves a few seconds — relationships are domain-level only)",
    )
    parser.add_argument(
        "--skip-handbook", action="store_true",
        help="Skip handbook term extraction, mapping, and context enrichment (steps 3-5). "
             "Produces LEANIX_ONLY output only — useful for quickly testing entity/subgroup extraction.",
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
    parser.add_argument(
        "--entity", default=None, metavar="ENTITY",
        help=(
            "Restrict to a single entity name for fast validation (e.g. 'Player'). "
            "Requires --domain. Skips step 4 (141 LLM mapping calls) — "
            "formal_definition is populated via direct handbook term lookup only. "
            "Useful for quickly validating RAG extraction and parsing for one entity."
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

    # Resolve handbook collections dynamically: prefer section collections (fa_handbook_sNN),
    # fall back to the legacy monolithic collection so existing setups keep working.
    from elt_llm_core.vector_store import create_chroma_client, list_collections_by_prefix
    import re as _re
    _client = create_chroma_client(rag_config.chroma)
    _section_pat = _re.compile(rf'^{_re.escape(_SECTION_PREFIX)}_s\d{{2}}$')
    _all = list_collections_by_prefix(_client, _SECTION_PREFIX)
    handbook_collections = [c for c in _all if _section_pat.match(c)]
    if handbook_collections:
        print(f"  Handbook: {len(handbook_collections)} section collections ({_SECTION_PREFIX}_sNN)")
    else:
        handbook_collections = ["fa_handbook"]
        print("  Handbook: monolithic 'fa_handbook' collection (section collections not found)")

    generate_consolidated_catalog(
        rag_config=rag_config,
        handbook_collections=handbook_collections,
        output_dir=output_dir,
        skip_relationships=args.skip_relationships,
        model_json=args.model_json.expanduser(),
        inventory_json=args.inventory_json.expanduser(),
        domain_filter=args.domain,
        skip_handbook=args.skip_handbook,
        entity_filter=args.entity,
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
