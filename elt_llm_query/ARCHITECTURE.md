# elt_llm_query — Architecture

## Purpose
Query local RAG collections with hybrid retrieval (BM25 + vector), optional embedding reranking, and single-pass LLM synthesis over combined context.

**See also**: [RAG_STRATEGY.md](../RAG_STRATEGY.md) for detailed documentation on the hybrid retrieval and reranking strategy.

## Retrieval Pipeline ([query.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_query/src/elt_llm_query/query.py))
1. Load `VectorStoreIndex` from ChromaDB for each target collection
2. Build retriever:
   - Vector-only by default
   - Hybrid (BM25 + vector) when docstore exists (`use_hybrid_search: true`)
   - Reciprocal Rank Fusion to merge candidate lists
3. Candidate pool size:
   - `similarity_top_k` (default)
   - `reranker_retrieve_k` when reranker enabled
4. Reranking:
   - `reranker_strategy: "embedding"` — cosine similarity using Ollama embeddings (no external downloads)
   - `reranker_top_k` retained for LLM synthesis
5. Synthesis:
   - Single LLM call (Ollama `llm_model`), optional `system_prompt`, with all top-k nodes merged across collections

## Profiles
- Located at [llm_rag_profile/](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_query/llm_rag_profile)
- Each profile defines:
  - Collections or `collection_prefixes` (resolved dynamically from Chroma)
  - Optional per-profile `similarity_top_k`, `system_prompt`
  - Use cases (e.g., FA enterprise architecture, Handbook only, DAMA only)

## Commands
```bash
# List profiles
uv run python -m elt_llm_query.runner --list

# Interactive session
uv run python -m elt_llm_query.runner --cfg <profile>

# Single query
uv run python -m elt_llm_query.runner --cfg <profile> -q "Your question"
```

## Notes
- Local-first: embeddings and LLM via Ollama (e.g., `nomic-embed-text`, `qwen2.5:14b`)
- Hybrid retrieval requires a persisted docstore created at ingest time
- Reranker improves ordering most when `reranker_retrieve_k` is larger (e.g., 20–30) and `reranker_top_k` is small (5–8)

