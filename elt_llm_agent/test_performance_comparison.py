#!/usr/bin/env python3
"""Performance comparison: Consumer vs Quality Gate for single entity.

Compares:
1. Consumer (elt_llm_consumer) - traditional approach (~60-90s per entity)
2. Quality Gate (elt_llm_agent) - hybrid approach with BM25 (~3-9s per entity)

Usage:
    uv run python test_performance_comparison.py
"""

import json
import time
from pathlib import Path

from elt_llm_agent import query_with_quality_gate
from elt_llm_consumer.fa_consolidated_catalog import _load_prompt
from elt_llm_query.query import query_collections
from elt_llm_core.config import load_config


def run_consumer_query(entity_name: str, domain: str = "PARTY") -> dict:
    """Run consumer-style query (what fa_consolidated_catalog.py does)."""
    print(f"\n{'='*80}")
    print(f"CONSUMER QUERY: {entity_name} ({domain})")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    # Load consumer prompt
    prompt = _load_prompt("handbook_context.yaml")
    prompt = prompt.format(entity_name=entity_name, domain=domain)
    
    # Load config
    rag_config = load_config(Path("elt_llm_ingest/config/rag_config.yaml"))
    
    # Query all handbook sections (slow - no BM25 optimization)
    from elt_llm_query.query import resolve_collection_prefixes
    all_sections = resolve_collection_prefixes(["fa_handbook"], rag_config)
    
    print(f"Querying {len(all_sections)} handbook sections...")
    
    result = query_collections(
        collection_names=all_sections,
        query=prompt,
        rag_config=rag_config,
        iterative=False,
    )
    
    elapsed = time.time() - start_time
    
    print(f"\nConsumer Result:")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Response length: {len(result.response)} chars")
    print(f"  Source nodes: {len(result.source_nodes)}")
    print(f"  Response (first 300 chars):")
    print(f"    {result.response[:300]}...")
    
    return {
        "method": "consumer",
        "entity": entity_name,
        "time": elapsed,
        "response": result.response,
        "source_nodes": len(result.source_nodes),
        "response_length": len(result.response),
    }


def run_quality_gate_query(entity_name: str, domain: str = "PARTY") -> dict:
    """Run quality gate query (hybrid approach with BM25)."""
    print(f"\n{'='*80}")
    print(f"QUALITY GATE QUERY: {entity_name} ({domain})")
    print(f"{'='*80}")
    
    start_time = time.time()
    
    # Query with quality gate (uses BM25 to find relevant sections)
    query = f"What does the FA Handbook say about {entity_name} in the {domain} domain? Provide definition, context, and governance rules."
    
    result = query_with_quality_gate(
        query=query,
        collection_names=["fa_handbook"],
        max_agent_iterations=5,
        verbose=True,  # Show BM25 and quality gate details
    )
    
    elapsed = time.time() - start_time
    
    print(f"\nQuality Gate Result:")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Path: {result['source']}")
    print(f"  Latency: {result['latency']}")
    
    if result["source"] == "classic_rag":
        qc = result["quality_check"]
        print(f"  Quality Check: passed={qc.passed}")
        print(f"    - Citations: {qc.has_citations}")
        print(f"    - Not empty: {not qc.is_empty}")
        print(f"    - Not too short: {not qc.is_too_short}")
        print(f"    - Not generic: {not qc.is_generic}")
        print(f"    - Confidence: {qc.confidence_score:.2f}")
        
        print(f"  Response (first 300 chars):")
        print(f"    {result['result'].response[:300]}...")
    else:
        print(f"  Agent was activated (quality gate failed)")
        print(f"  Response (first 300 chars):")
        print(f"    {result['result'].response[:300]}...")
    
    return {
        "method": "quality_gate",
        "entity": entity_name,
        "time": elapsed,
        "source": result["source"],
        "response": result["result"].response,
        "response_length": len(result["result"].response),
    }


