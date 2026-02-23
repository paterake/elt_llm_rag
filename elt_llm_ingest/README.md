# elt-llm-ingest

Generic document ingestion pipeline for RAG systems.

## Overview

This package provides a reusable document ingestion pipeline that:

- Loads documents from multiple formats (PDF, DOCX, TXT, HTML, etc.)
- Chunks documents using LlamaIndex transformers
- Embeds chunks using Ollama
- Stores embeddings in ChromaDB

## Installation

```bash
cd elt_llm_ingest
uv sync
```

## Usage

**Note:** Run these commands from the `elt_llm_ingest` directory or use the full path.

### List Available Configs

```bash
cd elt_llm_ingest
uv run python -m elt_llm_ingest.runner --list
```

### Ingest Documents

```bash
# Ingest DAMA-DMBOK
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

# Ingest FA Handbook
uv run python -m elt_llm_ingest.runner --cfg fa_handbook

# Ingest SAD
uv run python -m elt_llm_ingest.runner --cfg sad

# Ingest LeanIX
uv run python -m elt_llm_ingest.runner --cfg leanix

# Ingest Supplier Assessment
uv run python -m elt_llm_ingest.runner --cfg supplier_assess
```

### Ingest with Options

```bash
# Verbose output
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

# Append mode (don't rebuild collection)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild

# Verbose + append mode
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v --no-rebuild
```

### Delete Collections

```bash
# Delete DAMA-DMBOK (with confirmation)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete

# Delete DAMA-DMBOK (force, no confirmation)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f

# Delete FA Handbook
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --delete

# Delete SAD
uv run python -m elt_llm_ingest.runner --cfg sad --delete

# Delete LeanIX
uv run python -m elt_llm_ingest.runner --cfg leanix --delete

# Delete Supplier Assessment
uv run python -m elt_llm_ingest.runner --cfg supplier_assess --delete
```

### Available Configs

The `config/` directory includes predefined configs:

| Config | Description |
|--------|-------------|
| `dama_dmbok.yaml` | DAMA-DMBOK2R Data Management Body of Knowledge |
| `fa_handbook.yaml` | Financial Accounting Handbook |
| `sad.yaml` | Solution Architecture Definition |
| `leanix.yaml` | LeanIX Platform Documentation |
| `supplier_assess.yaml` | Supplier Assessment Documentation |

## Configuration

### Ingestion Config (`config/*.yaml`)

```yaml
collection_name: "dama_dmbok"

file_paths:
  - "~/Documents/__data/books/DAMA-DMBOK2R_unlocked.pdf"

metadata:
  domain: "data_management"
  type: "body_of_knowledge"

rebuild: true  # Rebuild collection on each run
```

### RAG Config (`config/rag_config.yaml`)

Shared settings for ChromaDB, Ollama, and chunking:

```yaml
chroma:
  persist_dir: "./chroma_db"
  tenant: "rag_tenants"
  database: "knowledge_base"

ollama:
  base_url: "http://localhost:11434"
  embedding_model: "nomic-embed-text"
  llm_model: "llama3.2"

chunking:
  strategy: "sentence"
  chunk_size: 1024
  chunk_overlap: 200
```

## Adding New Document Types

1. Create a new config file in `config/`:

```yaml
# config/my_docs.yaml
collection_name: "my_docs"

file_paths:
  - "~/Documents/my_book.pdf"

metadata:
  domain: "my_domain"
  type: "handbook"

rebuild: true
```

2. Ingest:

```bash
elt-llm-ingest --config config/my_docs.yaml
```

## Supported Formats

Via LlamaIndex readers:
- PDF (`.pdf`)
- Word (`.docx`)
- Text (`.txt`)
- HTML (`.html`)
- Markdown (`.md`)
- CSV (`.csv`)
- JSON (`.json`)
- And more...

## Module Structure

```
elt_llm_ingest/
├── config/
│   ├── rag_config.yaml           # Shared RAG settings
│   ├── dama_dmbok.yaml           # DAMA-DMBOK ingestion config
│   ├── fa_handbook.yaml          # FA Handbook ingestion config
│   ├── sad.yaml                  # SAD ingestion config
│   ├── leanix.yaml               # LeanIX ingestion config
│   └── supplier_assess.yaml      # Supplier assessment config
├── src/elt_llm_ingest/
│   ├── __init__.py
│   ├── runner.py                 # Generic runner (--cfg parameter)
│   ├── ingest.py                 # Ingestion pipeline
│   └── cli.py                    # CLI entry point
└── tests/
```

## Dependencies

- `elt_llm_core` - Core RAG infrastructure
- `llama-index` - Document processing
- `llama-index-readers-file` - File format support

## Prerequisites

- Python 3.11, 3.12, or 3.13 (ChromaDB is not yet compatible with Python 3.14)
- Ollama running locally: `ollama serve`
- Required models:
  ```bash
  ollama pull nomic-embed-text
  ollama pull llama3.2
  ```
