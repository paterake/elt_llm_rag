"""FA Glossary Generator — Claude AI-Native implementation.

AI-native approach: 3 targeted RAG queries + 1 LLM synthesis per entity.
Eliminates the 7-step pipeline, term mapping, and consolidation logic.

vs fa_consolidated_catalog.py (hybrid, ~170+ LLM calls):
  Architecture     Hybrid (7 steps)         AI-Native (this file)
  ─────────────    ──────────────────────   ──────────────────────────
  LLM calls        ~170+ per domain run     4 per entity (3 RAG + 1 synth)
  Term mapping     141 separate LLM calls   LLM infers from context
  Consolidation    Python merging logic     LLM outputs structured JSON
  Governance       Separate fallback pass   Included in synthesis prompt
  Default model    qwen2.5:14b              qwen3.5:9b

Per-entity flow:
  1. RAG → conceptual model   (what is this entity in the data model?)
  2. RAG → LeanIX inventory   (is it in the asset inventory?)
  3. RAG → FA Handbook        (definition + governance rules)
  4. LLM → synthesis prompt   (combine all 3 → structured JSON entry)

Usage:
    # Domain run (fastest comparison point)
    uv run --package elt-llm-consumer elt-llm-consumer-glossary-claude --domain PARTY

    # Single entity validation
    uv run --package elt-llm-consumer elt-llm-consumer-glossary-claude \\
        --domain PARTY --entity "Player"

    # Try a different model
    uv run --package elt-llm-consumer elt-llm-consumer-glossary-claude \\
        --domain PARTY --model qwen2.5:14b

    # Full run with handbook-only discovery
    uv run --package elt-llm-consumer elt-llm-consumer-glossary-claude
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_core.models import create_llm_model
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

_DEFAULT_MODEL = "qwen3.5:9b"

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

# Three focused RAG queries — one per source, keeps retrieval clean per corpus.
_QUERY_MODEL = (
    "Describe '{name}' in the FA data model. "
    "What domain does it belong to? What subgroup? What is its purpose and relationships?"
)
_QUERY_INVENTORY = (
    "Find '{name}' in the LeanIX inventory. "
    "What type is it? What description is given? What is its status?"
)
_QUERY_HANDBOOK = (
    "What does the FA Handbook say about '{name}'? "
    "Find the formal definition and all governance rules, regulations, "
    "registration requirements, eligibility criteria, and compliance obligations."
)

# Single synthesis prompt — receives all 3 RAG contexts, returns JSON.
_SYNTHESIS_PROMPT = """\
You are building a business glossary for the FA (Football Association) data model.

Entity: {entity_name}
Domain: {domain}
Known FA domains: PARTY, AGREEMENT, PRODUCT, CHANNEL, ACCOUNTS, ASSETS

=== LEANIX CONCEPTUAL MODEL ===
{model_context}

=== LEANIX INVENTORY ===
{inventory_context}

=== FA HANDBOOK ===
{handbook_context}

Generate a complete, accurate glossary entry. Return ONLY a valid JSON object — no markdown, no preamble:

