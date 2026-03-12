"""Embedding cosine-similarity reranker (current production approach).

Mirrors _rerank_nodes_embedding() in elt_llm_query.query exactly.
"""
from __future__ import annotations

from elt_llm_core.config import RagConfig
from elt_llm_query.query import _rerank_nodes_embedding

from . import ChunkResult, RankingResult, _collection_label


def rank(
    query: str,
    candidate_pool: list,
    keyword_chunks: list[str],
    rag_config: RagConfig,
) -> RankingResult:
    """Rerank candidate_pool by embedding cosine similarity (production behaviour).

    Args:
        query:          Synthesis query string.
        candidate_pool: NodeWithScore list from retriever.py.
        keyword_chunks: Verbatim keyword-scan chunk texts (Stage 1c).
        rag_config:     RAG configuration (provides reranker_top_k).

    Returns:
        RankingResult with all chunks ranked, keyword chunk positions annotated.
    """
    if not candidate_pool:
        return RankingResult(
            ranker="embedding", query=query,
            total_candidates=0, top_k_cutoff=rag_config.query.reranker_top_k,
            chunks=[],
        )

    keyword_set = {" ".join(t.split()) for t in keyword_chunks}

    reranked = _rerank_nodes_embedding(query, candidate_pool, rag_config)

    # Build full ranked list (all candidates, not just top-k)
    # _rerank_nodes_embedding returns top_k already — re-score all for diagnostics
    import numpy as np
    from elt_llm_core.models import create_embedding_model

    embed_model = create_embedding_model(rag_config.ollama)
    query_emb = np.array(embed_model.get_text_embedding(query))
    texts = [n.node.text for n in candidate_pool]
    doc_embs = np.array(embed_model.get_text_embedding_batch(texts))

    query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-9)
    doc_norms = doc_embs / (np.linalg.norm(doc_embs, axis=1, keepdims=True) + 1e-9)
    scores = doc_norms @ query_norm

    ranked_pairs = sorted(zip(candidate_pool, scores), key=lambda x: float(x[1]), reverse=True)

    top_k = rag_config.query.reranker_top_k
    chunks: list[ChunkResult] = []
    for rank_idx, (node, score) in enumerate(ranked_pairs, 1):
        text = node.node.text or ""
        stripped = " ".join(text.split())
        chunks.append(ChunkResult(
            rank=rank_idx,
            score=round(float(score), 4),
            collection=_collection_label(node.node),
            text_preview=stripped[:100],
            full_text=text,
            is_keyword_chunk=(stripped in keyword_set or any(
                " ".join(kw.split()) in stripped for kw in keyword_set if len(kw) > 30
            )),
        ))

    return RankingResult(
        ranker="embedding",
        query=query,
        total_candidates=len(candidate_pool),
        top_k_cutoff=top_k,
        chunks=chunks,
    )
