# elt_llm_core — Architecture

## Purpose
- Provides shared infrastructure for the workspace: configuration loading, Ollama model adapters, ChromaDB client/helpers, and the lightweight query engine wrapper.

**See also**: [RAG_STRATEGY.md](../RAG_STRATEGY.md) for detailed documentation on the hybrid retrieval and reranking strategy.

## Components
- Configuration ([config.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_core/src/elt_llm_core/config.py))
  - Dataclasses for `ChromaConfig`, `OllamaConfig`, `ChunkingConfig`, `QueryConfig`, `RagConfig`
  - YAML → dataclass mapping with fields:
    - Query: `similarity_top_k`, `use_hybrid_search`, `use_reranker`, `reranker_strategy`, `reranker_retrieve_k`, `reranker_top_k`, `reranker_model`, `num_queries`, `use_mmr`, `mmr_threshold`, `use_lost_in_middle`, `system_prompt`
    - Chunking: `strategy`, `chunk_size`, `chunk_overlap`, `sentence_split_threshold`
- Models ([models.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_core/src/elt_llm_core/models.py))
  - Embeddings: `OllamaEmbedding` (e.g., `nomic-embed-text`)
  - LLM: `Ollama` (e.g., `qwen3.5:9b`)
  - Utilities: connectivity and model-availability checks
- Vector Store ([vector_store.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_core/src/elt_llm_core/vector_store.py))
  - Persistent Chroma client (tenant/database/collection)
  - Storage context factory
  - Docstore path resolution for BM25 hybrid retrieval
  - Collection discovery and prefix resolution
- Query Engine ([query_engine.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_core/src/elt_llm_core/query_engine.py))
  - Creates a `RetrieverQueryEngine` bound to a retriever (vector or hybrid)
  - Sets `Settings.llm` once per query using the configured Ollama LLM

## Interactions
1. Ingestion sets `Settings.embed_model` using `create_embedding_model`, then writes vectors to Chroma and nodes to the docstore.
2. Query loads indices from Chroma, builds a hybrid retriever when enabled, and uses the core query engine to synthesize grounded answers.

## Configuration Reference

**File**: `elt_llm_ingest/config/rag_config.yaml`

For current parameter values and tuning rationale, see [RAG_TUNING.md](../RAG_TUNING.md).

## Guarantees
- Local-first operation: all inference via Ollama; no external dependencies required for the embedding reranker.
- Safe defaults with graceful fallbacks (vector-only retrieval if BM25/docstore missing; skip reranker if disabled).

