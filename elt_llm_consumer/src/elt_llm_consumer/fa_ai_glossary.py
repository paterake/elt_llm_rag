"""FA Business Glossary Generator — AI-Native (Qwen 2.5/3.5).

Minimal orchestration, maximum LLM synthesis.

Philosophy:
  - Trust the LLM to extract, synthesize, and structure
  - One comprehensive prompt per entity (not multiple specialized prompts)
  - RAG for retrieval, LLM for everything else
  - ~50 lines of core logic vs ~1300 lines

Primary Objective:
  Generate a comprehensive business glossary from the FA Handbook,
  reverse-engineered and mapped to the LeanIX conceptual data model.

Usage:
    # Full glossary generation
    uv run --package elt-llm-consumer elt-llm-consumer-ai-glossary \\
        --domain PARTY

    # Single entity (fast iteration)
    uv run --package elt-llm-consumer elt-llm-consumer-ai-glossary \\
        --domain PARTY --entity "Player"

    # Use Qwen 2.5/3.5
    uv run --package elt-llm-consumer elt-llm-consumer-ai-glossary \\
        --domain PARTY --model qwen2.5:14b
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_query.query import query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_RAG_CONFIG = Path(
    "~/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml"
).expanduser()

_DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"

# ---------------------------------------------------------------------------
# AI-Native Prompt — Single Comprehensive Synthesis
# ---------------------------------------------------------------------------

_GLOSSARY_ENTRY_PROMPT = """
You are creating a business glossary entry for "{entity_name}" in the {domain} domain.

CONTEXT FROM FA HANDBOOK:
{handbook_context}

CONTEXT FROM LEANIX CONCEPTUAL MODEL:
{conceptual_context}

CONTEXT FROM LEANIX ASSET INVENTORY:
{inventory_context}

REFERENCE DATA ARCHITECTURE DOMAINS:
{reference_domains}

Generate a complete glossary entry with these sections:

1. FORMAL_DEFINITION
   - Quote the EXACT definition from FA Handbook verbatim if it exists
   - Format: "{entity_name} means [exact quote]"
   - If no exact definition exists, state: "Not explicitly defined in FA Handbook"
   - Do NOT paraphrase or invent — only use what's in the handbook

2. BUSINESS_CONTEXT  
   - What role does this entity play in the {domain} domain?
   - What related concepts should be considered?
   - How does it relate to other entities in the domain?

3. GOVERNANCE
   - List ALL FA Handbook rules, obligations, and regulatory requirements
   - Cite specific section numbers, rule numbers, page references (e.g., "Rule A3.1", "Section C")
   - Include: eligibility criteria, registration requirements, compliance obligations, restrictions
   - If no governance rules apply, state: "Not documented in FA Handbook"

4. LEANIX_DESCRIPTION
   - Description from LeanIX asset inventory
   - Include level/status if available

5. RELATED_ENTITIES
   - Other conceptual model entities this relates to (from retrieved context)
   - Include relationship type if mentioned

6. DATA_STEWARDS
   - Any roles, responsibilities, or accountabilities mentioned
   - Who owns/manages this entity?

7. DOMAIN_VALIDATION
   - Confirm if {domain} is the correct domain
   - If not, suggest the correct domain from the reference architecture

Return ONLY valid JSON with this exact structure:
{{
  "entity_name": "{entity_name}",
  "domain": "{domain}",
  "formal_definition": "...",
  "business_context": "...",
  "governance": [
    {{
      "rule_type": "registration|eligibility|compliance|restriction|reporting|disciplinary",
      "citation": "Section X, Rule Y",
      "requirement": "..."
    }}
  ],
  "leanix_description": "...",
  "related_entities": ["Entity1", "Entity2"],
  "data_stewards": "...",
  "domain_validation": {{
    "is_correct": true,
    "suggested_domain": ""
  }},
  "sources": {{
    "handbook": true/false,
    "conceptual_model": true/false,
    "inventory": true/false
  }}
}}

