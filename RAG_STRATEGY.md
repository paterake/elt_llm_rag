# RAG Strategy

**Status**: Production-ready for FA glossary/catalogue generation  
**Last Updated**: March 2026

---

## Executive Summary

The system implements a **hybrid retrieval + reranking** strategy:

```
Query → Hybrid Retrieval (BM25 + Vector) → Embedding Reranker → Top-K Chunks → LLM → Answer
```

**Key Design Decisions**:
- **Hybrid search**: BM25 (keyword) + Vector (semantic) — captures both exact matches and conceptual similarity
- **Embedding reranking**: Re-scores retrieved chunks by query-document cosine similarity before LLM synthesis
- **Local-first**: All embeddings and inference via Ollama — no external API dependencies
- **Precision over recall**: Reranking ensures only the most relevant chunks reach the LLM

---

## What's Implemented (Production)

### Retrieval Pipeline

| Stage | Implementation | Status |
|-------|----------------|--------|
| **1. Hybrid Retrieval** | BM25 + Vector via QueryFusionRetriever | ✅ Production |
| **2. Multi-query expansion** | `num_queries=3` — LLM generates query variants for broader recall | ✅ Production |
| **3. Embedding Reranker** | Cosine similarity re-scoring with optional MMR diversity | ✅ Production |
| **4. Cross-encoder Reranker** | sentence-transformers CrossEncoder (joint query+doc scoring) | ✅ Production |
| **5. Lost-in-middle reorder** | Highest-scoring chunks placed at context window ends | ✅ Production |
| **6. LLM Synthesis** | Ollama (qwen2.5:14b) with system prompt | ✅ Production |

### Configuration

**File**: `elt_llm_ingest/config/rag_config.yaml`

```yaml
query:
  similarity_top_k: 10
  use_hybrid_search: true
  use_reranker: true
  reranker_strategy: "embedding"    # switch to "cross-encoder" for higher quality
  reranker_retrieve_k: 20
  reranker_top_k: 8
  num_queries: 3                    # query variants (1=off, 3=recommended)
  use_mmr: true                     # diversity filter (0.7 = 70% relevance, 30% diversity)
  mmr_threshold: 0.7
  use_lost_in_middle: true          # reorder chunks for LLM attention
```

### Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| Vector Store | ChromaDB | Persistent, tenant/database isolation |
| Embeddings | Ollama | `nomic-embed-text` (768 dimensions) |
| LLM | Ollama | `qwen2.5:14b` (8K context window) |
| Hybrid Retrieval | LlamaIndex | BM25 + Vector via QueryFusionRetriever |
| Reranking | Custom | Embedding cosine similarity |

### Package Boundaries

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
                         │  5. LLM Synthesis                    │
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

---

## What's Planned (Backlog)

### High Priority (Phase 1-2)

| Enhancement | Benefit | Effort | Status |
|-------------|---------|--------|--------|
| **Metadata enrichment** | Scoped queries by section/type/source | Medium | ⬜ Phase 2 — requires re-ingestion of fa_handbook |
| **Structured output + citations** | Purview-ready format with source attribution | Low | ⬜ Phase 2 |
| **GraphRAG** | Relationship traversal for Erwin LDM | High | ⬜ Phase 2 — requires re-ingestion of all collections |
| **MMR (Maximal Marginal Relevance)** | Prevents duplicate chunks in context | Low | ✅ Implemented |

### Medium Priority (Phase 2-3)

| Enhancement | Benefit | Effort | Status |
|-------------|---------|--------|--------|
| **Parent-child chunking** | Preserves full rule context for regulatory text | Medium | ⬜ Phase 2 — requires re-ingestion of fa_handbook |
| **Cross-encoder reranker** | Higher reranking quality (MiniLM-L-6-v2) | Medium | ✅ Implemented |
| **RAGAS evaluation harness** | Objective quality baseline | Medium | ⬜ Phase 2 |

### Lower Priority (Phase 3+)

| Enhancement | Benefit | Effort | Status |
|-------------|---------|--------|--------|
| **Caching** | Repeated Copilot queries | Low | ⬜ Phase 3 |
| **Context compression** | Reduces token noise | Medium | ⬜ Phase 2 |
| **Query decomposition / Multi-query** | Multi-entity queries, broader recall | Low | ✅ Implemented |
| **Lost-in-the-middle mitigation** | Better LLM attention on context window | Low | ✅ Implemented |
| **HyDE (query-time)** | Vague/exploratory queries | Low | ⬜ Phase 2 |

