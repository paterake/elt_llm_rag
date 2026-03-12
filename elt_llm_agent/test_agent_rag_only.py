#!/usr/bin/env python3
"""Test: Compare Agent (RAG-only mode) vs Consumer for the same entity queries.

This script tests the agent using only RAG queries (no JSON lookup dependency)
to compare with what the consumer produces.

Usage:
    uv run python test_agent_rag_only.py
"""

from elt_llm_agent import ReActAgent, AgentConfig
from elt_llm_query.query import query_collections


def test_with_agent(entity_name: str) -> str:
    """Query entity using agent with RAG-only tool."""
    agent = ReActAgent(
        AgentConfig(
            model="qwen3.5:9b",
            max_iterations=5,
            verbose=False,
        )
    )
    
    query = f"What does the FA Handbook say about {entity_name}? Provide definition, context, and governance rules with section citations."
    
    print(f"\n{'='*80}")
    print(f"AGENT QUERY: {query}")
    print(f"{'='*80}")
    
    response = agent.query(query, include_trace=False)
    
    print(f"\nAGENT RESPONSE:")
    print(response.response)
    
    return response.response


def test_with_direct_rag(entity_name: str) -> str:
    """Query entity using direct RAG (same as consumer)."""
    from elt_llm_consumer.fa_consolidated_catalog import _load_prompt
    
    prompt = _load_prompt("handbook_context.yaml")
    prompt = prompt.format(entity_name=entity_name, domain="PARTY")
    
    print(f"\n{'='*80}")
    print(f"DIRECT RAG QUERY (consumer approach): {prompt[:100]}...")
    print(f"{'='*80}")
    
    result = query_collections(
        collections=["fa_handbook"],
        query=prompt,
        num_queries=1,  # Same as agent
    )
    
    print(f"\nDIRECT RAG RESPONSE:")
    print(result.response)
    
    return result.response


def main():
    """Run comparison test."""
    print("="*80)
    print("AGENT (RAG-only) VS CONSUMER COMPARISON")
    print("="*80)
    
    # Test entities from PARTY domain
    test_entities = [
        "Club Official",
        "Match Official", 
        "Club",
        "Player",
    ]
    
    for entity in test_entities:
        print(f"\n\n{'#'*80}")
        print(f"# TESTING: {entity}")
        print(f"{'#'*80}")
        
        # Agent approach
        agent_response = test_with_agent(entity)
        
        # Direct RAG approach (consumer)
        rag_response = test_with_direct_rag(entity)
        
        # Save results
        import json
        from pathlib import Path
        
        output = {
            "entity": entity,
            "agent_response": agent_response,
            "rag_response": rag_response,
        }
        
        output_file = Path(f".tmp/test_compare_{entity.replace(' ', '_').lower()}.json")
        with open(output_file, "w") as f:
            json.dump(output, f, indent=2)
        
        print(f"\n💾 Saved to: {output_file}")


if __name__ == "__main__":
    main()