{{
  "formal_definition": "Verbatim definition from FA Handbook if found. Synthesised definition from context if no handbook entry. Empty string if nothing available.",
  "domain_context": "Role of {entity_name} in the {domain} domain — business purpose, key relationships, how it fits in the FA data model.",
  "governance_rules": "All FA Handbook rules, obligations, and requirements that apply to {entity_name} — include section/rule citations (e.g. Rule A3.1, Section C). Empty string if none found.",
  "leanix_description": "Description from LeanIX inventory. 'Not documented in LeanIX inventory' if absent.",
  "handbook_term": "Exact term as defined in the FA Handbook that maps to {entity_name}, or null if not a defined handbook term.",
  "mapping_confidence": "high if {entity_name} directly matches a handbook term, medium if related term found, low if inferred or not found",
  "mapping_rationale": "One sentence explaining why this handbook term maps to {entity_name}, or why no mapping was found.",
  "source": "BOTH if found in both LeanIX model and FA Handbook, LEANIX_ONLY if only in LeanIX, HANDBOOK_ONLY if only discovered via handbook",
  "review_status": "PENDING if well-defined and unambiguous, PROPOSED_NEW_TAXONOMY if candidate for model addition, NEEDS_CLARIFICATION if ambiguous or conflicting"
}}"""

# ---------------------------------------------------------------------------
# Entity enumeration from conceptual model docstores (deterministic)
# ---------------------------------------------------------------------------

_SUBGROUP_PAT = re.compile(r"^##\s+((?!.*Domain\s+Relationships)[^#\n]+)$")
_ENTITY_PAT = re.compile(r"^-?\s*\*\*(.+?)\*\*(?:\s*\*\(LeanIX ID:\s*`([^`]*)`\)\*)?")


def _extract_entities(rag_config: RagConfig, model_collections: list[str]) -> list[dict]:
    """Enumerate entities from conceptual model docstores."""
    from llama_index.core import StorageContext

    entities: list[dict] = []
    seen: set[str] = set()

    for coll_name in model_collections:
        docstore_path = get_docstore_path(rag_config.chroma, coll_name)
        if not docstore_path.exists():
            continue

        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = sorted(
            storage.docstore.docs.values(),
            key=lambda n: getattr(n, "start_char_idx", 0) or 0,
        )

        domain = coll_name.replace("fa_leanix_dat_enterprise_conceptual_model_", "").upper()
        current_subgroup = ""

        for node in nodes:
            for line in (getattr(node, "text", "") or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                m = _SUBGROUP_PAT.match(line)
                if m:
                    current_subgroup = m.group(1).strip()
                    continue
                if line.startswith("## "):
                    current_subgroup = ""
                    continue
                m = _ENTITY_PAT.match(line)
                if m:
                    name = m.group(1).strip()
                    fsid = (m.group(2) or "").strip()
                    if not name or len(name) > 100 or name.lower() in seen:
                        continue
                    seen.add(name.lower())
                    entities.append({
                        "entity_name": name,
                        "domain": domain,
                        "fact_sheet_id": fsid,
                        "subgroup": current_subgroup,
                    })

    print(f"  {len(entities)} entities extracted from conceptual model")
    return entities


# ---------------------------------------------------------------------------
# Handbook term discovery for HANDBOOK_ONLY entities
# ---------------------------------------------------------------------------

_DEF_MARKER = "<!-- DEF:"
_DEF_LINE_PAT = re.compile(r"<!--\s*DEF:\s*(\S+)\s*\|\s*(.+?)\s*\|\s*(.+?)\s*-->")
_ARTIFACT_FRAGMENTS = {"CONTENTS PAGE", "DEFINITION INTERPRETATION", "APPENDIX", "SCHEDULE"}


def _extract_handbook_terms(rag_config: RagConfig) -> dict[str, str]:
    """Return {term_lower: definition} from the FA Handbook docstore markers."""
    from llama_index.core import StorageContext

    docstore_path = get_docstore_path(rag_config.chroma, "fa_handbook")
    if not docstore_path.exists():
        return {}

    storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
    terms: dict[str, str] = {}

    for node in storage.docstore.docs.values():
        for line in (getattr(node, "text", "") or "").splitlines():
            if _DEF_MARKER not in line:
                continue
            m = _DEF_LINE_PAT.match(line.strip())
            if not m:
                continue
            term = m.group(2).strip()
            defn = m.group(3).strip()
            if any(f in term.upper() for f in _ARTIFACT_FRAGMENTS) or term.endswith(" -"):
                continue
            if term.lower() not in terms:
                terms[term.lower()] = defn

    print(f"  {len(terms)} defined terms in FA Handbook docstore")
    return terms


# ---------------------------------------------------------------------------
# Per-entity synthesis: 3 RAG + 1 LLM
# ---------------------------------------------------------------------------

def _rag(collections: list[str], query: str, rag_config: RagConfig) -> str:
    """RAG query → response text. Returns empty string on failure."""
    if not collections:
        return ""
    try:
        return query_collections(collections, query, rag_config).response.strip()
    except Exception as e:
        return f"[Error: {e}]"


def synthesize_entry(
    entity_name: str,
    domain: str,
    model_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    rag_config: RagConfig,
    llm,
    index: int,
    total: int,
) -> dict:
    """3 targeted RAG queries + 1 LLM synthesis → complete glossary entry dict."""
    print(f"  [{index}/{total}] {entity_name}…", end="\r", flush=True)

    model_ctx = _rag(model_collections, _QUERY_MODEL.format(name=entity_name), rag_config)
    inv_ctx = _rag(inventory_collections, _QUERY_INVENTORY.format(name=entity_name), rag_config)
    hb_ctx = _rag(handbook_collections, _QUERY_HANDBOOK.format(name=entity_name), rag_config)

    prompt = _SYNTHESIS_PROMPT.format(
        entity_name=entity_name,
        domain=domain,
        model_context=model_ctx or "No information found",
        inventory_context=inv_ctx or "Not documented",
        handbook_context=hb_ctx or "No information found",
    )

    try:
        response = str(llm.complete(prompt)).strip()
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON object in LLM response")
        return json.loads(json_match.group())
    except Exception:
        return {
            "formal_definition": "",
            "domain_context": "",
            "governance_rules": "",
            "leanix_description": "Not documented",
            "handbook_term": None,
            "mapping_confidence": "low",
            "mapping_rationale": "Synthesis failed",
            "source": "LEANIX_ONLY",
            "review_status": "NEEDS_CLARIFICATION",
        }


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------

def generate_glossary(
    rag_config: RagConfig,
    model_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    output_dir: Path,
    domain_filter: str | None = None,
    entity_filter: str | None = None,
    skip_handbook_only: bool = False,
) -> None:
    print("\n=== Step 1: Extract entities from conceptual model ===")
    all_entities = _extract_entities(rag_config, model_collections)

    entities = all_entities
    if domain_filter:
        entities = [e for e in entities if e["domain"] == domain_filter.upper()]
        print(f"  Filtered to {len(entities)} entities in {domain_filter} domain")
    if entity_filter:
        entities = [e for e in entities if e["entity_name"].lower() == entity_filter.lower()]
        print(f"  Filtered to entity: {entity_filter}")

    # Create LLM once — reused for all synthesis calls
    llm = create_llm_model(rag_config.ollama)

    print(f"\n=== Step 2: Synthesise {len(entities)} glossary entries ===")
    results: list[dict] = []

    for i, entity in enumerate(entities, 1):
        entry = synthesize_entry(
            entity_name=entity["entity_name"],
            domain=entity["domain"],
            model_collections=model_collections,
            inventory_collections=inventory_collections,
            handbook_collections=handbook_collections,
            rag_config=rag_config,
            llm=llm,
            index=i,
            total=len(entities),
        )
        results.append({
            "fact_sheet_id": entity.get("fact_sheet_id", ""),
            "entity_name": entity["entity_name"],
            "domain": entity["domain"],
            "subgroup": entity.get("subgroup", ""),
            "hierarchy_level": "",
            "review_notes": "",
            "relationships": [],
            **entry,
        })

    print(f"  {len(results)} entries synthesised        ")

    # HANDBOOK_ONLY discovery — only for full (non-domain, non-entity) runs
    if not entity_filter and not domain_filter and not skip_handbook_only:
        print("\n=== Step 3: Discover HANDBOOK_ONLY entities ===")
        handbook_terms = _extract_handbook_terms(rag_config)
        entity_names_lower = {e["entity_name"].lower() for e in all_entities}
        handbook_only = {t: d for t, d in handbook_terms.items() if t not in entity_names_lower}
        print(f"  {len(handbook_only)} handbook terms not in conceptual model")

        for i, (term, defn) in enumerate(handbook_only.items(), 1):
            entry = synthesize_entry(
                entity_name=term.title(),
                domain="HANDBOOK_DISCOVERED",
                model_collections=model_collections,
                inventory_collections=inventory_collections,
                handbook_collections=handbook_collections,
                rag_config=rag_config,
                llm=llm,
                index=i,
                total=len(handbook_only),
            )
            entry["source"] = "HANDBOOK_ONLY"
            if not entry.get("formal_definition"):
                entry["formal_definition"] = defn
            results.append({
                "fact_sheet_id": "",
                "entity_name": term.title(),
                "domain": entry.get("domain", "HANDBOOK_DISCOVERED"),
                "subgroup": "",
                "hierarchy_level": "",
                "review_notes": "Handbook term — candidate for conceptual model addition",
                "relationships": [],
                **entry,
            })
        print(f"  {len(handbook_only)} handbook-only entries added        ")

    # Write output
    domain_suffix = f"_{domain_filter.lower()}" if domain_filter else ""
    entity_suffix = f"_{entity_filter.lower().replace(' ', '_')}" if entity_filter else ""
    output_file = output_dir / f"fa_glossary_claude{domain_suffix}{entity_suffix}.json"
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    # Summary
    def _has_real_definition(e: dict) -> bool:
        v = e.get("formal_definition", "")
        return bool(v) and not v.startswith("[Error:")

    def _has_real_governance(e: dict) -> bool:
        v = e.get("governance_rules", "")
        return bool(v) and not v.startswith("Not documented in FA Handbook")

    by_source: dict[str, int] = {}
    for e in results:
        s = e.get("source", "UNKNOWN")
        by_source[s] = by_source.get(s, 0) + 1

    print("\n=== Summary ===")
    print(f"  Total entries: {len(results)}")
    print(f"  Entities with formal definitions: {sum(1 for e in results if _has_real_definition(e))}/{len(results)}")
    print(f"  Entities with governance rules:   {sum(1 for e in results if _has_real_governance(e))}/{len(results)}")
    for src, cnt in sorted(by_source.items()):
        print(f"  {src}: {cnt}")
    print(f"\n  Output → {output_file}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "FA Glossary Generator — Claude AI-Native "
            "(3 RAG + 1 LLM synthesis per entity, default model: qwen3.5:9b)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Approach: 3 targeted RAG queries (model / inventory / handbook) "
            "+ 1 direct LLM synthesis call per entity.\n\n"
            "Output: fa_glossary_claude[_domain][_entity].json\n\n"
            "Compare with: elt-llm-consumer-consolidated-catalog (hybrid 7-step pipeline)"
        ),
    )
    parser.add_argument(
        "--model", default=None,
        help=f"Override LLM model (default: {_DEFAULT_MODEL})",
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
        "--domain", default=None, metavar="DOMAIN",
        help="Restrict to a single domain (e.g. PARTY). Writes fa_glossary_claude_{domain}.json.",
    )
    parser.add_argument(
        "--entity", default=None, metavar="ENTITY",
        help="Restrict to a single entity (e.g. 'Player'). Requires --domain.",
    )
    parser.add_argument(
        "--num-queries", type=int, default=None,
        help="Override num_queries for RAG (1=fastest, 3=best recall; default: from rag_config.yaml)",
    )
    parser.add_argument(
        "--skip-handbook-only", action="store_true",
        help="Skip HANDBOOK_ONLY discovery (Step 3). Only applies to full (non-domain) runs.",
    )
    args = parser.parse_args()

    output_dir = args.output_dir.expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.config)

    rag_config.ollama.llm_model = args.model or _DEFAULT_MODEL
    print(f"  LLM: {rag_config.ollama.llm_model}")

    if args.num_queries is not None:
        rag_config.query.num_queries = args.num_queries
    print(f"  num_queries: {rag_config.query.num_queries}")

    print("\nResolving collections…")
    model_collections = resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    # For domain runs, filter to the matching collection only
    if args.domain:
        model_collections = [
            c for c in model_collections if c.endswith(args.domain.lower())
        ]
    inventory_collections = resolve_collection_prefixes(
        ["fa_leanix_global_inventory"], rag_config
    )
    handbook_collections = ["fa_handbook"]

    if not model_collections:
        print(
            "\nERROR: No conceptual model collections found.\n"
            "Run: uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"  Conceptual Model ({len(model_collections)}): {model_collections}")
    print(f"  Inventory ({len(inventory_collections)})")
    print(f"  Handbook: fa_handbook")

    generate_glossary(
        rag_config=rag_config,
        model_collections=model_collections,
        inventory_collections=inventory_collections,
        handbook_collections=handbook_collections,
        output_dir=output_dir,
        domain_filter=args.domain,
        entity_filter=args.entity,
        skip_handbook_only=args.skip_handbook_only,
    )


if __name__ == "__main__":
    main()