---

## Retrieval Flow

### Single Collection

```
┌─────────────┐
│   Query     │
└──────┬──────┘
       │
       ├──→ [Vector Retriever] ──→ Top-K dense vectors (ChromaDB)
       │
       └──→ [BM25 Retriever] ────→ Top-K keyword matches (DocStore)
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

### Multi-Collection

When querying across multiple collections (e.g., multiple LeanIX domains):

1. Retrieve `reranker_retrieve_k / num_collections` from each collection
2. Merge all candidates
3. Apply embedding reranker globally
4. Keep top-`reranker_top_k` overall

**Benefit**: Each collection has representation while reranker selects the most relevant overall.

---

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Vector retrieval | 10–50ms | ChromaDB ANN search |
| BM25 retrieval | 5–20ms | In-memory index |
| Embedding reranker | 100–500ms | Ollama embedding (20 candidates) |
| LLM synthesis | 1–5s | Depends on model and context size |

**Total typical latency**: 2–6 seconds per query

---

## Fallback Behaviour

| Condition | Fallback |
|-----------|----------|
| BM25 docstore missing | Vector-only retrieval |
| Reranker disabled | Direct top-K from fusion retriever |
| Ollama unavailable | Query fails (no cloud fallback) |

---

## Design Principles

1. **Local-first**: All embeddings and inference via Ollama — no external API dependencies
2. **Graceful degradation**: System functions with reduced quality if components are missing
3. **Precision over recall**: Reranking ensures only the most relevant chunks reach the LLM
4. **Transparency**: Retrieval scores and sources logged for debugging

---

## Enhancement Details

### Ingestion Strategies (Planned)

#### Parent-Child Chunking
Store small chunks for precise retrieval; expand to parent chunk for LLM context. LlamaIndex supports this natively (`HierarchicalNodeParser` + `AutoMergingRetriever`).

**Value**: Preserves full rule context for FA Handbook regulatory text where rules span multiple sentences.

#### Metadata Enrichment
Auto-extract and attach structured metadata during ingestion: section number, rule type, entity names, relationship types.

**Value**: Enables hard pre-filtering before vector search (e.g., "only Handbook Section C", "only LeanIX relationships").

**Current State**: Domain/subdomain set manually in config; structural metadata from documents not yet extracted.

---

### Query Strategies (Planned)

#### MMR (Maximal Marginal Relevance) ✅ Implemented
Penalise candidate chunks that are too similar to already-selected ones.

**Value**: Prevents top-8 being near-duplicate adjacent paragraphs — ensures LLM sees varied evidence.

**Implementation**: Custom MMR in a single embedding pass inside `_rerank_nodes_embedding`. Controlled by `use_mmr: true` and `mmr_threshold: 0.7` in `rag_config.yaml`.

#### Query Decomposition / Multi-Query ✅ Implemented
Generate additional query variants using the LLM, retrieve for each, merge before reranking.

**Value**: Consumer queries are compound (multi-entity, multi-domain). `num_queries=3` generates 2 additional query variants for broader retrieval coverage.

**Note**: Each additional query variant adds one LLM call during retrieval. Set `num_queries: 1` in `rag_config.yaml` to disable for batch jobs where runtime is critical.

#### Caching
Cache query embeddings and results for repeated or near-identical queries.

**Value**: Eliminates retrieval and LLM latency on cache hits. Useful for consumer scripts running same entity queries in batch.

---

### Graph-Based Retrieval (Planned)

#### GraphRAG
Build knowledge graph from LeanIX relationships at ingest time, then use graph traversal during retrieval.

**Value**: LeanIX is natively a graph (Applications → Interfaces → DataObjects → BusinessCapabilities). Questions like "what data objects flow through this interface?" are graph traversal problems, not similarity search problems.

**Implementation Options**:
- LlamaIndex `KnowledgeGraphIndex` — extracts triples, stores in graph
- Neo4j + LlamaIndex — persistent graph store with Cypher query support
- Hybrid — GraphRAG for relationship queries, flat retrieval for descriptive queries

**Effort**: High (requires re-ingestion with relationship extraction)  
**Priority**: Phase 2 (critical for Erwin LDM relationship export)

---

### Reranking Strategies (Planned)

#### Cross-Encoder Reranker ✅ Implemented
Cross-encoder sees query + document *together* rather than independently.

**Value**: Higher ranking quality than embedding cosine similarity.

**Implementation**: `cross-encoder/ms-marco-MiniLM-L-6-v2` via `sentence-transformers` (added to `elt-llm-query` dependencies). Switch with `reranker_strategy: "cross-encoder"` in `rag_config.yaml`. Falls back to embedding reranker if package unavailable.

**Latency**: 200–800ms (vs. 100–500ms for embedding reranker)

---

### Context Assembly Strategies (Planned)

#### Lost-in-the-Middle Mitigation ✅ Implemented
LLMs attend better to content at start and end of context. Reorder reranked chunks: highest-scoring first and last, lowest-scoring in middle.

**Value**: Improves LLM attention across larger context windows.

**Implementation**: `_reorder_for_lost_in_middle()` in `query.py`. Enabled via `use_lost_in_middle: true` in `rag_config.yaml`. Applied as the final post-processing step after reranking.

#### Context Compression
After retrieval, strip irrelevant sentences from each chunk before passing to LLM.

**Value**: Reduces token consumption, focuses LLM on signal.

**Implementation**: `LLMChainFilter` or `EmbeddingsFilter`

---

### LLM Synthesis Strategies (Planned)

#### Structured Output + Forced Citation
Prompt LLM to return structured JSON including answer and which chunk IDs were used.

**Value**: Makes consumer parsing reliable; adds full auditability of source evidence.

**Priority**: Phase 2 (critical for Purview import format)

#### Self-RAG / CRAG (Corrective RAG)
After generating answer, LLM evaluates whether retrieved context was sufficient. If not, triggers second retrieval pass with reformulated query.

**Value**: Reduces hallucinations on multi-hop questions requiring both Handbook and LeanIX context.

**Effort**: High (requires iterative retrieval loop)

---

### Evaluation (Planned)

#### RAGAS Evaluation Harness
Automated RAG evaluation framework scoring:
- **Faithfulness**: Answer grounded in context?
- **Answer Relevance**: Answers the question?
- **Context Precision**: Right chunks retrieved?
- **Context Recall**: All relevant chunks found?

**Value**: Objective quality baseline; measures impact of config changes.

**Current State**: No automated quality baseline.

---

## Delivery Context

### Phase 1 — Data Asset Catalog (Current)

**Goal**: Produce structured catalog linking FA Handbook terms to LeanIX conceptual model entities and inventory descriptions.

**RAG Requirements**:
- Hybrid retrieval (implemented)
- Multi-query expansion — `num_queries=3` (implemented)
- Embedding reranker with MMR diversity (implemented)
- Cross-encoder reranker — `reranker_strategy: "cross-encoder"` (implemented)
- Lost-in-the-middle reordering (implemented)
- Structured JSON output (implemented)

**Next**: Metadata enrichment, parent-child chunking (both require fa_handbook re-ingestion), RAGAS evaluation

---

### Phase 2 — Purview + Erwin LDM

**Goal**: Import reviewed catalog to Microsoft Purview + embed in Erwin Logical Data Model.

**RAG Requirements**:
- Structured output + citations (planned)
- GraphRAG for relationship extraction (planned)
- JSON format for reliable ingestion (implemented)

**Next**: GraphRAG implementation, citation forcing in prompts

---

### Phase 3 — Intranet + MS Fabric / Copilot

**Goal**: Publish to intranet + integrate with MS Fabric semantic model for Copilot.

**RAG Requirements**:
- Caching for repeated Copilot queries (planned)
- GraphRAG for semantic model relationships (planned)
- Low-latency responses (optimisation needed)

**Next**: Caching layer, performance optimisation

---

## References

- [README.md](README.md) — Quick start
- [ARCHITECTURE.md](ARCHITECTURE.md) — System architecture
- `elt_llm_core/src/elt_llm_core/query_engine.py` — Base query engine
- `elt_llm_query/src/elt_llm_query/query.py` — Retrieval, reranking, synthesis
- `elt_llm_ingest/config/rag_config.yaml` — Configuration reference
