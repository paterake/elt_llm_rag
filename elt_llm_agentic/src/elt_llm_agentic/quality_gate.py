"""Quality-gated retrieval — fast-path RAG with agentic fallback.

Pattern:
  1. Run query_collections (naive RAG, fast: ~2–6s)
  2. Evaluate response quality with lightweight rules
  3. If quality passes → return fast result immediately
  4. If quality fails → fall back to AgenticRetriever (~10–30s)

This is the recommended production entry point for single ad-hoc queries:
it gives the speed of naive RAG in the common case (answer already in top-k
chunks) and the thoroughness of agentic retrieval when needed (sparse entity,
terminology mismatch, generic response).

Usage:
    from elt_llm_agentic.quality_gate import quality_gated_query

    result = quality_gated_query(
        entity_name="Club Official",
        domain="PARTY",
        aliases=["officer", "director"],
        rag_config=rag_config,
        collections=handbook_collections,
    )
    print(result["response"])
    print(result["path"])   # "fast" or "agentic"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Quality evaluation
# ---------------------------------------------------------------------------

_GENERIC_PHRASES = (
    "i don't have enough information",
    "i cannot find",
    "no information available",
    "not mentioned in the",
    "the provided text does not",
    "i was unable to",
    "empty response",
    "based on the context provided, i cannot",
)

_NEGATIVE_DEFINITIONS = (
    "not defined in fa handbook",
    "not defined in the fa handbook",
    "no formal definition",
    "the provided handbook documents do not contain",
)


@dataclass
class QualityResult:
    """Outcome of a quality gate evaluation."""

    passed: bool
    score: float           # 0.0–1.0
    reasons: list[str]     # Why it passed or failed


def evaluate_quality(response: str, min_length: int = 150) -> QualityResult:
    """Evaluate whether a RAG response is substantive enough to return.

    Checks:
    - Non-empty and above minimum length
    - Contains at least one section/rule citation (Rule X, Section N)
    - Doesn't lead with known generic/negative phrases
    - Doesn't exclusively consist of "Not specified in FA Handbook" boilerplate

    Args:
        response:   LLM response text to evaluate
        min_length: Minimum character count to pass (default: 150)

    Returns:
        QualityResult with pass/fail, score, and reasons
    """
    if not response or not response.strip():
        return QualityResult(passed=False, score=0.0, reasons=["empty response"])

    text = response.strip()
    lower = text.lower()
    reasons: list[str] = []
    score = 0.0

    # Length check
    if len(text) >= min_length:
        score += 0.3
    else:
        reasons.append(f"too short ({len(text)} < {min_length} chars)")

    # Has citations
    has_citation = bool(
        re.search(r"\b(rule\s+[A-Z]\d|section\s+\d|s\d{2}\b|rule\s+e\d)", lower)
        or re.search(r"\b(article\s+\d|clause\s+\d|paragraph\s+\d)", lower)
    )
    if has_citation:
        score += 0.3
        reasons.append("has citations")
    else:
        reasons.append("no rule/section citations found")

    # Generic phrase check
    is_generic = any(lower.strip().startswith(p) or p in lower[:300] for p in _GENERIC_PHRASES)
    if not is_generic:
        score += 0.2
    else:
        reasons.append("starts with generic/negative phrase")

    # Negative definition check (only fail if the entire response is boilerplate)
    is_negative_def = any(p in lower for p in _NEGATIVE_DEFINITIONS)
    boilerplate_only = is_negative_def and len(text) < 300
    if not boilerplate_only:
        score += 0.2
    else:
        reasons.append("response is negative definition boilerplate only")

    passed = score >= 0.5 and len(text) >= min_length and not is_generic and not boilerplate_only
    return QualityResult(passed=passed, score=round(score, 2), reasons=reasons)


# ---------------------------------------------------------------------------
# Quality-gated query
# ---------------------------------------------------------------------------


def quality_gated_query(
    entity_name: str,
    domain: str,
    aliases: list[str] | None = None,
    rag_config: Any = None,
    collections: list[str] | None = None,
    rag_config_path: Path = Path("elt_llm_ingest/config/rag_config.yaml"),
    min_quality_score: float = 0.5,
    verbose: bool = False,
) -> dict:
    """Run naive RAG first; fall back to AgenticRetriever if quality is low.

    Args:
        entity_name:       Entity to retrieve context for
        domain:            Domain (e.g. "PARTY")
        aliases:           Known alias terms for the entity
        rag_config:        Pre-loaded RagConfig (loaded from rag_config_path if None)
        collections:       Collections to query (BM25-routed if None)
        rag_config_path:   Path to rag_config.yaml (used if rag_config is None)
        min_quality_score: Minimum score to accept fast-path result (default: 0.5)
        verbose:           Print path taken and quality score

    Returns:
        dict with keys:
            response (str), path ("fast" | "agentic"),
            quality_score (float), quality_reasons (list[str]),
            entity_name (str), domain (str)
    """
    from elt_llm_core.config import load_config
    from elt_llm_query.query import query_collections, discover_relevant_sections

    aliases = aliases or []

    if rag_config is None:
        rag_config = load_config(rag_config_path)

    # --- Fast path: naive RAG ---
    if not collections:
        from elt_llm_consumer.fa_consolidated_catalog import _get_alias_variants
        all_aliases = _get_alias_variants(entity_name)
        collections = discover_relevant_sections(
            entity_name=entity_name,
            section_prefix="fa_handbook",
            rag_config=rag_config,
            threshold=0.0,
            bm25_top_k=3,
            aliases=all_aliases,
        )

    fast_query = f"What is '{entity_name}' in the FA Handbook? Provide its definition, domain context, and governance rules."
    fast_result = None
    fast_response = ""

    try:
        fast_result = query_collections(collections, fast_query, rag_config, iterative=False)
        fast_response = fast_result.response.strip()
    except Exception as e:
        logger.warning("Fast-path query failed: %s", e)

    quality = evaluate_quality(fast_response)

    if verbose:
        print(f"  [quality_gate] fast path: score={quality.score} passed={quality.passed}")
        print(f"    reasons: {quality.reasons}")

    if quality.passed and quality.score >= min_quality_score:
        return {
            "response": fast_response,
            "path": "fast",
            "quality_score": quality.score,
            "quality_reasons": quality.reasons,
            "entity_name": entity_name,
            "domain": domain,
        }

    # --- Agentic fallback ---
    if verbose:
        print(f"  [quality_gate] fast path insufficient (score={quality.score}) → agentic fallback")

    from elt_llm_agentic.retriever import AgenticRetriever, RetrieverConfig

    retriever = AgenticRetriever(RetrieverConfig(
        max_iterations=5,
        rag_config_path=rag_config_path,
        verbose=verbose,
    ))
    ctx = retriever.retrieve_entity_context(entity_name, domain, aliases=aliases)

    # Combine fields into a single response string for uniform return type
    parts = []
    for label, key in [
        ("FORMAL_DEFINITION", "formal_definition"),
        ("DOMAIN_CONTEXT", "domain_context"),
        ("GOVERNANCE", "governance_rules"),
        ("BUSINESS_RULES", "business_rules"),
    ]:
        v = ctx.get(key, "").strip()
        if v and not v.lower().startswith("not specified"):
            parts.append(f"{label}:\n{v}")

    agentic_response = "\n\n".join(parts) if parts else fast_response

    return {
        "response": agentic_response,
        "path": "agentic",
        "quality_score": quality.score,
        "quality_reasons": quality.reasons,
        "entity_name": entity_name,
        "domain": domain,
        "agentic_context": ctx,
    }
