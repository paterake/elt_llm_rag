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

## Enhancement Backlog

Strategies are grouped by pipeline stage and prioritised for this stack (FA Handbook regulatory text + LeanIX structured EA data).

### Priority

| Priority | Strategy | Stage | Effort | Why it matters here |
|----------|----------|-------|--------|---------------------|
| **High** | Query decomposition / multi-query | Query | Low — `num_queries` config | Consumer queries are compound (multi-entity, multi-domain) |
| **High** | MMR (Maximal Marginal Relevance) | Query | Low — mode flag | Prevents top-8 being near-duplicate adjacent paragraphs |
| **High** | Metadata enrichment + filtering | Ingest + Query | Medium | Prerequisite for scoped queries; section/type/source filtering |
| **Medium** | Parent-child chunking | Ingest | Medium — re-ingest | Preserves full rule context for FA Handbook regulatory text |
| **Medium** | Cross-encoder reranker | Reranking | Medium — local model | Higher reranking quality than embedding cosine similarity |
| **Medium** | GraphRAG | Ingest + Query | High | LeanIX is a native graph; relationship traversal answers what flat retrieval cannot |
| **Medium** | RAGAS evaluation harness | Eval | Medium | Objective quality baseline; measures impact of config changes |
| **Lower** | Lost-in-the-middle mitigation | Context | Low — reorder only | Zero latency cost; improves LLM attention across larger context windows |
| **Lower** | Caching | Query | Low | Eliminates repeat latency for identical queries |
| **Lower** | HyDE (query-time) | Query | Low — one extra LLM call | Helps vague/exploratory queries; BM25 already handles keyword queries |
| **Lower** | Sentence window retrieval | Ingest | Low-Medium | Lightweight alternative to parent-child chunking |
| **Lower** | Proposition chunking | Ingest | Medium | Atomic facts improve precision; good for LeanIX entity definitions |
| **Lower** | HyDE ingest variant | Ingest | Medium — LLM at ingest | Bridges formal document language vs informal query vocabulary |
| **Lower** | Time-weighted retrieval | Query | Low | Deprioritises stale LeanIX export versions after refresh |
| **Lower** | LLM-as-reranker | Reranking | Low-Medium | Highest reranking quality; too slow for default path |
| **Lower** | Context compression | Context | Medium | Reduces token noise in top-K chunks before LLM sees them |
| **Lower** | Map-Reduce / Refine synthesis | Context | Medium | Handles context overflow when querying many collections |
| **Lower** | Structured output + citations | LLM | Low — prompt change | Improves consumer parsing reliability; adds source auditability |
| **Lower** | Self-RAG / CRAG | LLM | High | Corrective re-retrieval for multi-hop questions spanning Handbook + LeanIX |
| **Lower** | FLARE | LLM | High | Iterative retrieval during generation for long-form answers |

---

### Ingestion Strategies

**Hierarchical / Parent-Child Chunking**
Store small chunks for precise retrieval; expand to the parent chunk for LLM context. LlamaIndex supports this natively (`HierarchicalNodeParser` + `AutoMergingRetriever`). High value for FA Handbook where rules span multiple sentences.

**Sentence Window Retrieval**
Index individual sentences but return surrounding context (e.g. ±2 sentences) when a sentence is retrieved. Lower overhead than full parent-child, similar benefit.

**Proposition Chunking**
Decompose each chunk into atomic factual statements at ingest time. Better retrieval precision — you retrieve a single fact rather than a paragraph containing it. Good for LeanIX entity definitions.

**Hypothetical Question Generation (HyDE — ingest variant)**
For each chunk, generate 3–5 questions that chunk would answer; embed those questions alongside the chunk. Bridges the vocabulary gap between formal document language and informal user queries.

**Metadata Enrichment**
Auto-extract and attach structured metadata during ingestion: section number, rule type, entity names, relationship types. Enables hard pre-filtering before vector search. Currently domain/subdomain are set manually in config; structural metadata from within documents is not yet extracted.

---

### Query / Retrieval Strategies

**Query Decomposition / Multi-Query**
Break complex queries into sub-questions, retrieve for each independently, merge before reranking. Currently `num_queries=1` in `QueryFusionRetriever`. Directly benefits compound consumer queries.

**HyDE (Hypothetical Document Embedding — query-time)**
Generate a hypothetical answer to the query using the LLM, embed that answer, and use it for vector search instead of the raw query. Hypothetical answers are in the same language space as document chunks. Adds one LLM call pre-retrieval; best for vague queries (BM25 already handles keyword-heavy queries well).

