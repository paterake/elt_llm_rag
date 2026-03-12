"""Pure BM25 reranker — re-scores the candidate pool by keyword match.

This answers: "If we ranked by keyword relevance instead of embedding
cosine similarity, would the verbatim-match chunks rise to the top?"
"""
from __future__ import annotations

from elt_llm_core.config import RagConfig

from . import ChunkResult, RankingResult, _collection_label


def rank(
    query: str,
    candidate_pool: list,
    keyword_chunks: list[str],
    rag_config: RagConfig,
    entity_name: str = "",
) -> RankingResult:
    """Rerank candidate_pool using BM25 keyword scoring.

    Creates an in-memory BM25 index from the candidate pool nodes and scores
    them against entity_name (short, BM25-friendly) + the synthesis query.
    The max score across both queries is used so BM25 rewards both exact-match
    and relevant context chunks.

    Args:
        query:          Synthesis query string (used as second BM25 query).
        candidate_pool: NodeWithScore list from retriever.py.
        keyword_chunks: Verbatim keyword-scan chunk texts (Stage 1c).
        rag_config:     RAG configuration (provides reranker_top_k).
        entity_name:    Short entity name for BM25 exact-match query.
    """
    if not candidate_pool:
        return RankingResult(
            ranker="bm25", query=query,
            total_candidates=0, top_k_cutoff=rag_config.query.reranker_top_k,
            chunks=[],
        )

    try:
        from llama_index.retrievers.bm25 import BM25Retriever
        import logging as _logging
        _logging.getLogger("bm25s").setLevel(_logging.WARNING)
    except ImportError:
        print("  [ERROR] llama-index-retrievers-bm25 not installed")
        return RankingResult(
            ranker="bm25", query=query,
            total_candidates=len(candidate_pool),
            top_k_cutoff=rag_config.query.reranker_top_k,
            chunks=[],
        )

    keyword_set = {" ".join(t.split()) for t in keyword_chunks}
    nodes = [n.node for n in candidate_pool]
    k = len(nodes)

    bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=k)

    # Score each query variant, take max per node
    node_id_to_score: dict[str, float] = {}
    queries = [q for q in [entity_name, query] if q]

    for q in queries:
        hits = bm25.retrieve(q)
        for hit in hits:
            nid = hit.node.node_id
            score = hit.score or 0.0
            if nid not in node_id_to_score or score > node_id_to_score[nid]:
                node_id_to_score[nid] = score

    # Assign scores back to candidate pool (preserving original ordering for ties)
    scored = [
        (node_with_score, node_id_to_score.get(node_with_score.node.node_id, 0.0))
        for node_with_score in candidate_pool
    ]
    scored.sort(key=lambda x: x[1], reverse=True)

    top_k = rag_config.query.reranker_top_k
    chunks: list[ChunkResult] = []
    for rank_idx, (node_ws, score) in enumerate(scored, 1):
        text = node_ws.node.text or ""
        stripped = " ".join(text.split())
        chunks.append(ChunkResult(
            rank=rank_idx,
            score=round(float(score), 4),
            collection=_collection_label(node_ws.node),
            text_preview=stripped[:100],
            full_text=text,
            is_keyword_chunk=(stripped in keyword_set or any(
                " ".join(kw.split()) in stripped for kw in keyword_set if len(kw) > 30
            )),
        ))

    return RankingResult(
        ranker="bm25",
        query=query,
        total_candidates=len(candidate_pool),
        top_k_cutoff=top_k,
        chunks=chunks,
    )
