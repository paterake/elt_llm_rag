# elt-llm-core

Shared RAG infrastructure — ChromaDB, Ollama, config, and query engine. Used as a library by `elt_llm_ingest` and `elt_llm_query`. Has no CLI. See [ARCHITECTURE.md](../ARCHITECTURE.md) for design documentation.

## Installation

```bash
cd elt_llm_core
uv sync
```

## Module Structure

```
src/elt_llm_core/
├── config.py         # YAML configuration (RagConfig)
├── models.py         # Ollama embedding + LLM model factories
├── vector_store.py   # ChromaDB client and collection management
└── query_engine.py   # Query interface and response synthesis
```
