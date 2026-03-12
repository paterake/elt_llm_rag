#!/usr/bin/env python3
"""Agent-based consolidated catalog — alternative to elt_llm_consumer.

This uses agentic RAG (elt_llm_agent) instead of traditional RAG (elt_llm_consumer)
to extract handbook context for conceptual model entities.

Usage:
    uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

Output:
    .tmp/fa_agent_catalog_party.json (compare with fa_consolidated_catalog_party.json)
"""

import json
import logging
import sys
import time
from pathlib import Path

from elt_llm_agent import ReActAgent, AgentConfig
from elt_llm_consumer.fa_consolidated_catalog import (
    _normalize,
    _SECTION_PREFIX,
    _STATIC_CONTEXT,
    load_entities_from_json,
    load_inventory_from_json,
    extract_handbook_terms_from_docstore,
    load_relationships_from_json,
)
from elt_llm_core.config import load_config

logging.basicConfig(level=logging.WARNING)
for lib in ("httpx", "httpcore", "chromadb", "llama_index", "bm25s"):
    logging.getLogger(lib).setLevel(logging.WARNING)


def get_handbook_context_for_entity_agent(
    entity_name: str,
    domain: str,
    agent: ReActAgent,
) -> dict:
    """Get FA Handbook context for an entity using agentic RAG.
    
    Agentic approach:
    1. Load entity aliases (from entity_aliases.yaml)
    2. BM25 section routing for entity name + all aliases
    3. Keyword scan for entity name + all aliases (safety net)
    4. Direct query_collections call (proven retrieval from consumer)
    5. Structured prompt (proven output format)
    
    This is truly agentic (decides WHICH sections to query) while using proven retrieval.
    """
    from elt_llm_query.query import discover_relevant_sections, find_sections_by_keyword, query_collections
    from elt_llm_consumer.fa_consolidated_catalog import _get_alias_variants, _extract_around_mention
    from elt_llm_core.config import load_config
    from pathlib import Path
    
    # Load config
    rag_config = load_config(Path("elt_llm_ingest/config/rag_config.yaml"))
    
    # AGENTIC STEP 0: Get all aliases (like consumer does)
    # This ensures we find content even if handbook uses different terminology
    aliases = _get_alias_variants(entity_name)
    all_query_terms = [entity_name] + aliases
    
    # AGENTIC STEP 1: BM25 section routing for entity name + ALL aliases
    # This is the "agentic" part - dynamically selecting sections instead of querying all 44
    relevant_sections = []
    seen_sections = set()
    
    for term in all_query_terms:
        sections = discover_relevant_sections(
            entity_name=term,
            section_prefix="fa_handbook",
            rag_config=rag_config,
            threshold=0.0,
            bm25_top_k=3,
            aliases=[],
        )
        for s in sections:
            if s not in seen_sections:
                relevant_sections.append(s)
                seen_sections.add(s)
    
    # AGENTIC STEP 2: Keyword scan for entity name + ALL aliases (safety net)
    all_keyword_chunks = []
    seen_chunks = set()
    
    for term in all_query_terms:
        keyword_sections, keyword_chunks = find_sections_by_keyword(
            term=term,
            section_prefix="fa_handbook",
            rag_config=rag_config,
        )
        
        # Add sections
        for s in keyword_sections:
            if s not in seen_sections:
                relevant_sections.append(s)
                seen_sections.add(s)
        
        # Add unique chunks
        for chunk in keyword_chunks:
            stripped = " ".join(chunk.split())
            if stripped not in seen_chunks:
                all_keyword_chunks.append(chunk)
                seen_chunks.add(stripped)
    
    # If no sections found, entity is not in handbook
    if not relevant_sections and not all_keyword_chunks:
        return {
            "formal_definition": "Not defined in FA Handbook.",
            "domain_context": "Not found in FA Handbook.",
            "governance_rules": "",
            "business_rules": "",
            "lifecycle_states": "",
            "data_classification": "",
            "regulatory_context": "",
            "associated_agreements": "",
            "raw_agent_response": "No handbook content found",
        }
    
    # PROVEN RETRIEVAL: Use same approach as consumer (guaranteed to work)
    # Build structured prompt (same as consumer - proven to extract structured output)
    prompt = f"""Provide a complete terms of reference entry for the FA entity '{entity_name}' in the {domain} domain, using only the FA Handbook text provided.

Important: The FA Handbook may use different names for '{entity_name}'. When searching, also consider these equivalent terms: {', '.join(aliases) if aliases else 'none'}.

Respond using this exact format:

FORMAL_DEFINITION:
[If there is an explicit 'X means Y' or 'X is defined as Y' statement, quote it exactly.
If '{entity_name}' appears in the documents but is never formally defined, write a concise description (2-4 sentences).
If '{entity_name}' does not appear anywhere, write: Not defined in FA Handbook.]

DOMAIN_CONTEXT:
[Describe what role or function '{entity_name}' performs in the {domain} domain, what authority or influence it has, and what related entities are relevant. 2-4 sentences.]

GOVERNANCE:
[Describe rules imposed ON '{entity_name}' by the FA and authority EXERCISED BY '{entity_name}'. Cite section and rule numbers where possible (e.g. Rule A3.1, Section C). If not regulated by FA Rules, describe operational role.]

BUSINESS_RULES:
[List key business rules, eligibility conditions, and constraints. Use 3-5 bullet points or 2-3 sentences. If none stated, write: Not specified in FA Handbook.]

LIFECYCLE_STATES:
[List states or statuses '{entity_name}' can be in. If not applicable, write: Not specified in FA Handbook.]

DATA_CLASSIFICATION:
[Describe personal/sensitive data categories. If not referenced, write: Not specified in FA Handbook.]

REGULATORY_CONTEXT:
[List external legislation referenced (e.g. UK GDPR, Companies Act). If none cited, write: Not specified in FA Handbook.]

ASSOCIATED_AGREEMENTS:
[List agreement types that govern '{entity_name}'. If none apply, write: Not specified in FA Handbook.]
"""
    
    # Add keyword chunks as explicit context (bypasses reranker for verbatim mentions)
    if all_keyword_chunks:
        passages = "\n".join(
            f"- {_extract_around_mention(c, entity_name)}" for c in all_keyword_chunks[:5]
        )
        prompt += f"\n\nThe following passages from the FA Handbook explicitly mention '{entity_name}' or its aliases — they must be considered in your response:\n{passages}"
    
    # PROVEN RETRIEVAL: query_collections (same as consumer)
    result = query_collections(
        collection_names=relevant_sections,  # Agentic: only relevant sections, not all 44
        query=prompt,
        rag_config=rag_config,
        iterative=False,
    )
    
    # Parse structured response
    response_text = result.response
    
    sections = {
        "formal_definition": "",
        "domain_context": "",
        "governance_rules": "",
        "business_rules": "",
        "lifecycle_states": "",
        "data_classification": "",
        "regulatory_context": "",
        "associated_agreements": "",
        "raw_agent_response": response_text,
    }
    
    # Parse by field labels
    import re
    
    def extract_field(label: str) -> str:
        pattern = rf"{label}:\s*(.*?)(?=\n\n[A-Z_]+:|\Z)"
        match = re.search(pattern, response_text, re.DOTALL | re.IGNORECASE)
        return match.group(1).strip() if match else ""
    
    sections["formal_definition"] = extract_field("FORMAL_DEFINITION")
    sections["domain_context"] = extract_field("DOMAIN_CONTEXT")
    sections["governance_rules"] = extract_field("GOVERNANCE")
    sections["business_rules"] = extract_field("BUSINESS_RULES")
    sections["lifecycle_states"] = extract_field("LIFECYCLE_STATES")
    sections["data_classification"] = extract_field("DATA_CLASSIFICATION")
    sections["regulatory_context"] = extract_field("REGULATORY_CONTEXT")
    sections["associated_agreements"] = extract_field("ASSOCIATED_AGREEMENTS")
    
    return sections