def compare_results(consumer_result: dict, qg_result: dict) -> None:
    """Print side-by-side comparison."""
    print(f"\n{'='*80}")
    print("PERFORMANCE COMPARISON")
    print(f"{'='*80}")
    
    print(f"\n⏱️  LATENCY:")
    print(f"  Consumer:      {consumer_result['time']:.1f}s")
    print(f"  Quality Gate:  {qg_result['time']:.1f}s")
    
    speedup = consumer_result['time'] / qg_result['time'] if qg_result['time'] > 0 else 0
    print(f"  Speedup:       {speedup:.1f}x faster")
    print(f"  Time saved:    {consumer_result['time'] - qg_result['time']:.1f}s")
    
    print(f"\n📊 RESPONSE QUALITY:")
    print(f"  Consumer length:      {consumer_result['response_length']} chars")
    print(f"  Quality Gate length:  {qg_result['response_length']} chars")
    
    print(f"\n📚 SOURCES:")
    print(f"  Consumer source nodes:  {consumer_result['source_nodes']}")
    if qg_result["source"] == "classic_rag":
        # Source nodes not directly available in quality gate result
        print(f"  Quality Gate sources:   N/A (used BM25 section discovery)")
    
    print(f"\n🎯 PATH:")
    print(f"  Quality Gate path:  {qg_result['source']}")
    if qg_result["source"] == "classic_rag":
        print(f"  → Fast path (BM25 + Classic RAG)")
    else:
        print(f"  → Slow path (BM25 + Agent fallback)")
    
    print(f"\n💡 INSIGHT:")
    if speedup > 5:
        print(f"  ✓ Quality gate is {speedup:.1f}x faster - excellent!")
    elif speedup > 2:
        print(f"  ✓ Quality gate is {speedup:.1f}x faster - good improvement")
    else:
        print(f"  ⚠ Quality gate is only {speedup:.1f}x faster - modest improvement")


def main():
    """Run performance comparison."""
    print("\n" + "="*80)
    print("PERFORMANCE COMPARISON: Consumer vs Quality Gate")
    print("Single entity query - FA County (PARTY domain)")
    print("="*80)
    
    # Test entity
    entity_name = "FA County"
    domain = "PARTY"
    
    print(f"\nTesting entity: {entity_name} ({domain})")
    print(f"Expected:")
    print(f"  - Consumer: ~60-90s (queries all 40+ handbook sections)")
    print(f"  - Quality Gate: ~3-9s (BM25 finds 3-5 relevant sections)")
    
    # Run consumer query
    consumer_result = run_consumer_query(entity_name, domain)
    
    # Run quality gate query
    qg_result = run_quality_gate_query(entity_name, domain)
    
    # Compare results
    compare_results(consumer_result, qg_result)
    
    # Save results
    output_file = Path(".tmp/performance_comparison.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    comparison = {
        "entity": entity_name,
        "domain": domain,
        "consumer": consumer_result,
        "quality_gate": qg_result,
        "speedup": consumer_result["time"] / qg_result["time"] if qg_result["time"] > 0 else 0,
        "time_saved": consumer_result["time"] - qg_result["time"],
    }
    
    with open(output_file, "w") as f:
        json.dump(comparison, f, indent=2)
    
    print(f"\n💾 Results saved to: {output_file}")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"Entity: {entity_name}")
    print(f"Consumer time:      {consumer_result['time']:.1f}s")
    print(f"Quality Gate time:  {qg_result['time']:.1f}s")
    print(f"Speedup:            {comparison['speedup']:.1f}x faster")
    print(f"Time saved:         {comparison['time_saved']:.1f}s")
    print(f"\nFor 175 entities (full PARTY domain):")
    print(f"  Consumer total:      ~{consumer_result['time'] * 175 / 60:.0f} minutes")
    print(f"  Quality Gate total:  ~{qg_result['time'] * 175 / 60:.0f} minutes")
    print(f"  Time saved:          ~{(consumer_result['time'] - qg_result['time']) * 175 / 60:.0f} minutes")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
