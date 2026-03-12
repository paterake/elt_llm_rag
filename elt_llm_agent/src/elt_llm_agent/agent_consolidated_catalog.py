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
    """Get FA Handbook context for an entity using agentic RAG."""
    
    query = f"What does the FA Handbook say about {entity_name} in the {domain} domain? Provide definition, context, and governance rules."
    
    response = agent.query(query, include_trace=False)
    
    # Parse agent response into structured fields
    # (Agent returns natural language, we extract structured fields)
    response_text = response.response
    
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
    
    # Simple extraction: split by paragraphs
    # (In production, would use LLM to parse into structured fields)
    paragraphs = [p.strip() for p in response_text.split("\n\n") if p.strip()]
    
    if paragraphs:
        # First paragraph often contains definition/context
        sections["domain_context"] = paragraphs[0][:500]
        
        # Remaining paragraphs often contain governance/rules
        if len(paragraphs) > 1:
            sections["governance_rules"] = "\n\n".join(paragraphs[1:])[:1000]
    
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
