#!/usr/bin/env python3
"""Compare Consumer vs Agent for the same entity queries.

Usage:
    uv run --package elt-llm-agent python -m elt_llm_agent.test_consumer_vs_agent
"""

import json
import time
from pathlib import Path

from elt_llm_agent import ReActAgent, AgentConfig


def load_consumer_results() -> list[dict]:
    """Load consumer output from .tmp/fa_consolidated_catalog_party.json."""
    catalog_file = Path(".tmp/fa_consolidated_catalog_party.json")
    if not catalog_file.exists():
        print(f"❌ File not found: {catalog_file}")
        print("Run: uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY")
        return []
    
    with open(catalog_file, "r") as f:
        catalog = json.load(f)
    
    # Extract PARTY Individual entities
    party = catalog.get("PARTY", {}).get("subtypes", {}).get("Individual", {}).get("entities", [])
    print(f"Loaded {len(party)} PARTY Individual entities from consumer output")
    return party


def query_entity_with_agent(entity_name: str) -> dict:
    """Query a single entity using the agent."""
    agent = ReActAgent(
        AgentConfig(
            model="qwen3.5:9b",
            max_iterations=5,
            verbose=False,
        )
    )
    
    query = f"What does the FA Handbook say about {entity_name}? Provide definition, context, and governance rules."
    
    start = time.time()
    response = agent.query(query, include_trace=False)
    elapsed = time.time() - start
    
    return {
        "entity_name": entity_name,
        "agent_response": response.response,
        "tool_calls": response.tool_calls,
        "elapsed_time": elapsed,
    }


def compare_entity(consumer_entity: dict, agent_result: dict) -> dict:
    """Compare consumer vs agent output for a single entity."""
    comparison = {
        "entity_name": consumer_entity["entity_name"],
        "consumer": {
            "source": consumer_entity.get("source", "UNKNOWN"),
            "definition_length": len(consumer_entity.get("formal_definition", "")),
            "governance_length": len(consumer_entity.get("governance_rules", "")),
            "has_definition": bool(consumer_entity.get("formal_definition")),
            "has_governance": bool(consumer_entity.get("governance_rules")),
        },
        "agent": {
            "response_length": len(agent_result.get("agent_response", "")),
            "tool_calls": len(agent_result.get("tool_calls", [])),
            "elapsed_time": agent_result.get("elapsed_time", 0),
            "has_response": bool(agent_result.get("agent_response")),
        },
    }
    return comparison


def print_comparison(comparison: dict) -> None:
    """Print side-by-side comparison."""
    print(f"\n{'='*80}")
    print(f"ENTITY: {comparison['entity_name']}")
    print(f"{'='*80}")
    
    print(f"\n📊 CONSUMER:")
    print(f"  Source: {comparison['consumer']['source']}")
    print(f"  Definition: {comparison['consumer']['definition_length']} chars")
    print(f"  Governance: {comparison['consumer']['governance_length']} chars")
    
    print(f"\n🤖 AGENT:")
    print(f"  Response: {comparison['agent']['response_length']} chars")
    print(f"  Tool calls: {comparison['agent']['tool_calls']}")
    print(f"  Time: {comparison['agent']['elapsed_time']:.1f}s")
    
    # Quick verdict
    if comparison['consumer']['source'] == 'LEANIX_ONLY':
        print(f"\n⚠️  CONSUMER: No handbook coverage (LEANIX_ONLY)")
        if comparison['agent']['has_response']:
            print(f"✅ AGENT: Found handbook content!")
        else:
            print(f"⚠️  AGENT: Also no handbook content")
    else:
        print(f"\n✅ CONSUMER: Has handbook coverage (BOTH)")
        if comparison['agent']['has_response']:
            print(f"✅ AGENT: Also found handbook content")


def main():
    """Run comparison test."""
    print("="*80)
    print("CONSUMER VS AGENT COMPARISON TEST")
    print("="*80)
    
    # Load consumer results
    consumer_entities = load_consumer_results()
    if not consumer_entities:
        return
    
    # Select test entities (mix of BOTH and LEANIX_ONLY)
    test_entities = [
        e for e in consumer_entities
        if e['entity_name'] in [
            "Club Official",      # BOTH - well-defined
            "Player",             # BOTH - rich governance
            "Employees",          # BOTH - referenced not defined
            "Customer",           # LEANIX_ONLY - thin coverage
            "Casual & Contingent Labourers",  # LEANIX_ONLY - no coverage
        ]
    ]
    
    if not test_entities:
        test_entities = consumer_entities[:5]  # Fallback to first 5
    
    print(f"\nTesting {len(test_entities)} entities with Agent...")
    
    results = []
    for entity in test_entities:
        print(f"\n{'='*80}")
        print(f"Querying agent: {entity['entity_name']}")
        print(f"{'='*80}")
        
        # Query with agent
        agent_result = query_entity_with_agent(entity['entity_name'])
        
        # Compare
        comparison = compare_entity(entity, agent_result)
        results.append(comparison)
        
        # Print comparison
        print_comparison(comparison)
        
        # Save intermediate result
        output_file = Path(f".tmp/comparison_{entity['entity_name'].replace(' ', '_').lower()}.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump({
                "consumer": entity,
                "agent": agent_result,
                "comparison": comparison,
            }, f, indent=2)
        print(f"\n💾 Saved to: {output_file}")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    
    print(f"\nTested: {len(results)} entities")
    print(f"Output files: .tmp/comparison_*.json")
    
    # Aggregate stats
    consumer_both = sum(1 for r in results if r['consumer']['source'] == 'BOTH')
    consumer_leanix_only = sum(1 for r in results if r['consumer']['source'] == 'LEANIX_ONLY')
    agent_with_response = sum(1 for r in results if r['agent']['has_response'])
    
    print(f"\nConsumer breakdown:")
    print(f"  BOTH (handbook coverage): {consumer_both}")
    print(f"  LEANIX_ONLY (no handbook): {consumer_leanix_only}")
    
    print(f"\nAgent breakdown:")
    print(f"  With response: {agent_with_response}/{len(results)}")
    
    avg_time = sum(r['agent']['elapsed_time'] for r in results) / len(results) if results else 0
    print(f"  Avg query time: {avg_time:.1f}s")
    
    print(f"\n💾 Detailed results:")
    print(f"  ls -la .tmp/comparison_*.json")


if __name__ == "__main__":
    main()
