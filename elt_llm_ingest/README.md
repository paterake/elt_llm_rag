# elt-llm-ingest

Generic document ingestion pipeline for RAG systems with smart change detection.

## Overview

This package provides a reusable document ingestion pipeline that:

- Loads documents from multiple formats (PDF, DOCX, TXT, HTML, etc.)
- Chunks documents using LlamaIndex transformers
- Embeds chunks using Ollama
- Stores embeddings in ChromaDB
- **Smart ingest**: Automatically skips unchanged files using SHA256 hash detection

## Quick Start

```bash
# Check collection status
uv run python -m elt_llm_ingest.runner --status

# List available configs
uv run python -m elt_llm_ingest.runner --list

# Ingest a collection
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

# Re-run (only processes changed files)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild
```

## Installation

```bash
cd elt_llm_ingest
uv sync
```

## Usage

**Note:** Run these commands from the `elt_llm_ingest` directory or use the full path.

### Check Collection Status

```bash
# Show all collections with document counts
uv run python -m elt_llm_ingest.runner --status

# Show detailed metadata
uv run python -m elt_llm_ingest.runner --status -v
```

Example output:
```
=== ChromaDB Status ===

Persist directory: /path/to/chroma_db

Collection Name                        Documents  Metadata
----------------------------------------------------------------------
fa_handbook                                 9673  -
fa_data_architecture                        2261  -
dama_dmbok                                 11943  -
file_hashes                                    3  -

Total: 4 collection(s), 23880 document(s)
```

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

# Ingest FA Handbook
uv run python -m elt_llm_ingest.runner --cfg fa_data_architecture

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

# Append mode (don't rebuild collection, skip unchanged files)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild

# Verbose + append mode
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v --no-rebuild

# Force re-ingestion (bypass hash checking)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --force
```

**Smart Ingest Behavior:**

| Mode | Command | Behavior |
|------|---------|----------|
| Rebuild (default) | `--cfg dama_dmbok` | Clears collection, re-ingests all files, resets hash tracking |
| Append | `--cfg dama_dmbok --no-rebuild` | Only ingests changed/new files, preserves existing data |
| Force | `--cfg dama_dmbok --force` | Bypasses hash check, re-ingests everything |

### Smart Ingest (Change Detection)

The ingestion system uses **file-level SHA256 hash detection** to avoid re-processing unchanged files:

1. **First run**: All files are ingested; hashes stored in `file_hashes` collection
2. **Subsequent runs**: Only files with changed hashes are re-ingested
3. **Hash storage**: Uses a dedicated `file_hashes` ChromaDB collection (key-value style)

**Example workflow:**

```bash
# Initial ingest
$ uv run python -m elt_llm_ingest.runner --cfg dama_dmbok
✅ Ingestion complete: 11943 chunks indexed

# Re-run without rebuild (file unchanged)
$ uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild
✅ No changes detected - collection unchanged

# Re-run with force (re-process everything)
$ uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild --force
✅ Ingestion complete: 11943 chunks indexed
```

---

## Delete Collections

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

rebuild: true  # Rebuild collection on each run (default: true)
```

**Options:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `collection_name` | string | required | Name of the ChromaDB collection |
| `file_paths` | list | required | List of file paths to ingest |
| `metadata` | dict | optional | Metadata to attach to all documents |
| `rebuild` | bool | `true` | Whether to rebuild collection on each run |

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
│   ├── fa_data_architecture.yaml # FA Data Architecture config
│   ├── sad.yaml                  # SAD ingestion config
│   ├── leanix.yaml               # LeanIX ingestion config
│   └── supplier_assess.yaml      # Supplier assessment config
├── src/elt_llm_ingest/
│   ├── __init__.py
│   ├── runner.py                 # Generic runner (--cfg parameter)
│   ├── cli.py                    # CLI entry point
│   ├── ingest.py                 # Ingestion pipeline
│   └── file_hash.py              # File hash utilities (smart ingest)
└── tests/
```

## Dependencies

- `elt_llm_core` - Core RAG infrastructure
- `llama-index` - Document processing
- `llama-index-readers-file` - File format support
- `chromadb` - Vector database

## Prerequisites

- Python 3.11, 3.12, or 3.13 (ChromaDB is not yet compatible with Python 3.14)
- Ollama running locally: `ollama serve`
- Required models:
  ```bash
  ollama pull nomic-embed-text
  ollama pull llama3.2
  ```

## Troubleshooting

### Collection shows 0 documents after ingest

Check if the source files exist and are accessible:
```bash
uv run python -m elt_llm_ingest.runner --cfg <config> -v
```

### "No changes detected" but expected updates

The file hash hasn't changed. Use `--force` to re-ingest:
```bash
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --force
```

### ChromaDB connection errors

Check the persist directory path in `config/rag_config.yaml`:
```bash
uv run python -m elt_llm_ingest.runner --status -v
```

### Reset hash tracking

Delete and re-ingest to reset hash tracking:
```bash
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok
```

## See Also

- **RUNNERS.md** - Detailed command reference and workflows
- **elt_llm_query/** - Query module for searching ingested documents
- **elt_llm_core/** - Core RAG utilities and configuration
