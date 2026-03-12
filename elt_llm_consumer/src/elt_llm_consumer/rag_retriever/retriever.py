"""Stage 1 + Stage 2 retrieval diagnostic.

Runs all retrieval stages and returns a RetrievalResult with:
  - Stage 1a: BM25 section scores per section (entity + aliases)
  - Stage 1c: verbatim keyword scan results
  - Stage 2:  hybrid candidate pool (pre-rerank NodeWithScore list)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_core.vector_store import get_docstore_path
from elt_llm_query.query import (
    find_sections_by_keyword,
    load_index,
    resolve_collection_prefixes,
    _build_hybrid_retriever,
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class SectionScore:
    collection: str
    score: float
    winning_variant: str  # which query variant achieved the max score


@dataclass
class RetrievalResult:
    entity_name: str
    aliases: list[str]
    # Stage 1a
    bm25_sections: list[SectionScore]
    # Stage 1c
    keyword_sections: list[str]
    keyword_chunks: list[str]
    # Stage 2
    unified_sections: list[str]   # merged set passed to hybrid retrieval
    candidate_pool: list          # NodeWithScore list — pre-rerank


# ---------------------------------------------------------------------------
# Stage 1a: BM25 section scoring (returns scores, unlike discover_relevant_sections)
# ---------------------------------------------------------------------------

def _score_sections_bm25(
    entity_name: str,
    aliases: list[str],
    section_prefix: str,
    rag_config: RagConfig,
    bm25_top_k: int = 3,
    threshold: float = 0.0,
) -> list[SectionScore]:
    """BM25-score every section collection for entity_name + aliases.

    Returns all sections that score above threshold, sorted by score descending.
    Includes the winning query variant so you can see whether the entity name or
    an alias drove the score.
    """
    try:
        from llama_index.core import StorageContext
        from llama_index.retrievers.bm25 import BM25Retriever
        import logging as _logging
        _logging.getLogger("bm25s").setLevel(_logging.WARNING)
    except ImportError:
        print("  [ERROR] llama-index-retrievers-bm25 not installed")
        return []

    all_collections = resolve_collection_prefixes([section_prefix], rag_config)
    section_pat = re.compile(rf'^{re.escape(section_prefix)}_s\d{{2}}$')
    section_collections = [c for c in all_collections if section_pat.match(c)]

    query_variants = [entity_name] + [a for a in aliases if a.lower() != entity_name.lower()]
    scored: list[SectionScore] = []

    for collection_name in sorted(section_collections):
        docstore_path = get_docstore_path(rag_config.chroma, collection_name)
        if not docstore_path.exists():
            continue
        try:
            from llama_index.core import StorageContext
            storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
            nodes = list(storage.docstore.docs.values())
            if not nodes:
                continue

            k = min(bm25_top_k, len(nodes))
            bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=k)

            max_score = 0.0
            winning_variant = ""
            for variant in query_variants:
                hits = bm25.retrieve(variant)
                if hits:
                    s = max((n.score for n in hits if n.score is not None), default=0.0)
                    if s > max_score:
                        max_score = s
                        winning_variant = variant

            if max_score >= threshold:
                scored.append(SectionScore(
                    collection=collection_name,
                    score=round(max_score, 4),
                    winning_variant=winning_variant,
                ))
        except Exception as e:
            print(f"  [WARN] BM25 scan failed for '{collection_name}': {e}")

    scored.sort(key=lambda x: x.score, reverse=True)
    return scored


# ---------------------------------------------------------------------------
# Stage 2: hybrid chunk retrieval (pre-rerank candidate pool)
# ---------------------------------------------------------------------------

def _retrieve_candidate_pool(
    unified_sections: list[str],
    query: str,
    rag_config: RagConfig,
) -> list:
    """Retrieve chunks from unified_sections using hybrid search.

    Mirrors the per-collection retrieval in query_collections() pooled mode
    but stops BEFORE the reranker — returns the raw candidate pool.

    Returns:
        List of NodeWithScore, sorted by fusion score descending.
    """
    from llama_index.core import StorageContext
    from llama_index.core.schema import NodeWithScore

    full_ctx_threshold = rag_config.query.full_context_max_chunks
    n_collections = max(len(unified_sections), 1)
    per_k = max(rag_config.query.reranker_retrieve_k // n_collections, 5)

    all_nodes: list = []

    for name in unified_sections:
        try:
            index = load_index(name, rag_config)
        except Exception as e:
            print(f"  [WARN] Could not load index '{name}': {e}")
            continue

        # Full-context for small sections (same logic as query_collections)
        docstore_path = get_docstore_path(rag_config.chroma, name)
        if full_ctx_threshold > 0 and docstore_path.exists():
            try:
                ds = StorageContext.from_defaults(persist_dir=str(docstore_path))
                doc_nodes = list(ds.docstore.docs.values())
                if 0 < len(doc_nodes) <= full_ctx_threshold:
                    all_nodes.extend(NodeWithScore(node=n, score=1.0) for n in doc_nodes)
                    continue
            except Exception:
                pass

        try:
            if rag_config.query.use_hybrid_search:
                retriever = _build_hybrid_retriever(index, name, rag_config, per_k)
            else:
                retriever = index.as_retriever(similarity_top_k=per_k)
            nodes = retriever.retrieve(query)
            all_nodes.extend(nodes)
        except Exception as e:
            print(f"  [WARN] Retrieval failed for '{name}': {e}")

    all_nodes.sort(key=lambda x: x.score or 0.0, reverse=True)
    return all_nodes


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_retrieval(
    entity_name: str,
    rag_config: RagConfig,
    aliases: list[str],
    section_prefix: str = "fa_handbook",
    bm25_top_k: int = 3,
    threshold: float = 0.0,
) -> RetrievalResult:
    """Run all retrieval stages for entity_name and return a RetrievalResult.

    Args:
        entity_name:    Conceptual model entity name.
        rag_config:     RAG configuration.
        aliases:        Alias variants from entity_aliases.yaml.
        section_prefix: ChromaDB section collection prefix.
        bm25_top_k:     BM25 candidates per section in Stage 1a.
        threshold:      Minimum BM25 score to include a section.
    """
    print(f"\n{'='*70}")
    print(f"  RETRIEVAL: {entity_name}")
    print(f"{'='*70}")

    # Stage 1a
    print(f"\nStage 1a — BM25 section routing")
    print(f"  Aliases used ({len(aliases)}): {', '.join(aliases[:8])}{'...' if len(aliases) > 8 else ''}")
    bm25_sections = _score_sections_bm25(
        entity_name, aliases, section_prefix, rag_config, bm25_top_k, threshold
    )
    print(f"  Sections found: {len(bm25_sections)}")
    for s in bm25_sections[:10]:
        print(f"    {s.collection:<35}  score={s.score:.4f}  via: '{s.winning_variant}'")
    if len(bm25_sections) > 10:
        print(f"    ... ({len(bm25_sections) - 10} more)")

    # Stage 1c
    print(f"\nStage 1c — Keyword scan (verbatim: '{entity_name}')")
    keyword_sections, keyword_chunks = find_sections_by_keyword(
        entity_name, section_prefix, rag_config
    )
    print(f"  Sections: {len(keyword_sections)}  |  Chunks: {len(keyword_chunks)}")
    for i, chunk in enumerate(keyword_chunks, 1):
        preview = " ".join(chunk.split())[:120]
        print(f"  [{i}] {preview}{'...' if len(chunk) > 120 else ''}")

    # Merge sections
    bm25_names = [s.collection for s in bm25_sections]
    seen: set[str] = set(bm25_names)
    unified = list(bm25_names)
    for s in keyword_sections:
        if s not in seen:
            unified.append(s)
            seen.add(s)

    print(f"\nUnified section pool: {len(unified)} sections → {unified}")

    # Stage 2: build synthesis query
    query = (
        f"Entity: {entity_name}\n"
        f"Provide the formal definition, domain context, and governance rules "
        f"for '{entity_name}' as described in the FA Handbook."
    )

    print(f"\nStage 2 — Hybrid retrieval (pre-rerank)")
    if not unified:
        print("  No sections in pool — skipping retrieval")
        candidate_pool = []
    else:
        candidate_pool = _retrieve_candidate_pool(unified, query, rag_config)
        print(f"  Candidate pool: {len(candidate_pool)} chunks")

    return RetrievalResult(
        entity_name=entity_name,
        aliases=aliases,
        bm25_sections=bm25_sections,
        keyword_sections=keyword_sections,
        keyword_chunks=keyword_chunks,
        unified_sections=unified,
        candidate_pool=candidate_pool,
    )