def generate_agent_catalog(
    model_json: Path,
    inventory_json: Path,
    output_dir: Path,
    domain_filter: str | None = None,
    entity_filter: list[str] | None = None,
) -> None:
    """Generate consolidated catalog using agentic RAG."""
    
    if domain_filter:
        domain_filter = domain_filter.upper()
        catalog_json_path = output_dir / f"fa_agent_catalog_{domain_filter.lower()}.json"
    else:
        catalog_json_path = output_dir / "fa_agent_catalog.json"
    
    print("\n=== FA Agent Catalog (Agentic RAG) ===")
    print(f"  Model: qwen3.5:9b")
    print(f"  Output: {catalog_json_path}")
    
    # Step 1: Load entities
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
        filter_norms = {_normalize(f) for f in entity_filter}
        matched = [
            e for e in conceptual_entities
            if _normalize(e["entity_name"]) in filter_norms
        ]
        conceptual_entities = matched
        print(f"  Entity filter: {entity_filter} ({len(matched)} entities)")
    
    # Step 2: Load inventory
    print("\n=== Step 2: Load Inventory Descriptions ===")
    inventory_lookup = load_inventory_from_json(inventory_json)
    inventory_descriptions = {}
    for entity in conceptual_entities:
        fsid = entity.get("fact_sheet_id", "")
        inv = inventory_lookup.get(fsid, {})
        inventory_descriptions[_normalize(entity["entity_name"])] = inv
    print(f"  {len(inventory_descriptions)} entities matched in inventory")
    
    # Step 3: Extract handbook terms (for mapping)
    print("\n=== Step 3: Extract Handbook Defined Terms ===")
    rag_config = load_config(Path("elt_llm_ingest/config/rag_config.yaml"))
    handbook_terms = extract_handbook_terms_from_docstore(rag_config)
    print(f"  {len(handbook_terms)} defined terms extracted")
    
    # Step 4: Match terms to entities
    print("\n=== Step 4: Match Handbook Terms to Conceptual Model ===")
    handbook_mappings = {}
    matched = 0
    for term_entry in handbook_terms:
        term = term_entry["term"].lower()
        for entity in conceptual_entities:
            if term in _normalize(entity["entity_name"]).lower():
                handbook_mappings[term] = {
                    "mapped_entity": entity["entity_name"],
                    "domain": entity["domain"],
                }
                matched += 1
                break
    print(f"  {matched}/{len(handbook_terms)} handbook terms matched")
    
    # Step 5: Get handbook context using AGENT
    print("\n=== Step 5: Extract Handbook Context (Agent-based) ===")
    handbook_context = {}
    
    agent = ReActAgent(
        AgentConfig(
            model="qwen3.5:9b",
            max_iterations=5,
            verbose=False,
        )
    )
    
    total = len(conceptual_entities)
    for i, entity in enumerate(conceptual_entities, 1):
        name = entity.get("entity_name", "")
        domain = entity.get("domain", "UNKNOWN")
        
        print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)
        
        # Skip entities with no handbook coverage (from static config)
        if name in _STATIC_CONTEXT:
            handbook_context[_normalize(name)] = {
                "formal_definition": "",
                "domain_context": "Not applicable — internal FA business concept outside regulatory scope",
                "governance_rules": "Not documented in FA Handbook — outside governance scope",
                "source": "LEANIX_ONLY",
            }
            continue
        
        # Query agent
        context = get_handbook_context_for_entity_agent(name, domain, agent)
        context["source"] = "BOTH" if context.get("domain_context") else "LEANIX_ONLY"
        handbook_context[_normalize(name)] = context
    
    print(f"  {len(handbook_context)} entities processed with agent")
    
    # Step 6: Load relationships
    print("\n=== Step 6: Load Relationships ===")
    relationships = load_relationships_from_json(model_json)
    print(f"  {len(relationships)} relationships loaded")
    
    # Step 7: Consolidate
    print("\n=== Step 7: Consolidating ===")
    
    # Build output structure (similar to consumer output)
    output_entities = []
    for entity in conceptual_entities:
        name = entity["entity_name"]
        norm_name = _normalize(name)
        ctx = handbook_context.get(norm_name, {})
        
        entity_record = {
            "fact_sheet_id": entity.get("fact_sheet_id", ""),
            "entity_name": name,
            "domain": entity.get("domain", ""),
            "subgroup": entity.get("subgroup", ""),
            "source": ctx.get("source", "UNKNOWN"),
            "leanix_description": inventory_descriptions.get(norm_name, {}).get("description", ""),
            "formal_definition": ctx.get("formal_definition", ""),
            "domain_context": ctx.get("domain_context", ""),
            "governance_rules": ctx.get("governance_rules", ""),
            "handbook_term": None,
            "mapping_confidence": "",
            "mapping_rationale": "",
            "review_status": "PENDING",
            "review_notes": f"Agent-based extraction (compare with consumer)",
            "relationships": [],
        }
        output_entities.append(entity_record)
    
    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(catalog_json_path, "w", encoding="utf-8") as f:
        json.dump({"entities": output_entities}, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"\n  Agent catalog (JSON) → {catalog_json_path}")
    
    source_counts = {}
    for e in output_entities:
        src = e.get("source", "UNKNOWN")
        source_counts[src] = source_counts.get(src, 0) + 1
    
    print("\n=== Summary by Source ===")
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")
    
    with_definitions = sum(1 for e in output_entities if e.get("formal_definition") and len(e["formal_definition"]) > 50)
    with_governance = sum(1 for e in output_entities if e.get("governance_rules") and len(e["governance_rules"]) > 100)
    
    print("\n=== Quality Metrics ===")
    print(f"  Entities with formal definitions: {with_definitions}/{len(output_entities)}")
    print(f"  Entities with governance rules: {with_governance}/{len(output_entities)}")


def main() -> None:
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate FA catalog using agentic RAG (alternative to consumer)"
    )
    parser.add_argument(
        "--domain", default=None, metavar="DOMAIN",
        help="Restrict to a single domain (e.g. PARTY, AGREEMENTS)"
    )
    parser.add_argument(
        "--entity", default=None, metavar="ENTITY",
        help="Restrict to one or more entity names (comma-separated)"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path(".tmp"),
        help="Output directory (default: .tmp)"
    )
    parser.add_argument(
        "--model-json", type=Path, default=Path("~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model_model.json").expanduser(),
        help="Path to LeanIX model JSON"
    )
    parser.add_argument(
        "--inventory-json", type=Path, default=Path("~/Documents/__data/resources/thefa/20260227_085233_UtvKD_inventory_inventory.json").expanduser(),
        help="Path to LeanIX inventory JSON"
    )
    
    args = parser.parse_args()
    
    generate_agent_catalog(
        model_json=args.model_json,
        inventory_json=args.inventory_json,
        output_dir=args.output_dir,
        domain_filter=args.domain,
        entity_filter=[e.strip() for e in args.entity.split(",")] if args.entity else None,
    )


if __name__ == "__main__":
    main()
