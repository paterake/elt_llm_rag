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
- [6. Implementation Roadmap](#6-implementation-roadmap)

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
    ├── fa_consolidated_catalog.py  # Target output
    ├── fa_integrated_catalog.py
    ├── fa_handbook_model_builder.py
    ├── fa_coverage_validator.py
    └── business_glossary.py
```

---

## 3. Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| Vector Store | ChromaDB | Persistent, tenant/database isolation |
| Embeddings | Ollama | `nomic-embed-text` (768 dims) |
| LLM | Ollama | `qwen2.5:14b` (8K context) |
| Retrieval | LlamaIndex | BM25 + Vector hybrid |
| Reranking | Embedding | Cosine similarity (top-20 → top-8) |
| Dependency Mgmt | uv | Python 3.11-3.13 |

---

## 4. RAG Pipeline

### 4.1 Retrieval Flow

```
Query → Hybrid Retrieval (BM25 + Vector) → Top-20 candidates
      → Embedding Reranker (cosine similarity) → Top-8 chunks
      → LLM Synthesis (qwen2.5:14b) → Structured output
```

### 4.2 Configuration

Defined in `elt_llm_ingest/config/rag_config.yaml`:

```yaml
query:
  similarity_top_k: 8
  use_hybrid_search: true
  use_reranker: true
  reranker_strategy: "embedding"
  reranker_retrieve_k: 20
  reranker_top_k: 8
```

### 4.3 Collection Structure

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
| `fa_integrated_catalog` | ToR per entity | Alternative output format |
| `fa_handbook_model_builder` | Handbook-only extraction | No LeanIX available |
| `fa_coverage_validator` | Coverage scoring | Model refinement cycle |
| `business_glossary` | Inventory-driven glossary | Different output format |

---

## 6. Implementation Roadmap

### 6.1 Phase 1: Foundation (Weeks 1-4)

| Task | Owner | Status |
|------|-------|--------|
| LeanIX glossary export | Development Team | TODO |
| ISO Reference Data ingestion | Development Team | TODO |
| FAGlossaryPreprocessor | Development Team | TODO |
| FDM ingestion + alignment | Data Team | TODO |

### 6.2 Phase 2: SAD Quality + Generation (Weeks 5-8)

| Task | Owner | Status |
|------|-------|--------|
| SAD Quality Checker | Development Team | TODO |
| Confluence scraper | Development Team | TODO |
| SAD template definition | Development Team + Data Team | TODO |

### 6.3 Phase 3: ERD Automation (Weeks 9-12)

| Task | Owner | Status |
|------|-------|--------|
| PlantUML ERD generator | Development Team | TODO |
| draw.io export | Development Team | TODO |
| Conceptual → Logical mapping | Data Team | TODO |

### 6.4 Phase 4: Purview Integration (Weeks 13-16)

| Task | Owner | Status |
|------|-------|--------|
| Purview glossary export | Development Team | TODO |
| Purview schema import | Development Team | TODO |
| Lineage query interface | Development Team | TODO |

### 6.5 Phase 5: Vendor Assessment (Weeks 17-20)

| Task | Owner | Status |
|------|-------|--------|
| Vendor assessment template | Development Team + Data Team | TODO |
| Vendor comparison generator | Development Team | TODO |

---

## 7. Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| SAD authoring time | 2-3 weeks | 3-5 days |
| Glossary term lookup | Manual search | <10 seconds |
| ERD creation | Manual (days) | Automated (minutes) |
| Reference data conformance | Unknown | 95%+ validated |

---

## 8. References

- [README.md](README.md) — Quick start
- [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) — Stakeholder presentation
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy
- [ORCHESTRATION.md](ORCHESTRATION.md) — Workflow
- [elt_llm_consumer/README.md](elt_llm_consumer/README.md) — Consumer documentation
