# ELT LLM RAG Architecture

**Workspace**: `elt_llm_rag`  
**Purpose**: Technical architecture documentation

**See also**:
- [README.md](README.md) — Quick start and module overview
- [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) — Stakeholder presentation
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy details
- [ORCHESTRATION.md](ORCHESTRATION.md) — Workflow documentation

---

## Table of Contents

- [1. System Architecture](#1-system-architecture)
- [2. Module Structure](#2-module-structure)
- [3. Technology Stack](#3-technology-stack)
- [4. RAG Pipeline](#4-rag-pipeline)
- [5. Consumer Layer](#5-consumer-layer)
- [6. Delivery Roadmap](#6-delivery-roadmap)

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Knowledge Sources                        │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│   FA Handbook   │    LeanIX XML   │   DAMA-DMBOK    │   FDM     │
│   (PDF/HTML)    │  (draw.io)      │   (PDF)         │ (Excel)   │
└────────┬────────┴────────┬────────┴────────┬────────┴────┬─────┘
         │                 │                 │             │
         ↓                 ↓                 ↓             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Ingestion Layer                               │
│  elt_llm_ingest: Chunk → Embed → ChromaDB + DocStore            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Collections                               │
│  ChromaDB: fa_handbook, fa_leanix_*, dama_dmbok, ...            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Query Layer                                  │
│  elt_llm_query: BM25 + Vector → Rerank → LLM Synthesis          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Consumer Layer                                │
│  elt_llm_consumer: fa_consolidated_catalog.py + others          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Structure

```
elt_llm_rag/
├── elt_llm_core/           # Shared RAG infrastructure
│   ├── config.py           # YAML configuration
│   ├── vector_store.py     # ChromaDB client
│   ├── models.py           # Ollama models
│   └── query_engine.py     # Base query engine
│
├── elt_llm_ingest/         # Document ingestion
│   ├── runner.py           # Ingestion runner
│   ├── preprocessor.py     # Preprocessor framework
│   ├── doc_leanix_parser.py # LeanIX XML parser
│   └── config/             # Ingestion configs
│
├── elt_llm_query/          # Query interface
│   ├── runner.py           # Query runner
│   ├── query.py            # Single/multi-collection queries
│   └── llm_rag_profile/    # Query profiles
│
├── elt_llm_api/            # Gradio GUI + API
│   └── app.py              # Gradio web application
│
└── elt_llm_consumer/       # Output generators
    ├── fa_consolidated_catalog.py  # Target output (primary)
    ├── fa_handbook_model_builder.py
    └── fa_coverage_validator.py
```

---

## 3. Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| Vector Store | ChromaDB | Persistent, tenant/database isolation |
| Embeddings | Ollama | `nomic-embed-text` (768 dims) |
| LLM | Ollama | `qwen2.5:14b` (8K context) |
| Retrieval | LlamaIndex | BM25 + Vector hybrid |
| Reranking | Embedding or Cross-encoder | Cosine similarity or CrossEncoder (top-20 → top-8) |
| Dependency Mgmt | uv | Python 3.11-3.13 |

---

## 4. RAG Pipeline

### 4.1 Retrieval Flow

```
Query → Multi-query expansion → Hybrid Retrieval (BM25 + Vector)
      → Embedding or Cross-encoder Reranker + MMR diversity
      → Lost-in-middle reorder → LLM Synthesis → Structured output
```

See [RAG_STRATEGY.md](RAG_STRATEGY.md) for full pipeline detail, config knobs, and performance characteristics.

### 4.2 Collection Structure

| Collection | Source | Content |
|------------|--------|---------|
| `fa_handbook` | FA Handbook PDF | Governance rules, definitions |
| `fa_leanix_dat_enterprise_conceptual_model_*` | LeanIX XML | Conceptual model entities |
| `fa_leanix_global_inventory_*` | LeanIX Excel | System descriptions |
| `dama_dmbok` | DAMA-DMBOK PDF | Data management best practices |

---

## 5. Consumer Layer

### 5.1 Primary Consumer: fa_consolidated_catalog.py

**Purpose**: Generate consolidated glossary/catalog from all sources.

**Process**:
1. Scan conceptual model docstores → entities
2. RAG query → inventory descriptions
3. Scan Handbook docstore → defined terms
4. RAG query → map terms to entities
5. RAG query → extract Handbook context
6. Scan docstores → relationships
7. Consolidate → JSON output

**Command**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
```

**Output**: `.tmp/fa_consolidated_catalog.json`

**Docs**: [elt_llm_consumer/README.md](elt_llm_consumer/README.md)

### 5.2 Supporting Consumers

| Consumer | Purpose | When to Use |
|----------|---------|-------------|
| `fa_handbook_model_builder` | Handbook-only entity extraction | No LeanIX available; gap discovery |
| `fa_coverage_validator` | Coverage scoring against Handbook | Model refinement cycle; gap analysis |

---

## 6. Delivery Roadmap

Phase 1 (Data Asset Catalog) is complete. Phases 2–5 (Purview, Erwin LDM, Intranet, MS Fabric/Copilot) are planned.

See [ORCHESTRATION.md](ORCHESTRATION.md) for full phase detail, runbooks, and current status.

---

## 7. References

- [README.md](README.md) — Quick start
- [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) — Stakeholder presentation
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy
- [ORCHESTRATION.md](ORCHESTRATION.md) — Workflow
- [elt_llm_consumer/README.md](elt_llm_consumer/README.md) — Consumer documentation
