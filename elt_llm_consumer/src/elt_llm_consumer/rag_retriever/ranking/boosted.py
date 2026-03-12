"""Boosted reranker — embedding cosine similarity + forced keyword chunk injection.

This is Option C: run the embedding reranker as normal, then unconditionally
inject any keyword chunks that didn't make the top-k cutoff.  The LLM sees
the reranker's best picks PLUS the verbatim-match passages it might have missed.

This answers: "Does forcing the keyword chunks through fix the synthesis gap
without needing to change the ranking strategy entirely?"
"""
from __future__ import annotations

import numpy as np

from elt_llm_core.config import RagConfig
from elt_llm_core.models import create_embedding_model
from llama_index.core.schema import NodeWithScore

from . import ChunkResult, RankingResult, _collection_label


def rank(
    query: str,
    candidate_pool: list,
    keyword_chunks: list[str],
    rag_config: RagConfig,
) -> RankingResult:
    """Embedding reranker + forced injection of keyword chunks.

    Process:
      1. Score all candidates by cosine similarity (same as embedding.py).
      2. Take top_k normally.
      3. For each keyword chunk not already in top_k, append it.
      4. Report which chunks were forced in (they're the fix).

    Args:
        query:          Synthesis query string.
        candidate_pool: NodeWithScore list from retriever.py.
        keyword_chunks: Verbatim keyword-scan chunk texts (Stage 1c).
        rag_config:     RAG configuration.
    """
    top_k = rag_config.query.reranker_top_k
    keyword_set = {" ".join(t.split()) for t in keyword_chunks}

    if not candidate_pool:
        return RankingResult(
            ranker="boosted", query=query,
            total_candidates=0, top_k_cutoff=top_k,
            chunks=[],
        )

    # Score all candidates
    embed_model = create_embedding_model(rag_config.ollama)
    query_emb = np.array(embed_model.get_text_embedding(query))
    texts = [n.node.text for n in candidate_pool]
    doc_embs = np.array(embed_model.get_text_embedding_batch(texts))

    query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-9)
    doc_norms = doc_embs / (np.linalg.norm(doc_embs, axis=1, keepdims=True) + 1e-9)
    scores = doc_norms @ query_norm

    ranked_pairs = sorted(zip(candidate_pool, scores), key=lambda x: float(x[1]), reverse=True)

    def _is_kw(text: str) -> bool:
        stripped = " ".join(text.split())
        return stripped in keyword_set or any(
            " ".join(kw.split()) in stripped for kw in keyword_set if len(kw) > 30
        )

    # Build full ChunkResult list with embedding ranks
    chunks: list[ChunkResult] = []
    for rank_idx, (node_ws, score) in enumerate(ranked_pairs, 1):
        text = node_ws.node.text or ""
        stripped = " ".join(text.split())
        chunks.append(ChunkResult(
            rank=rank_idx,
            score=round(float(score), 4),
            collection=_collection_label(node_ws.node),
            text_preview=stripped[:100],
            full_text=text,
            is_keyword_chunk=_is_kw(text),
        ))

    # Effective cutoff: top_k base + forced keyword chunks beyond the cutoff
    top_k_chunks = chunks[:top_k]
    dropped = chunks[top_k:]

    forced_in = [c for c in dropped if c.is_keyword_chunk]
    effective_cutoff = top_k + len(forced_in)

    # Re-number so forced chunks appear at the end of the "passed" band
    # (visual only — the rank field still reflects embedding order)
    if forced_in:
        print(f"\n  Boosted: {len(forced_in)} keyword chunk(s) forced past cutoff:")
        for c in forced_in:
            print(f"    Embedding rank {c.rank} → forced into LLM context")
            print(f"    Text: {c.text_preview[:100]}")

    return RankingResult(
        ranker="boosted",
        query=query,
        total_candidates=len(candidate_pool),
        top_k_cutoff=effective_cutoff,
        chunks=chunks,
    )
