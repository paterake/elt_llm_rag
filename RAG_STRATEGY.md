# RAG Strategy

This document defines the Retrieval-Augmented Generation (RAG) strategy employed by `elt_llm_rag`.

## Overview

The system implements a **hybrid retrieval** strategy combining dense vector search, sparse keyword matching, and embedding-based reranking to maximise retrieval quality before LLM synthesis.

```
Query → Hybrid Retrieval (BM25 + Vector) → Embedding Reranker → Top-K Chunks → LLM → Answer
```

All retrieval steps — including LLM synthesis — are owned by `elt_llm_query`. Consumers (`elt_llm_consumer`, `elt_llm_api`) call into it and receive a completed `QueryResult`.

## Package Boundaries

```
┌──────────────────────────────────────────────────┐
│              elt_llm_core (shared)               │
│  models · vector_store · config · query_engine   │
└────────────┬──────────────────────┬──────────────┘
             │                      │
             ▼                      ▼
┌────────────────────┐   ┌──────────────────────────────────────┐
│   elt_llm_ingest   │   │           elt_llm_query              │
│  chunk · embed     │   │  1. Dense Vector (ChromaDB)          │
│  → ChromaDB        │   │  2. BM25 (DocStore)                  │
│  → DocStore        │   │  3. Hybrid Fusion (RRF)              │
└────────────────────┘   │  4. Embedding Reranker               │
                         │  5. LLM Synthesis  ← final step here │
                         └──────────┬───────────────────────────┘
                                    │  QueryResult
                    ┌───────────────┴────────────────┐
                    ▼                                ▼
       ┌────────────────────────┐     ┌─────────────────────┐
       │    elt_llm_consumer    │     │    elt_llm_api       │
       │  catalog · glossary    │     │  HTTP / Gradio UI    │
       │  coverage · handbook   │     └─────────────────────┘
       └────────────────────────┘
```

### Ingest vs Query responsibilities

| Module | Does | Does NOT do |
|--------|------|-------------|
| **`elt_llm_ingest`** | Chunk · embed · store in ChromaDB + DocStore | Retrieval · BM25 · reranking · querying |
| **`elt_llm_query`** | Dense + BM25 retrieval · hybrid fusion · reranking · LLM synthesis | Ingestion · embedding generation |

## Retrieval Pipeline (inside `elt_llm_query`)

### Step 1: Hybrid Retrieval

Two parallel retrievers fetch candidate chunks:

| Retriever | Technology | Strengths |
|-----------|------------|-----------|
| **Dense Vector** | LlamaIndex + ChromaDB | Finds conceptually related content even with different wording |
| **Sparse (BM25)** | llama-index-retrievers-bm25 + bm25s | Finds exact terms, acronyms, version numbers, structured data |

**Fusion**: `QueryFusionRetriever` in `reciprocal_rerank` mode combines both result sets, balancing semantic and keyword signals.

### Step 2: Embedding Reranker

The initial retrieval uses fast approximations (vector cosine similarity + BM25 scores). The reranker performs a more careful re-scoring pass:

1. Fetch top-20 candidates (`reranker_retrieve_k`)
2. Embed each chunk using Ollama (`nomic-embed-text`)
3. Compute query-document cosine similarity
4. Keep top-8 (`reranker_top_k`) for LLM context

**Why reranking matters**: Initial retrieval optimises for speed. Reranking optimises for relevance — ensuring the LLM receives the most pertinent chunks.

### Step 3: LLM Synthesis

The reranked chunks are passed to the LLM (via Ollama) with an optional system prompt. This is the final step executed inside `query_collection()` / `query_collections()` — the result is returned as a `QueryResult` to the caller.

## Configuration

Defined in `elt_llm_ingest/config/rag_config.yaml`:

```yaml
query:
  similarity_top_k: 8
  use_hybrid_search: true          # Combine BM25 + vector
  use_reranker: true               # Enable reranking
  reranker_strategy: "embedding"   # "embedding" | "cross-encoder"
  reranker_retrieve_k: 20          # Candidates before reranking
  reranker_top_k: 8                # Chunks passed to LLM
```

