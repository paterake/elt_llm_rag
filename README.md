# ELT LLM RAG

RAG platform for FA architecture knowledge, data governance, and automated documentation generation.

**Start here for understanding**: Read [ARCHITECTURE.md](ARCHITECTURE.md) for the complete system overview — what's built, why, how AI + custom code work together, and end-to-end flow. This README is for quick start commands only.

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

| Document | Purpose | When to Read |
|----------|---------|--------------|
| **[ARCHITECTURE.md](ARCHITECTURE.md)** | **Complete system overview** — what's built, why, how it works | **Read this first** |
| **[COMPLETE_DATA_FLOW.md](COMPLETE_DATA_FLOW.md)** | **How RAG+LLM works** — ingestion → retrieval → synthesis (with diagrams) | **Understand the flow** |
| **[README.md](README.md)** (this file) | Quick start commands only | Use for running the system |
| **[RAG_STRATEGY.md](RAG_STRATEGY.md)** | Retrieval strategy details, tuning, enhancement roadmap | When optimizing RAG |
| **[ORCHESTRATION.md](ORCHESTRATION.md)** | Runbooks, phase status, troubleshooting | When running or extending |
| **Module README** | Module-specific usage and reference | When working on a module |

### Module Documentation

| Module | Purpose | Documentation |
|--------|---------|---------------|
| `elt_llm_core/` | Shared RAG infrastructure | [README](elt_llm_core/README.md) |
| `elt_llm_ingest/` | Document ingestion pipeline | [README](elt_llm_ingest/README.md), [ARCHITECTURE](elt_llm_ingest/ARCHITECTURE.md) |
| `elt_llm_query/` | Query interface | [README](elt_llm_query/README.md) |
| `elt_llm_api/` | Gradio GUI + API | [README](elt_llm_api/README.md) |
| `elt_llm_consumer/` | Purpose-built output generators | [README](elt_llm_consumer/README.md), [ARCHITECTURE](elt_llm_consumer/ARCHITECTURE.md) |

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

See [ORCHESTRATION.md](ORCHESTRATION.md) for the full stakeholder review workflow.

---

## Contact

Development Team | Data Governance Lead | Data Modelling Team