**Maximal Marginal Relevance (MMR)**
Penalise candidate chunks that are too similar to already-selected ones. Balances relevance with diversity, ensuring the LLM sees varied evidence rather than near-duplicate adjacent paragraphs. LlamaIndex supports `mmr` mode on vector retrievers.

**Metadata Filtering**
Apply hard filters (source, section, date range, document type) before vector search to scope retrieval. Requires metadata enrichment at ingest time.

**Time-Weighted Retrieval**
Decay relevance scores of older document versions. Relevant when LeanIX exports are refreshed and stale versions should be deprioritised.

**Caching**
Cache query embeddings and results for repeated or near-identical queries. Eliminates retrieval and LLM latency entirely on cache hits. Particularly useful for consumer scripts that run the same entity queries in batch.

---

### Graph-Based Retrieval

**GraphRAG**
Build a knowledge graph from LeanIX relationships at ingest time, then use graph traversal during retrieval to follow entity relationships rather than relying solely on chunk proximity. LeanIX is natively a graph (Applications → Interfaces → DataObjects → BusinessCapabilities → Providers). Questions like "what data objects flow through this interface?" or "which applications depend on this IT component?" are graph traversal problems, not similarity search problems — flat retrieval gives partial answers at best.

Implementation options:
- **LlamaIndex `KnowledgeGraphIndex`** — extracts triples from text and stores in a graph; queries traverse it
- **Neo4j + LlamaIndex** — persistent graph store with Cypher query support; higher setup cost, much richer traversal
- **Hybrid** — use GraphRAG for relationship queries, flat hybrid retrieval for descriptive/definitional queries; route based on query classification

This is the highest-effort enhancement but potentially the highest-value one for LeanIX data specifically.

---

### Reranking Strategies

**Cross-Encoder Reranker**
A cross-encoder sees query + document *together* rather than independently, giving much higher ranking quality than embedding cosine similarity. `cross-encoder/ms-marco-MiniLM-L-6-v2` runs fully locally via `sentence-transformers`. Higher latency (~200–800ms). Already in config as `reranker_strategy: "cross-encoder"` — requires `sentence-transformers` package.

**LLM-as-Reranker**
Pass top-N candidates to the LLM with a prompt asking it to rank by relevance. Highest possible reranking quality; high latency. Best used selectively for low-volume, high-stakes queries rather than as the default path.

---

### Context Assembly Strategies

**Context Compression**
After retrieval, strip irrelevant sentences from each chunk before passing to the LLM (`LLMChainFilter` or `EmbeddingsFilter`). Reduces token consumption and focuses the LLM on signal rather than noise. Useful when `reranker_top_k` is high.

**Lost-in-the-Middle Mitigation**
LLMs attend better to content at the start and end of context. Reorder reranked chunks so the highest-scoring appear first and last, lowest-scoring in the middle. Zero latency cost; measurable quality improvement for larger context windows.

**Map-Reduce / Refine Synthesis**
For very large context (many collections), process chunks in batches: either summarise each batch then combine (map-reduce), or iteratively refine a running answer with each new chunk (refine). Prevents context window overflow when querying across all LeanIX collections simultaneously.

---

### LLM Synthesis Strategies

**Structured Output + Forced Citation**
Prompt the LLM to return structured JSON including answer and which chunk IDs were used. Makes consumer parsing more reliable than regex over free text; adds full auditability of source evidence.

**Self-RAG / CRAG (Corrective RAG)**
After generating an answer, the LLM evaluates whether its retrieved context was sufficient. If not, it triggers a second retrieval pass with a reformulated query. Reduces hallucinations on multi-hop questions that require both Handbook and LeanIX context. Significantly higher latency and complexity.

**FLARE (Forward-Looking Active Retrieval)**
Retrieval is triggered iteratively *during* generation — when the LLM is uncertain about the next token, it pauses and retrieves before continuing. Most powerful for long-form answers that require evidence at multiple points.

---

### Evaluation

**RAGAS**
Automated RAG evaluation framework scoring on: faithfulness (answer grounded in context?), answer relevance (answers the question?), context precision (right chunks retrieved?), context recall (all relevant chunks found?). Run offline against a small test set to objectively measure whether config changes improve or regress quality. Currently there is no automated quality baseline.

## References

- [ARCHITECTURE.md](ARCHITECTURE.md) — Full system architecture and package overview
- `elt_llm_core/src/elt_llm_core/query_engine.py` — Base query engine (shared infrastructure)
- `elt_llm_query/src/elt_llm_query/query.py` — Retrieval, reranking, and LLM synthesis
- `elt_llm_ingest/config/rag_config.yaml` — Configuration reference