If a section has no information, use empty string "" or empty array [].
Return ONLY the JSON, no other text.
"""

# ---------------------------------------------------------------------------
# Core AI-Native Logic — ~50 lines
# ---------------------------------------------------------------------------


def generate_glossary_entry(
    entity_name: str,
    domain: str,
    conceptual_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    rag_config: RagConfig,
    reference_domains: list[str],
) -> dict:
    """Generate a complete glossary entry for one entity using AI-native synthesis."""
    
    # RAG retrieval — one query per source
    conceptual_query = f"Find information about '{entity_name}' in the conceptual data model. Include entity details, relationships, and domain context."
    inventory_query = f"Find the LeanIX inventory description for '{entity_name}'. Provide description, level, and status."
    handbook_query = f"Find the definition and governance rules for '{entity_name}' in the FA Handbook. Search for '{entity_name} means' or similar definition format, and any rules/obligations."
    
    try:
        conceptual_result = query_collections(conceptual_collections, conceptual_query, rag_config)
        conceptual_context = conceptual_result.response.strip()
    except Exception:
        conceptual_context = "No information retrieved."
    
    try:
        inventory_result = query_collections(inventory_collections, inventory_query, rag_config)
        inventory_context = inventory_result.response.strip()
    except Exception:
        inventory_context = "No information retrieved."
    
    try:
        handbook_result = query_collections(handbook_collections, handbook_query, rag_config)
        handbook_context = handbook_result.response.strip()
    except Exception:
        handbook_context = "No information retrieved."
    
    # Single comprehensive synthesis prompt
    prompt = _GLOSSARY_ENTRY_PROMPT.format(
        entity_name=entity_name,
        domain=domain,
        handbook_context=handbook_context[:3000] if handbook_context else "No context",
        conceptual_context=conceptual_context[:2000] if conceptual_context else "No context",
        inventory_context=inventory_context[:1500] if inventory_context else "No context",
        reference_domains=", ".join(reference_domains),
    )
    
    # LLM synthesis using query_collections with empty collections (LLM only)
    try:
        synthesis_result = query_collections([], prompt, rag_config)
        response_text = synthesis_result.response.strip()
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        pass
    
    # Fallback: return basic structure
    return {
        "entity_name": entity_name,
        "domain": domain,
        "formal_definition": "",
        "business_context": "",
        "governance": [],
        "leanix_description": inventory_context[:500] if inventory_context else "",
        "related_entities": [],
        "data_stewards": "",
        "domain_validation": {"is_correct": True, "suggested_domain": ""},
        "sources": {
            "handbook": bool(handbook_context and "No information" not in handbook_context),
            "conceptual_model": bool(conceptual_context and "No information" not in conceptual_context),
            "inventory": bool(inventory_context and "No information" not in inventory_context),
        },
    }


def extract_entities_from_conceptual_model_simple(
    conceptual_collections: list[str],
    rag_config: RagConfig,
) -> list[dict]:
    """Extract entity list from conceptual model using AI-native approach."""
    
    query = """
