# LLM RAG Workspace

Retrieval-Augmented Generation (RAG) workspace for document ingestion and querying.

## Prerequisites

- Python 3.11, 3.12, or 3.13 (ChromaDB incompatible with 3.14)
- Ollama running locally
- uv for dependency management

## Quick Start

```bash
cd /Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag
uv sync

# Pull models
ollama pull nomic-embed-text
ollama pull llama3.2
ollama pull qwen2.5:14b


# Ingest
cd elt_llm_ingest
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

# Query
cd ../elt_llm_query
uv run python -m elt_llm_query.runner --cfg dama_only
```

## Structure

- `elt_llm_core/` - Core RAG infrastructure
- `elt_llm_ingest/` - Document ingestion  
- `elt_llm_query/` - Query interface

See individual README files for details.