## Technologies

| Component | Technology | Notes |
|-----------|------------|-------|
| **Shared infrastructure** | `elt_llm_core` | Models, vector store, config, base query engine |
| **Dense Vector Store** | ChromaDB | `chromadb` + `llama-index-vector-stores-chroma` |
| **Sparse Retrieval** | BM25 | `bm25s` + `llama-index-retrievers-bm25` |
| **Embeddings** | Ollama | `nomic-embed-text` |
| **LLM** | Ollama | Local models (e.g. `qwen2.5:14b`, `llama3.1`, `mistral`) |
| **Reranking** | Embedding cosine similarity | Custom implementation via Ollama embeddings |

## Why This Strategy?

| Retriever | Weakness without hybrid |
|-----------|------------------------|
| **Vector-only** | Struggles with exact matches (version numbers, acronyms, IDs) |
| **BM25-only** | Misses semantic equivalence ("How do I join?" ≠ "Membership process") |

Combining both captures what either alone misses. The reranker then re-scores all candidates by genuine relevance so the LLM receives the highest-precision chunks.

## Retrieval Flow (Single Collection)

```
┌─────────────┐
│   Query     │
└──────┬──────┘
       │
       ├──→ [Vector Retriever] ──→ Top-K dense vectors
       │      (ChromaDB)
       │
       └──→ [BM25 Retriever] ────→ Top-K keyword matches
              (Docstore)
                    │
                    ↓
       ┌────────────────────────┐
       │  QueryFusionRetriever  │
       │  (reciprocal_rerank)   │
       └────────────┬───────────┘
                    │
                    ↓
       ┌────────────────────────┐
       │  Embedding Reranker    │
       │  (cosine similarity)   │
       └────────────┬───────────┘
                    │
                    ↓
       ┌────────────────────────┐
       │  LLM Synthesis (Ollama)│
       └────────────┬───────────┘
                    │
                    ↓
              QueryResult
```

## Multi-Collection Queries

When querying across multiple RAG collections (e.g. multiple LeanIX domains):

1. Retrieve `reranker_retrieve_k / num_collections` from each collection
2. Merge all candidates
3. Apply embedding reranker globally
4. Keep top-`reranker_top_k` overall

This ensures each collection has representation in the candidate pool while the reranker selects the most relevant overall.

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Vector retrieval | ~10–50ms | ChromaDB ANN search |
| BM25 retrieval | ~5–20ms | In-memory index |
| Embedding reranker | ~100–500ms | Ollama embedding (20 candidates) |
| LLM synthesis | ~1–5s | Depends on model and context size |

## Fallback Behaviour

| Condition | Fallback |
|-----------|----------|
| BM25 docstore missing | Vector-only retrieval |
| Reranker disabled | Direct top-K from fusion retriever |
| Ollama unavailable | Query fails (no cloud fallback) |

## Design Principles

1. **Local-first**: All embeddings and inference via Ollama — no external API dependencies
2. **Graceful degradation**: System functions with reduced quality if components are missing
3. **Precision over recall**: Reranking ensures only the most relevant chunks reach the LLM
4. **Transparency**: Retrieval scores and sources logged for debugging

## Future Enhancements

- [ ] Cross-encoder reranker support (higher quality, slower)
- [ ] Query rewriting/expansion before retrieval
- [ ] Metadata filtering (date ranges, document types, section numbers)
- [ ] Caching for repeated queries
- [ ] Evaluation harness for retrieval quality metrics

## References

- [ARCHITECTURE.md](ARCHITECTURE.md) — Full system architecture and package overview
- `elt_llm_core/src/elt_llm_core/query_engine.py` — Base query engine (shared infrastructure)
- `elt_llm_query/src/elt_llm_query/query.py` — Retrieval, reranking, and LLM synthesis
- `elt_llm_ingest/config/rag_config.yaml` — Configuration reference