List all entities in the conceptual data model with their domains.
Return as JSON array: [{"entity_name": "...", "domain": "...", "subgroup": "..."}]
Include ALL entities from all domains.
"""
    
    try:
        result = query_collections(conceptual_collections, query, rag_config)
        response = result.response.strip()
        
        json_match = re.search(r'\[.*\]', response, re.DOTALL)
        if json_match:
            entities = json.loads(json_match.group())
            return entities
    except Exception:
        pass
    
    # Fallback: return empty (will be populated by deterministic extractor if needed)
    return []


# ---------------------------------------------------------------------------
# Main Generation
# ---------------------------------------------------------------------------


def generate_ai_glossary(
    rag_config: RagConfig,
    conceptual_collections: list[str],
    inventory_collections: list[str],
    handbook_collections: list[str],
    output_dir: Path,
    domain_filter: str | None = None,
    entity_filter: str | None = None,
    model_override: str | None = None,
) -> None:
    """Generate business glossary using AI-native synthesis."""
    
    # Reference data architecture domains
    reference_domains = ["PARTY", "AGREEMENT", "PRODUCT", "CHANNEL", "ACCOUNTS", "ASSETS", "ADDITIONAL"]
    
    # Output path
    if domain_filter:
        domain_filter = domain_filter.upper()
        suffix = f"_{domain_filter.lower()}"
        conceptual_collections = [c for c in conceptual_collections if c.endswith(suffix)]
        if not conceptual_collections:
            print(f"\nERROR: No collection found for domain '{domain_filter}'.", file=sys.stderr)
            sys.exit(1)
        output_path = output_dir / f"fa_ai_glossary_{domain_filter.lower()}.json"
        print(f"\n  Domain filter: {domain_filter} ({len(conceptual_collections)} collection(s))")
    else:
        output_path = output_dir / "fa_ai_glossary.json"
    
    if entity_filter:
        print(f"  Entity filter: {entity_filter}")
    
    if model_override:
        rag_config.ollama.llm_model = model_override
    
    print("\n=== FA Business Glossary Generator (AI-Native) ===")
    print(f"  Model: {rag_config.ollama.llm_model}")
    print(f"  Collections:")
    print(f"    - Conceptual Model ({len(conceptual_collections)})")
    print(f"    - Inventory ({len(inventory_collections)})")
    print(f"    - Handbook ({len(handbook_collections)})")
    
    # Get entity list
    print("\n=== Step 1: Get Entity List ===")
    entities = extract_entities_from_conceptual_model_simple(conceptual_collections, rag_config)
    
    if domain_filter:
        entities = [e for e in entities if e.get("domain", "").upper() == domain_filter]
        print(f"  After domain filter ({domain_filter}): {len(entities)} entities")
    
    if entity_filter:
        entities = [e for e in entities if e.get("entity_name", "").lower() == entity_filter.lower()]
        if not entities:
            print(f"\nERROR: Entity '{entity_filter}' not found.", file=sys.stderr)
            sys.exit(1)
        print(f"  After entity filter: 1 entity")
    
    if not entities:
        print("\nWARNING: No entities found. Exiting.")
        return
    
    # Generate glossary entries
    print("\n=== Step 2: Generate Glossary Entries (AI-Native) ===")
    glossary_entries = []
    
    for i, entity in enumerate(entities, 1):
        entity_name = entity.get("entity_name", "")
        domain = entity.get("domain", "UNKNOWN")
        
        print(f"  [{i:>3}/{len(entities)}] {entity_name[:50]:<50}", end="\r", flush=True)
        
        entry = generate_glossary_entry(
            entity_name=entity_name,
            domain=domain,
            conceptual_collections=conceptual_collections,
            inventory_collections=inventory_collections,
            handbook_collections=handbook_collections,
            rag_config=rag_config,
            reference_domains=reference_domains,
        )
        
        glossary_entries.append(entry)
    
    print(f"  {len(glossary_entries)} glossary entries generated      ")
    
    # Write output
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(glossary_entries, f, indent=2, ensure_ascii=False)
    
    print(f"\n  Glossary (JSON) → {output_path}")
    
    # Quality metrics
    print("\n=== Quality Metrics ===")
    with_definitions = sum(1 for e in glossary_entries if e.get("formal_definition"))
    with_governance = sum(1 for e in glossary_entries if e.get("governance") and len(e["governance"]) > 0)
    print(f"  Entities with formal definitions: {with_definitions}/{len(glossary_entries)}")
    print(f"  Entities with governance rules: {with_governance}/{len(glossary_entries)}")
    
    # Source coverage
    handbook_coverage = sum(1 for e in glossary_entries if e.get("sources", {}).get("handbook"))
    conceptual_coverage = sum(1 for e in glossary_entries if e.get("sources", {}).get("conceptual_model"))
    inventory_coverage = sum(1 for e in glossary_entries if e.get("sources", {}).get("inventory"))
    print(f"\n=== Source Coverage ===")
    print(f"  FA Handbook: {handbook_coverage}/{len(glossary_entries)}")
    print(f"  Conceptual Model: {conceptual_coverage}/{len(glossary_entries)}")
    print(f"  LeanIX Inventory: {inventory_coverage}/{len(glossary_entries)}")


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="FA Business Glossary Generator (AI-Native) — minimal orchestration, maximum LLM synthesis"
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
        "--model",
        type=str,
        help="Override LLM model (e.g., qwen2.5:14b)",
    )
    
    args = parser.parse_args()
    
    # Load RAG config
    print("Loading RAG config…")
    rag_config = RagConfig.from_yaml(args.rag_config)
    print(f"  LLM: {rag_config.ollama.llm_model}")
    print(f"  num_queries: {rag_config.query.num_queries}")
    
    # Resolve collections
    print("\nResolving collections…")
    conceptual_collections = resolve_collection_prefixes(
        ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
    )
    inventory_collections = resolve_collection_prefixes(
        ["fa_leanix_global_inventory"], rag_config
    )
    handbook_collections = ["fa_handbook"]
    
    print(f"  Conceptual Model ({len(conceptual_collections)})")
    print(f"  Inventory ({len(inventory_collections)})")
    print(f"  Handbook: {'fa_handbook' if handbook_collections else 'NOT FOUND'}")
    
    # Ensure output directory exists
    args.output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate glossary
    generate_ai_glossary(
        rag_config=rag_config,
        conceptual_collections=conceptual_collections,
        inventory_collections=inventory_collections,
        handbook_collections=handbook_collections,
        output_dir=args.output_dir,
        domain_filter=args.domain,
        entity_filter=args.entity,
        model_override=args.model,
    )
    
    print("\n=== Complete ===")
    print(f"\nNext steps:")
    print(f"  1. Review {args.output_dir / 'fa_ai_glossary_*.json'} with Data Architects")
    print(f"  2. Validate domain mappings and governance rules")
    print(f"  3. Import to Purview or downstream systems")


if __name__ == "__main__":
    main()
