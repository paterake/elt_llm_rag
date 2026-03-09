#!/usr/bin/env python3
"""Test script: Compare Agent vs Consumer for the same entity queries.

This script takes entities from the PARTY domain and queries them using
the agent instead of the consumer pipeline, to compare output quality.

Usage:
    uv run python -m elt_llm_agent.test_agent_vs_consumer
"""

import json
from pathlib import Path

from elt_llm_agent import ReActAgent, AgentConfig


def load_party_entities() -> list[dict]:
    """Load PARTY domain entities from consumer output."""
    catalog_file = Path(".tmp/fa_consolidated_catalog_party.json")
    if not catalog_file.exists():
        print(f"❌ File not found: {catalog_file}")
        print("Run: uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY")
        return []
    
    with open(catalog_file, "r") as f:
        catalog = json.load(f)
    
    # Extract entities from nested structure
    entities = []
    party_data = catalog.get("PARTY", {})
    subtypes = party_data.get("subtypes", {})
    
    for subtype_name, subtype_data in subtypes.items():
        for entity in subtype_data.get("entities", []):
            entity["_subtype"] = subtype_name
            entities.append(entity)
    
    print(f"Loaded {len(entities)} PARTY domain entities from consumer output")
    return entities


def test_entity_with_agent(entity_name: str, domain: str, subtype: str) -> dict:
    """Query a single entity using the agent."""
    agent = ReActAgent(
        AgentConfig(
            model="qwen3.5:9b",
            max_iterations=8,
            verbose=False,
        )
    )
    
    query = f"What does the FA Handbook say about {entity_name} in the {domain} domain? Provide definition, context, and governance rules."
    
    print(f"\n{'='*60}")
    print(f"Entity: {entity_name} ({subtype})")
    print(f"Query: {query}")
    print(f"{'='*60}")
    
    response = agent.query(query, include_trace=True)
    
    result = {
        "entity_name": entity_name,
        "domain": domain,
        "subtype": subtype,
        "agent_response": response.response,
        "tool_calls": response.tool_calls,
        "reasoning_trace": response.reasoning_trace,
    }
    
    # Print summary
    print(f"\nAgent Response (first 500 chars):")
    print(response.response[:500])
    print(f"\nTool calls: {len(response.tool_calls)}")
    for tc in response.tool_calls:
        print(f"  - {tc['tool']} (step {tc['step']})")
    
    return result


def compare_outputs(consumer_entity: dict, agent_result: dict) -> None:
    """Print side-by-side comparison."""
    print(f"\n{'='*80}")
    print("COMPARISON")
    print(f"{'='*80}")
    
    print(f"\n📋 CONSUMER OUTPUT:")
    print(f"  Source: {consumer_entity.get('source', 'UNKNOWN')}")
    print(f"  Handbook Term: {consumer_entity.get('handbook_term', 'None')}")
    print(f"  Formal Definition (first 200 chars):")
    print(f"    {consumer_entity.get('formal_definition', 'N/A')[:200]}")
    print(f"  Governance Rules (first 200 chars):")
    print(f"    {consumer_entity.get('governance_rules', 'N/A')[:200]}")
    
    print(f"\n🤖 AGENT OUTPUT:")
    print(f"  Tool Calls: {len(agent_result['tool_calls'])}")
    for tc in agent_result['tool_calls']:
        print(f"    - {tc['tool']}")
    print(f"  Response (first 400 chars):")
    print(f"    {agent_result['agent_response'][:400]}")
    
    print(f"\n📊 QUALITY CHECK:")
    consumer_has_def = len(consumer_entity.get('formal_definition', '')) > 50
    agent_has_response = len(agent_result['agent_response']) > 100
    print(f"  Consumer has definition: {'✅ Yes' if consumer_has_def else '❌ No'}")
    print(f"  Agent has response: {'✅ Yes' if agent_has_response else '❌ No'}")


def main():
    """Run comparison test."""
    print("="*80)
    print("AGENT VS CONSUMER COMPARISON TEST")
    print("="*80)
    
    # Load entities from consumer output
    entities = load_party_entities()
    if not entities:
        return
    
    # Filter to interesting cases (LEANIX_ONLY or thin coverage)
    interesting = [
        e for e in entities 
        if e.get('source') == 'LEANIX_ONLY' or not e.get('formal_definition')
    ][:5]  # Test first 5
    
    if not interesting:
        interesting = entities[:5]  # Fallback to first 5
    
    print(f"\nTesting {len(interesting)} entities with Agent...")
    print("These are entities where Consumer returned LEANIX_ONLY or empty definitions")
    
    results = []
    for entity in interesting:
        agent_result = test_entity_with_agent(
            entity['entity_name'],
            entity.get('domain', 'PARTY'),
            entity.get('_subtype', 'Unknown'),
        )
        results.append(agent_result)
        
        # Compare
        compare_outputs(entity, agent_result)
        
        # Save intermediate result
        output_file = Path(f".tmp/agent_test_{entity['entity_name'].replace(' ', '_').lower()}.json")
        with open(output_file, "w") as f:
            json.dump({
                "consumer": entity,
                "agent": agent_result,
            }, f, indent=2)
        print(f"\n💾 Saved comparison to: {output_file}")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Tested: {len(results)} entities")
    print(f"Output files: .tmp/agent_test_*.json")
    print(f"\nTo review:")
    print(f"  ls -la .tmp/agent_test_*.json")
    print(f"  cat .tmp/agent_test_club_official.json  # Example")


if __name__ == "__main__":
    main()
