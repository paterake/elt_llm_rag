# ELT LLM RAG

RAG platform for FA architecture knowledge, data governance, and automated documentation generation.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system documentation and [RAG_STRATEGY.md](RAG_STRATEGY.md) for retrieval strategy details.

---

## Prerequisites

```bash
# Python 3.11–3.13, uv, and Ollama
ollama serve
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
```

## Quick Start

```bash
uv sync --all-packages

# Ingest all collections
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Query (CLI)
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture

# Query (GUI — http://localhost:7860)
uv run python -m elt_llm_api.app

# Generate business catalog CSV
uv run --package elt-llm-consumer elt-llm-consumer-glossary
```

---

## Modules

| Module | Purpose | Docs |
|--------|---------|------|
| `elt_llm_core/` | Shared RAG infrastructure (ChromaDB, Ollama, config) | [README](elt_llm_core/README.md) |
| `elt_llm_ingest/` | Document ingestion pipeline | [README](elt_llm_ingest/README.md) |
| `elt_llm_query/` | Query interface (CLI + multi-collection) | [README](elt_llm_query/README.md) |
| `elt_llm_api/` | Gradio GUI + programmatic API | [README](elt_llm_api/README.md) |
| `elt_llm_consumer/` | Purpose-built products over the RAG system | [README](elt_llm_consumer/README.md) |

---

## Documentation Index

- Root
  - [README.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/README.md)
  - [ARCHITECTURE.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/ARCHITECTURE.md)
  - [RAG_STRATEGY.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/RAG_STRATEGY.md)
- elt_llm_core
  - [README.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_core/README.md)
  - [ARCHITECTURE.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_core/ARCHITECTURE.md)
- elt_llm_ingest
  - [README.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/README.md)
  - [ARCHITECTURE.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/ARCHITECTURE.md)
- elt_llm_query
  - [README.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_query/README.md)
  - [ARCHITECTURE.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_query/ARCHITECTURE.md)
- elt_llm_api
  - [README.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_api/README.md)
  - [ARCHITECTURE.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_api/ARCHITECTURE.md)
- elt_llm_consumer
  - [README.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_consumer/README.md)
  - [ARCHITECTURE.md](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_consumer/ARCHITECTURE.md)

## Common Commands

```bash

```bash
# Check collection status
uv run python -m elt_llm_ingest.runner --status

# List ingestion configs
uv run python -m elt_llm_ingest.runner --list

# List query profiles
uv run python -m elt_llm_query.runner --list

# Single query — FA sources (LeanIX CM + Inventory + Handbook + Data Architecture)
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture -q "What is a Club?"

# Single query — Full data management programme (all sources)
uv run python -m elt_llm_query.runner --cfg fa_data_management -q "What are the key PARTY domain entities?"

# Interactive session
uv run python -m elt_llm_query.runner --cfg fa_handbook_only

# Selective collection reset (e.g. LeanIX only)
uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix

# Full reset
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Generate business catalog (LeanIX inventory as driver, all FA RAG collections)
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model qwen2.5:14b

# Generate integrated catalog (conceptual model as frame + inventory join + FA Handbook)
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --model qwen2.5:14b

# Build candidate model and ToR from FA Handbook only (no LeanIX)
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model --model qwen2.5:14b

# Validate model entities against FA Handbook (no LLM — ~5 min)
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis
```
