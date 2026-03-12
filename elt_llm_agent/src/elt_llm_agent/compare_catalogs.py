#!/usr/bin/env python3
"""Compare consumer vs agent catalog outputs.

Usage:
    uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
"""

import json
from pathlib import Path


def load_catalog(catalog_file: Path) -> dict:
    """Load catalog JSON file."""
    if not catalog_file.exists():
        print(f"❌ File not found: {catalog_file}")
        return None
    
    with open(catalog_file, "r") as f:
        return json.load(f)


def compare_catalogs(consumer_catalog: dict, agent_catalog: dict) -> None:
    """Compare consumer vs agent catalog outputs."""
    
    # Extract entities from both catalogs
    if "entities" in agent_catalog:
        agent_entities = agent_catalog["entities"]
    else:
        # Consumer has nested structure
        agent_entities = []
        for domain_data in agent_catalog.values():
            if isinstance(domain_data, dict) and "subtypes" in domain_data:
                for subtype_data in domain_data["subtypes"].values():
                    agent_entities.extend(subtype_data.get("entities", []))
    
    if "entities" in consumer_catalog:
        consumer_entities = consumer_catalog["entities"]
    else:
        consumer_entities = []
        for domain_data in consumer_catalog.values():
            if isinstance(domain_data, dict) and "subtypes" in domain_data:
                for subtype_data in domain_data["subtypes"].values():
                    consumer_entities.extend(subtype_data.get("entities", []))
    
    print(f"\nConsumer entities: {len(consumer_entities)}")
    print(f"Agent entities: {len(agent_entities)}")
    
    # Build lookup by entity name
    consumer_lookup = {e["entity_name"]: e for e in consumer_entities}
    agent_lookup = {e["entity_name"]: e for e in agent_entities}
    
    # Compare
    print(f"\n{'='*80}")
    print("ENTITY-BY-ENTITY COMPARISON")
    print(f"{'='*80}")
    
    matches = 0
    consumer_better = 0
    agent_better = 0
    both_empty = 0
    
    for entity_name in sorted(set(consumer_lookup.keys()) | set(agent_lookup.keys())):
        consumer = consumer_lookup.get(entity_name, {})
        agent = agent_lookup.get(entity_name, {})
        
        consumer_def = len(consumer.get("formal_definition", ""))
        agent_def = len(agent.get("formal_definition", ""))
        consumer_gov = len(consumer.get("governance_rules", ""))
        agent_gov = len(agent.get("governance_rules", ""))
        
        consumer_source = consumer.get("source", "UNKNOWN")
        agent_source = agent.get("source", "UNKNOWN")
        
        # Determine winner
        if consumer_def > 50 and agent_def > 50 and consumer_gov > 100 and agent_gov > 100:
            result = "✅ BOTH GOOD"
            matches += 1
        elif consumer_def < 10 and agent_def < 10 and consumer_gov < 50 and agent_gov < 50:
            result = "⚠️  BOTH EMPTY"
            both_empty += 1
        elif (consumer_def > 50 or consumer_gov > 100) and (agent_def < 10 and agent_gov < 50):
            result = "📊 CONSUMER BETTER"
            consumer_better += 1
        elif (agent_def > 50 or agent_gov > 100) and (consumer_def < 10 and consumer_gov < 50):
            result = "🤖 AGENT BETTER"
            agent_better += 1
        else:
            result = "✅ COMPARABLE"
            matches += 1
        
        if result not in ("✅ BOTH GOOD", "✅ COMPARABLE"):
            print(f"\n{entity_name}:")
            print(f"  Consumer: source={consumer_source}, def={consumer_def}, gov={consumer_gov}")
            print(f"  Agent:    source={agent_source}, def={agent_def}, gov={agent_gov}")
            print(f"  Result:   {result}")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Total entities compared: {len(set(consumer_lookup.keys()) | set(agent_lookup.keys()))}")
    print(f"✅ Both good: {matches}")
    print(f"⚠️  Both empty: {both_empty}")
    print(f"📊 Consumer better: {consumer_better}")
    print(f"🤖 Agent better: {agent_better}")


def main():
    """Run catalog comparison."""
    print("="*80)
    print("CONSUMER VS AGENT CATALOG COMPARISON")
    print("="*80)
    
    # Load catalogs
    print("\nLoading consumer catalog...")
    consumer_catalog = load_catalog(Path(".tmp/fa_consolidated_catalog_party.json"))
    
    print("\nLoading agent catalog...")
    agent_catalog = load_catalog(Path(".tmp/fa_agent_catalog_party.json"))
    
    if not consumer_catalog or not agent_catalog:
        print("\n❌ Cannot compare - one or both catalogs missing")
        print("\nRun these first:")
        print("  uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY")
        print("  uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY")
        return
    
    # Compare
    compare_catalogs(consumer_catalog, agent_catalog)
    
    print(f"\n💾 Detailed comparison files:")
    print(f"  ls -la .tmp/comparison_*.json")


if __name__ == "__main__":
    main()
