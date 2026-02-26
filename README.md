# ELT LLM RAG

RAG platform for FA architecture knowledge, data governance, and automated documentation generation.

See [ARCHITECTURE.md](ARCHITECTURE.md) for full system documentation and [ROADMAP.md](ROADMAP.md) for implementation phases.

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
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined

# Query (GUI — http://localhost:7860)
uv run python -m elt_llm_api.app
```

---

## Modules

| Module | Purpose | Commands |
|--------|---------|----------|
| `elt_llm_ingest/` | Document ingestion | [README](elt_llm_ingest/README.md) |
| `elt_llm_query/` | Query interface | [README](elt_llm_query/README.md) |
| `elt_llm_core/` | Core RAG infrastructure | [README](elt_llm_core/README.md) |

## Common Commands

```bash
# Check collection status
uv run python -m elt_llm_ingest.runner --status

# List ingestion configs
uv run python -m elt_llm_ingest.runner --list

# List query profiles
uv run python -m elt_llm_query.runner --list

# Single query
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined -q "What is a Club?"

# Interactive session
uv run python -m elt_llm_query.runner --cfg fa_data_management

# Full reset
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.runner --cfg load_rag
```
