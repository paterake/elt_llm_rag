#!/usr/bin/env python3
"""Test the Quality Gate for Hybrid Agentic RAG.

Demonstrates:
1. Classic RAG (fast path) for queries with good results
2. Agent fallback (slow path) for queries with poor results
3. Quality check details

Usage:
    uv run python test_quality_gate.py
"""

import logging
from pathlib import Path

from elt_llm_agent.quality_gate import (
    query_with_quality_gate,
    run_quality_checks,
    batch_query_with_quality_gate,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Test queries
TEST_QUERIES = [
    # These should PASS quality gate (classic RAG - fast)
    ("What is a Club according to the FA Handbook?", "Should pass - well-defined entity"),
    ("What are the governance rules for Match Officials?", "Should pass - specific governance"),
    ("What does the FA Handbook say about Player registration?", "Should pass - clear topic"),
    
    # These might FAIL quality gate (agent fallback - slow)
    ("What does the FA Handbook say about Club Official?", "Might fail - thin coverage"),
    ("Tell me about Board & Committee Members", "Might fail - not in handbook"),
    ("What are the rules for Coach Developers?", "Might fail - niche role"),
]


def test_single_query():
    """Test single query with quality gate."""
    print("="*80)
    print("TEST 1: Single Query with Quality Gate")
    print("="*80)
    
    query = "What does the FA Handbook say about Club?"
    print(f"\nQuery: {query}")
    print("-"*80)
    
    result = query_with_quality_gate(
        query=query,
        collection_names=["fa_handbook"],
        max_agent_iterations=5,
        verbose=True,  # Show quality check details
    )
    
    print(f"\n✓ Result:")
    print(f"  Source: {result['source']}")
    print(f"  Latency: {result['latency']}")
    
    if result["source"] == "classic_rag":
        print(f"\n  Quality Check:")
        qc = result["quality_check"]
        print(f"    Passed: {qc.passed}")
        print(f"    Citations: {qc.has_citations}")
        print(f"    Not empty: {not qc.is_empty}")
        print(f"    Not too short: {not qc.is_too_short}")
        print(f"    Not generic: {not qc.is_generic}")
        print(f"    Confidence: {qc.confidence_score:.2f}")
        
        print(f"\n  Response (first 300 chars):")
        print(f"    {result['result'].response[:300]}...")
    else:
        print(f"\n  Agent was activated (quality gate failed)")
        print(f"  Response (first 300 chars):")
        print(f"    {result['result'].response[:300]}...")
    
    print("\n")


def test_quality_check_details():
    """Show detailed quality check breakdown."""
    print("="*80)
    print("TEST 2: Quality Check Details")
    print("="*80)
    
    from elt_llm_query.query import query_collections
    from elt_llm_core.config import load_config
    
    # Load config - use absolute path
    # This file is at: elt_llm_rag/test_quality_gate.py
    # Config is at: elt_llm_rag/elt_llm_ingest/config/rag_config.yaml
    project_root = Path(__file__).parent  # Already in project root
    rag_config = load_config(project_root / "elt_llm_ingest" / "config" / "rag_config.yaml")
    
    # Query that should fail
    query = "What does the FA Handbook say about Club Official?"
    print(f"\nQuery: {query}")
    print("-"*80)
    
    result = query_collections(
        collection_names=["fa_handbook"],
        query=query,
        rag_config=rag_config,
        iterative=False,
    )
    
    # Run quality checks
    qc = run_quality_checks(result)
    
    print(f"\nQuality Check Results:")
    print(f"  ✓ Passed: {qc.passed}")
    print(f"  ✓ Has citations: {qc.has_citations}")
    print(f"  ✗ Is empty: {qc.is_empty}")
    print(f"  ✗ Is too short: {qc.is_too_short}")
    print(f"  ✗ Is generic: {qc.is_generic}")
    print(f"  ✓ Confidence: {qc.confidence_score:.2f}")
    print(f"\n  Reasons: {', '.join(qc.reasons)}")
    
    print(f"\n  Response (first 400 chars):")
    print(f"    {result.response[:400]}...")
    print("\n")


def test_batch_queries():
    """Test batch of queries with quality gate."""
    print("="*80)
    print("TEST 3: Batch Queries with Quality Gate")
    print("="*80)
    
    queries = [q[0] for q in TEST_QUERIES[:4]]  # First 4 queries
    
    print(f"\nProcessing {len(queries)} queries...")
    print("-"*80)
    
    results = batch_query_with_quality_gate(
        queries=queries,
        collection_names=["fa_handbook"],
        max_agent_iterations=5,
    )
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    
    classic_count = sum(1 for r in results if r["source"] == "classic_rag")
    agent_count = sum(1 for r in results if r["source"] == "agentic_rag")
    
    print(f"\nTotal queries: {len(results)}")
    print(f"  Classic RAG (fast): {classic_count} ({classic_count/len(results)*100:.0f}%)")
    print(f"  Agentic RAG (slow): {agent_count} ({agent_count/len(results)*100:.0f}%)")
    
    print(f"\nDetailed Results:")
    for i, (query, result) in enumerate(zip(queries, results), 1):
        source = result["source"]
        latency = result["latency"]
        print(f"\n{i}. {query[:60]}...")
        print(f"   Source: {source}, Latency: {latency}")
        
        if source == "classic_rag":
            qc = result["quality_check"]
            status = "✓ PASS" if qc.passed else "✗ FAIL"
            print(f"   Quality: {status} (confidence: {qc.confidence_score:.2f})")


def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("QUALITY GATE TEST SUITE")
    print("Hybrid Agentic RAG: Classic RAG (fast) → Agent (slow fallback)")
    print("="*80 + "\n")
    
    # Test 1: Single query
    test_single_query()
    
    # Test 2: Quality check details
    test_quality_check_details()
    
    # Test 3: Batch queries
    test_batch_queries()
    
    print("\n" + "="*80)
    print("TESTS COMPLETE")
    print("="*80)
    print("\nKey Insights:")
    print("  - Quality gate routes queries to fast (classic RAG) or slow (agent) path")
    print("  - Fast path: 2-6s, returns if has citations + good content")
    print("  - Slow path: 10-30s, activated when quality checks fail")
    print("  - Rule-based checks: <10ms overhead")
    print("\nNext: Review which queries triggered agent fallback")
    print("      Those are candidates for LLM query planning enhancement\n")


if __name__ == "__main__":
    main()
