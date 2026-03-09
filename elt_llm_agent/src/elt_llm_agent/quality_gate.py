"""Quality Gate for Hybrid Agentic RAG.

Implements fast, rule-based quality checks to decide whether to:
- Return classic RAG result (fast path: 2-6s)
- Activate agentic RAG (slow path: 10-30s)

Design Principle: "Don't pay for loops unless your task routinely fails in one pass."
(Towards Data Science, 2025)

Usage:
    from elt_llm_agent.quality_gate import query_with_quality_gate
    
    result = query_with_quality_gate("What does the FA Handbook say about Club Official?")
    
    if result["source"] == "classic_rag":
        print(f"Fast answer: {result['result'].response}")
    else:
        print(f"Agent answer: {result['result'].response}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from elt_llm_core.config import load_config

logger = logging.getLogger(__name__)


@dataclass
class QualityCheckResult:
    """Result of quality gate checks."""

    passed: bool
    has_citations: bool
    is_empty: bool
    is_too_short: bool
    is_generic: bool
    confidence_score: float = 0.0
    reasons: list[str] | None = None


def check_citations(result: Any) -> bool:
    """Check if result has source citations.

    Args:
        result: QueryResult from query_collections

    Returns:
        True if has source_nodes
    """
    has_citations = len(result.source_nodes) > 0
    logger.debug("Citation check: %d source nodes", len(result.source_nodes))
    return has_citations


def check_empty_content(result: Any) -> bool:
    """Check if result is empty or hedged.

    Args:
        result: QueryResult from query_collections

    Returns:
        True if response contains empty/hedged phrases
    """
    response_lower = result.response.lower()

    empty_phrases = [
        "not defined",
        "not documented",
        "not found",
        "not present",
        "no information",
        "unable to",
        "cannot find",
        "does not contain",
        "outside governance scope",
        "leanix_only",  # Consumer-specific marker
    ]

    is_empty = any(phrase in response_lower for phrase in empty_phrases)

    if is_empty:
        logger.debug("Empty content check: FAILED - contains hedged phrases")

    return is_empty


def check_response_length(result: Any, min_length: int = 100) -> bool:
    """Check if response is too short.

    Args:
        result: QueryResult from query_collections
        min_length: Minimum acceptable response length

    Returns:
        True if response is too short
    """
    is_too_short = len(result.response) < min_length

    if is_too_short:
        logger.debug(
            "Length check: FAILED - %d chars (min: %d)",
            len(result.response),
            min_length,
        )

    return is_too_short


def check_generic_response(result: Any) -> bool:
    """Check if response is generic/boilerplate.

    Args:
        result: QueryResult from query_collections

    Returns:
        True if response uses generic phrases
    """
    response_lower = result.response.lower()

    generic_phrases = [
        "the provided documents",
        "the handbook does not",
        "no entities found",
        "based on the provided context",
        "the documents do not mention",
        "there is no information",
    ]

    is_generic = any(phrase in response_lower for phrase in generic_phrases)

    if is_generic:
        logger.debug("Generic check: FAILED - uses boilerplate phrases")

    return is_generic


def calculate_confidence(result: Any) -> float:
    """Calculate confidence score based on source nodes.

    Args:
        result: QueryResult from query_collections

    Returns:
        Confidence score 0.0-1.0
    """
    if not hasattr(result, "source_nodes") or not result.source_nodes:
        return 0.0

    # Average score from source nodes
    scores = [node.score for node in result.source_nodes if hasattr(node, "score") and node.score]

    if not scores:
        return 0.5  # No scores available

    avg_score = sum(scores) / len(scores)

    # Normalize to 0-1 range (typical cosine similarity: 0.3-0.9)
    normalized = min(1.0, max(0.0, (avg_score - 0.3) / 0.6))

    return normalized


def run_quality_checks(result: Any) -> QualityCheckResult:
    """Run all quality checks on RAG result.

    Args:
        result: QueryResult from query_collections

    Returns:
        QualityCheckResult with pass/fail and details
    """
    has_citations = check_citations(result)
    is_empty = check_empty_content(result)
    is_too_short = check_response_length(result)
    is_generic = check_generic_response(result)
    confidence = calculate_confidence(result)

    # Pass gate if:
    # - Has citations AND
    # - Not empty/hedged AND
    # - Not too short AND
    # - Not generic
    passed = has_citations and not is_empty and not is_too_short and not is_generic

    # Build reasons list
    reasons = []
    if not has_citations:
        reasons.append("No citations")
    if is_empty:
        reasons.append("Empty/hedged content")
    if is_too_short:
        reasons.append("Response too short")
    if is_generic:
        reasons.append("Generic response")
    if passed:
        reasons.append("All checks passed")

    return QualityCheckResult(
        passed=passed,
        has_citations=has_citations,
        is_empty=is_empty,
        is_too_short=is_too_short,
        is_generic=is_generic,
        confidence_score=confidence,
        reasons=reasons,
    )


def query_with_quality_gate(
    query: str,
    collection_names: list[str] | None = None,
    max_agent_iterations: int = 5,
    verbose: bool = False,
) -> dict[str, Any]:
    """Query with quality gate — use classic RAG first, agent fallback.

    Implements hybrid agentic RAG pattern:
    1. Try classic RAG (fast path: 2-6s)
    2. Check quality (rule-based, <10ms)
    3. If quality fails, activate agent (slow path: 10-30s)

    Args:
        query: User query
        collection_names: Collections to query (default: ["fa_handbook"])
        max_agent_iterations: Max agent reasoning loops if fallback needed
        verbose: Enable detailed logging

    Returns:
        Dict with:
            - source: "classic_rag" or "agentic_rag"
            - result: QueryResult or AgentResponse
            - quality_check: QualityCheckResult (if classic_rag)
            - latency: Estimated latency category

    Example:
        >>> result = query_with_quality_gate(
        ...     "What does the FA Handbook say about Club Official?"
        ... )
        >>> print(f"Used: {result['source']}")
        >>> print(f"Latency: {result['latency']}")
    """
    from elt_llm_query.query import query_collections

    if collection_names is None:
        # Default to all FA Handbook sections - will use BM25 to find relevant ones
        collection_names = ["fa_handbook"]

    logger.info("Quality gate: Trying classic RAG first (query: %s...)", query[:50])

    # Load RAG config - use absolute path from project root
    # This file is at: elt_llm_rag/elt_llm_agent/src/elt_llm_agent/quality_gate.py
    # Config is at: elt_llm_rag/elt_llm_ingest/config/rag_config.yaml
    # Need 4 parent levels to get from quality_gate.py to project root
    project_root = Path(__file__).parent.parent.parent.parent
    rag_config_path = project_root / "elt_llm_ingest" / "config" / "rag_config.yaml"
    
    logger.debug("Loading RAG config from: %s", rag_config_path)
    rag_config = load_config(rag_config_path)
    
    # Resolve collection prefixes and use BM25 to find relevant sections (fast, no LLM)
    # This is critical for performance: FA Handbook has 40+ sections, querying all is slow
    from elt_llm_query.query import resolve_collection_prefixes, discover_relevant_sections
    
    # Step 1: Resolve prefixes (e.g., "fa_handbook" → all fa_handbook_* collections)
    all_collections = resolve_collection_prefixes(collection_names, rag_config)
    
    if not all_collections:
        logger.warning("No collections found for prefixes: %s", collection_names)
        # Fall back to agent
        return _activate_agent(query, max_agent_iterations, verbose)
    
    # Step 2: Use BM25 to find relevant sections (fast, 1-3s, no LLM)
    # Extract prefix from first collection (e.g., "fa_handbook_s01" → "fa_handbook")
    prefix = collection_names[0]
    relevant_sections = discover_relevant_sections(
        entity_name=query[:50],  # Use query as entity name for BM25
        section_prefix=prefix,
        rag_config=rag_config,
        threshold=0.0,  # Include any section with BM25 match
        bm25_top_k=3,  # Top 3 candidates per section
    )
    
    # Use relevant sections if found, otherwise use all collections
    if relevant_sections:
        resolved_collections = relevant_sections
        logger.info("BM25 found %d relevant sections: %s", len(resolved_collections), resolved_collections[:5])
    else:
        resolved_collections = all_collections
        logger.info("BM25 found no relevant sections, using all %d collections", len(resolved_collections))
    
    logger.info("Resolved collections: %s", resolved_collections)

    # STEP 1: Try classic RAG (fast path)
    try:
        rag_result = query_collections(
            collection_names=resolved_collections,
            query=query,
            rag_config=rag_config,
            iterative=False,
        )
    except Exception as e:
        logger.exception("Classic RAG failed - activating agent")
        # Classic RAG failed - go straight to agent
        return _activate_agent(query, max_agent_iterations, verbose)

    # STEP 2: Check quality (rule-based, <10ms)
    quality_result = run_quality_checks(rag_result)

    logger.info(
        "Quality gate: passed=%s, reasons=%s",
        quality_result.passed,
        quality_result.reasons,
    )

    if verbose:
        logger.info("Quality check details:")
        logger.info("  - Citations: %s", quality_result.has_citations)
        logger.info("  - Empty: %s", quality_result.is_empty)
        logger.info("  - Too short: %s", quality_result.is_too_short)
        logger.info("  - Generic: %s", quality_result.is_generic)
        logger.info("  - Confidence: %.2f", quality_result.confidence_score)

    # STEP 3: Return or fallback
    if quality_result.passed:
        logger.info("Quality gate: PASSED - returning classic RAG result (fast path)")
        return {
            "source": "classic_rag",
            "result": rag_result,
            "quality_check": quality_result,
            "latency": "fast (2-6s)",
        }
    else:
        logger.info(
            "Quality gate: FAILED (%s) - activating agent (slow path)",
            ", ".join(quality_result.reasons),
        )
        return _activate_agent(query, max_agent_iterations, verbose)


def _activate_agent(
    query: str,
    max_iterations: int,
    verbose: bool,
) -> dict[str, Any]:
    """Activate agentic RAG as fallback.

    Args:
        query: User query
        max_iterations: Max reasoning loops
        verbose: Enable detailed logging

    Returns:
        Dict with agent result
    """
    from elt_llm_agent import ReActAgent, AgentConfig

    logger.info("Activating ReAct agent (max_iterations=%d)", max_iterations)

    agent = ReActAgent(
        AgentConfig(
            model="qwen3.5:9b",
            max_iterations=max_iterations,
            verbose=verbose,
        )
    )

    agent_result = agent.query(query, include_trace=verbose)

    return {
        "source": "agentic_rag",
        "result": agent_result,
        "latency": "slow (10-30s)",
    }


def batch_query_with_quality_gate(
    queries: list[str],
    collection_names: list[str] | None = None,
    max_agent_iterations: int = 5,
) -> list[dict[str, Any]]:
    """Run multiple queries with quality gate.

    Args:
        queries: List of queries to process
        collection_names: Collections to query
        max_agent_iterations: Max agent loops for fallbacks

    Returns:
        List of result dicts (one per query)
    """
    results = []

    for i, query in enumerate(queries):
        logger.info("Query %d/%d: %s", i + 1, len(queries), query[:50])
        result = query_with_quality_gate(
            query=query,
            collection_names=collection_names,
            max_agent_iterations=max_agent_iterations,
            verbose=False,
        )
        results.append(result)

    # Summary
    classic_count = sum(1 for r in results if r["source"] == "classic_rag")
    agent_count = sum(1 for r in results if r["source"] == "agentic_rag")

    logger.info(
        "Batch complete: %d classic RAG, %d agentic RAG out of %d queries",
        classic_count,
        agent_count,
        len(queries),
    )

    return results
