# ELT LLM RAG

RAG platform for FA architecture knowledge, data governance, and automated documentation generation.

---

## Quick Start

```bash
# Prerequisites
ollama serve
ollama pull nomic-embed-text
ollama pull qwen3.5:9b

# Install
uv sync --all-packages

# Ingest collections
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Generate consolidated catalog (target output)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Query (GUI)
uv run python -m elt_llm_api.app
```

**Output**: `.tmp/fa_consolidated_catalog.json`

---

## Documentation

| Document | Purpose | Location |
|----------|---------|----------|
| **README.md** (this file) | Quick start and module overview | Root |
| **SOLUTION_OVERVIEW.md** | Stakeholder presentation — challenge, solution, output | Root |
| **ARCHITECTURE.md** | Technical architecture — system design, components, roadmap | Root |
| **RAG_STRATEGY.md** | Retrieval strategy — hybrid search, reranking, configuration | Root |
| **ORCHESTRATION.md** | Workflow documentation — ingestion to output pipeline | Root |
| **Module README** | Module-specific usage and reference | Each module directory |

### Module Documentation

| Module | Purpose | Documentation |
|--------|---------|---------------|
| `elt_llm_core/` | Shared RAG infrastructure | [README](elt_llm_core/README.md) |
| `elt_llm_ingest/` | Document ingestion pipeline | [README](elt_llm_ingest/README.md) |
| `elt_llm_query/` | Query interface | [README](elt_llm_query/README.md) |
| `elt_llm_api/` | Gradio GUI + API | [README](elt_llm_api/README.md) |
| `elt_llm_consumer/` | Purpose-built output generators | [README](elt_llm_consumer/README.md) |

---

## Modules Overview

### elt_llm_core

Shared infrastructure: ChromaDB client, Ollama models, configuration, base query engine.

```bash
# Not run directly — imported by other modules
```

**Docs**: [elt_llm_core/README.md](elt_llm_core/README.md)

---

### elt_llm_ingest

Document ingestion: chunk, embed, store in ChromaDB + DocStore.

```bash
# Ingest all collections
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Ingest specific source
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory

# Check status
uv run python -m elt_llm_ingest.runner --status
```

**Docs**: [elt_llm_ingest/README.md](elt_llm_ingest/README.md)

---

### elt_llm_query

Query interface: hybrid retrieval (BM25 + Vector), reranking, LLM synthesis.

```bash
# List query profiles
uv run python -m elt_llm_query.runner --list

# Query with profile
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture -q "What is a Club?"
uv run python -m elt_llm_query.runner --cfg fa_data_management -q "What are the key PARTY domain entities?"

# Interactive session
uv run python -m elt_llm_query.runner --cfg fa_handbook_only
```

**Docs**: [elt_llm_query/README.md](elt_llm_query/README.md)

---

### elt_llm_api

Gradio GUI (http://localhost:7860) + programmatic API.

```bash
# Start GUI
uv run python -m elt_llm_api.app
```

**Docs**: [elt_llm_api/README.md](elt_llm_api/README.md)

---

### elt_llm_consumer

Purpose-built output generators: consolidated catalog, handbook model builder, coverage validator.

```bash
# Primary output: consolidated catalog
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships

# Handbook-only entity extraction
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model

# Coverage validation
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis
```

**Docs**: [elt_llm_consumer/README.md](elt_llm_consumer/README.md)

---

## Common Workflows

### Generate Target Output

```bash
# 1. Ingest sources
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory

# 2. Generate consolidated catalog
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# 3. Review output
# File: .tmp/fa_consolidated_catalog.json
```

### Query Collections

```bash
# GUI (recommended)
uv run python -m elt_llm_api.app

# CLI
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture -q "What is a Club?"
```

### Maintenance

```bash
# List collection status
uv run python -m elt_llm_ingest.runner --status

# Reset specific collection
uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix

# Full reset
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.runner --cfg load_rag
```

---

## Technology Stack

| Component | Technology |
|-----------|------------|
| Vector Store | ChromaDB |
| Embeddings | Ollama (nomic-embed-text) |
| LLM | Ollama (qwen3.5:9b) |
| Retrieval | LlamaIndex (BM25 + Vector hybrid) |
| Reranking | Embedding (default) or Cross-encoder |
| Dependency Management | uv |

---

## Output Files

| File | Location | Purpose |
|------|----------|---------|
| `fa_consolidated_catalog.json` | `.tmp/` | Stakeholder review (master output) |
| `fa_consolidated_relationships.json` | `.tmp/` | Relationships with source attribution |

---

## Next Steps

1. **Review output** — Open `.tmp/fa_consolidated_catalog.json` with data modelling team
2. **Update review status** — Mark entities as APPROVED/REJECTED/NEEDS_CLARIFICATION
3. **Downstream import** — Transform for Purview, Erwin LDM, MS Fabric

See [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) for detailed stakeholder review process.

---

## Contact

Development Team | Data Governance Lead | Data Modelling Team
