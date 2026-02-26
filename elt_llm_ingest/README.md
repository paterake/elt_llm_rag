# elt-llm-ingest

Generic document ingestion pipeline for RAG systems with smart change detection and document preprocessing.

## Overview

This package provides a reusable document ingestion pipeline that:

- Loads documents from multiple formats (PDF, DOCX, TXT, HTML, etc.)
- **Preprocesses documents** before embedding (e.g., LeanIX XML split into per-domain collections)
- Chunks documents using LlamaIndex sentence splitters (per-config chunk size override supported)
- Embeds chunks using Ollama (`nomic-embed-text`)
- Stores embeddings in ChromaDB
- Persists a parallel BM25 docstore alongside every collection for hybrid vector+keyword search
- **Smart ingest**: Automatically skips unchanged files using SHA256 hash detection

## Quick Start

## Installation

```bash
cd elt_llm_ingest
uv sync
```

```bash
# Check collection and BM25 docstore status
uv run python -m elt_llm_ingest.runner --status -v

# Full cleardown then rebuild all collections in one go
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Ingest a single collection
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok

# List available configs
uv run python -m elt_llm_ingest.runner --list
```

---

## Commands

**All commands are run from the repository root.**

### Check Collection Status

Shows every ChromaDB collection alongside its BM25 docstore node count. The `BM25` column tells you whether hybrid search is active.

```bash
# Compact view — collection name, chunk count, BM25 node count
uv run python -m elt_llm_ingest.runner --status

# Verbose view — also shows ChromaDB collection metadata
uv run python -m elt_llm_ingest.runner --status -v
```

Example output:

```
=== ChromaDB Status ===

Persist directory: /path/to/chroma_db

Collection Name                      Chunks  BM25 nodes   BM25
--------------------------------------------------------------
dama_dmbok                             2649        2649      ✅
fa_data_architecture                     66          66      ✅
fa_handbook                            3537        3537      ✅
fa_leanix_additional_entities             1           1      ✅
fa_leanix_agreements                      2           2      ✅
fa_leanix_campaign                        1           1      ✅
fa_leanix_location                        1           1      ✅
fa_leanix_overview                        1           1      ✅
fa_leanix_product                         1           1      ✅
fa_leanix_reference_data                  1           1      ✅
fa_leanix_relationships                   4           4      ✅
fa_leanix_static_data                     1           1      ✅
fa_leanix_time_bounded_groupings          1           1      ✅
fa_leanix_transaction_and_events          1           1      ✅
file_hashes                               3           -    n/a

Total: 15 collection(s), 6270 chunk(s)
```

**BM25 column legend:**

| Symbol | Meaning |
|--------|---------|
| ✅ | Docstore present with nodes — hybrid search active |
| ⚠️ | Docstore present but empty — hybrid search will fall back to vector-only |
| ❌ | No docstore found — hybrid search will fall back to vector-only |
| `n/a` | Internal collection (`file_hashes`) — no docstore expected |

---

### List Available Configs

```bash
uv run python -m elt_llm_ingest.runner --list
```

---

### Full Cleardown and Rebuild

To wipe all ChromaDB data and reload everything from scratch:

```bash
# Step 1: Delete the entire chroma_db directory
uv run python -m elt_llm_ingest.clean_slate

# Step 2: Re-ingest all collections via the batch config
uv run python -m elt_llm_ingest.runner --cfg load_rag
```

`clean_slate` reads `config/rag_config.yaml` to locate the persist directory and deletes it entirely — removing all collections and docstores in one operation.

`load_rag` is a batch meta-config (`config/load_rag.yaml`) that lists the individual ingest configs to run in sequence. Edit that file to control which collections are included in a full rebuild.

---

### Ingest a Single Collection

```bash
# Standard rebuild (clears collection, re-ingests all files)
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok -v

# Append mode — only re-ingests files whose SHA256 hash has changed
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --no-rebuild

# Force re-ingest everything regardless of hashes
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --force
```

**Ingest mode summary:**

| Mode | Flags | Behaviour |
|------|-------|-----------|
| Rebuild (default) | *(none)* | Clears collection and docstore, re-ingests all files, resets hash tracking |
| Append | `--no-rebuild` | Keeps existing data, only ingests changed or new files |
| Force | `--force` | Bypasses hash check — re-ingests all files regardless of changes |
| Force append | `--no-rebuild --force` | Keeps existing data but re-ingests every file unconditionally |

---

### Batch Ingest (Multiple Collections)

`load_rag.yaml` is a meta-config that runs multiple ingest configs in sequence:

```bash
uv run python -m elt_llm_ingest.runner --cfg load_rag
```

Contents of `config/load_rag.yaml`:

```yaml
file_paths:
  - "ingest_dama_dmbok.yaml"
  - "ingest_fa_data_architecture.yaml"
  - "ingest_fa_ea_leanix.yaml"
  - "ingest_fa_handbook.yaml"
```

Add or remove entries to control which collections are included in a batch run.

---

### Delete a Collection

```bash
# Delete with confirmation prompt
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --delete

# Delete without confirmation
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --delete -f
```

For **split-mode configs** (e.g. `ingest_fa_ea_leanix`), `--delete` removes all collections matching the prefix (`fa_leanix_*`) in a single operation:

```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_ea_leanix --delete -f
# Deletes: fa_leanix_overview, fa_leanix_agreements, fa_leanix_relationships, ...
```

---

## Available Configs

| Config name | Collection(s) produced | Notes |
|-------------|------------------------|-------|
| `ingest_dama_dmbok` | `dama_dmbok` | DAMA-DMBOK2R PDF |
| `ingest_fa_data_architecture` | `fa_data_architecture` | FA Data Architecture docs |
| `ingest_fa_ea_leanix` | `fa_leanix_*` (11 collections) | LeanIX XML — split mode, one collection per domain |
| `ingest_fa_handbook` | `fa_handbook` | FA Handbook 2025–26 PDF |
| `load_rag` | All of the above | Batch meta-config, runs all four in sequence |

---

## Configuration

### Ingestion Config (`config/ingest_*.yaml`)

**Standard single-collection config:**

```yaml
collection_name: "dama_dmbok"

file_paths:
  - "~/Documents/__data/books/DAMA-DMBOK2R_unlocked.pdf"

metadata:
  domain: "data_management"
  type: "body_of_knowledge"

# Optional: override global chunking for this collection
chunking:
  chunk_size: 512
  chunk_overlap: 64

rebuild: true
```

**Config fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `collection_name` | string | yes* | ChromaDB collection name. Mutually exclusive with `collection_prefix`. |
| `collection_prefix` | string | yes* | Prefix for split-mode ingestion (see below). Mutually exclusive with `collection_name`. |
| `file_paths` | list | yes | Source files to ingest |
| `metadata` | dict | no | Metadata attached to every chunk |
| `chunking.chunk_size` | int | no | Overrides global `rag_config.yaml` chunk size for this collection |
| `chunking.chunk_overlap` | int | no | Overrides global chunk overlap |
| `rebuild` | bool | no | Default `true`. Clears and rebuilds the collection each run |
| `preprocessor` | dict | no | Preprocessor config (see below) |

*Exactly one of `collection_name` or `collection_prefix` must be set.

---

### Split-Mode Ingestion (LeanIX)

When `collection_prefix` is set and the preprocessor uses `output_format: "split"`, one ChromaDB collection is created per logical section of the source document. This avoids chunking fragmentation when entity lists and relationships are interleaved.

```yaml
collection_prefix: "fa_leanix"

preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "split"
  enabled: true

file_paths:
  - "~/Documents/__data/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml"

metadata:
  domain: "architecture"
  type: "enterprise_architecture"
  source: "LeanIX"

chunking:
  chunk_size: 512
  chunk_overlap: 64
```

Collections produced (prefix `fa_leanix`):

| Collection | Content |
|------------|---------|
| `fa_leanix_overview` | Model summary and domain list |
| `fa_leanix_agreements` | AGREEMENTS domain entities |
| `fa_leanix_campaign` | CAMPAIGN domain entities |
| `fa_leanix_location` | LOCATION domain entities |
| `fa_leanix_product` | PRODUCT domain entities |
| `fa_leanix_reference_data` | REFERENCE DATA domain entities |
| `fa_leanix_static_data` | Static Data domain entities |
| `fa_leanix_time_bounded_groupings` | Time Bounded Groupings domain |
| `fa_leanix_transaction_and_events` | TRANSACTION AND EVENTS domain |
| `fa_leanix_additional_entities` | Party types, channel types, accounts, assets |
| `fa_leanix_relationships` | All domain-level relationships (dedicated collection) |

---

### Preprocessor Configuration

Preprocessors transform source files into a RAG-friendly format before chunking and embedding.

**Available preprocessors:**

| Class | Output formats | Description |
|-------|---------------|-------------|
| `LeanIXPreprocessor` | `markdown`, `json`, `both`, `split` | Extracts entities and relationships from LeanIX draw.io XML exports |
| `IdentityPreprocessor` | *(n/a)* | Pass-through — no transformation applied |

**LeanIX output formats:**

| `output_format` | Behaviour |
|-----------------|-----------|
| `markdown` | Single Markdown file, all domains and relationships combined |
| `json` | Single JSON file |
| `both` | Both Markdown and JSON |
| `split` | One Markdown file per domain section + one for relationships; each loaded into its own collection. Requires `collection_prefix`. |

**Preprocessor config fields:**

| Field | Type | Description |
|-------|------|-------------|
| `module` | string | Python module containing the preprocessor class |
| `class` | string | Class name |
| `output_format` | string | Format-specific output mode (default: `markdown`) |
| `output_suffix` | string | Suffix for generated files in single-file modes (default: `_processed`) |
| `enabled` | bool | Set `false` to disable preprocessing (defaults to `IdentityPreprocessor`) |

---

### RAG Config (`config/rag_config.yaml`)

Shared settings for ChromaDB, Ollama, and chunking. These are the global defaults; individual ingest configs can override `chunking` per collection.

```yaml
chroma:
  persist_dir: "../chroma_db"
  tenant: "rag_tenants"
  database: "knowledge_base"

ollama:
  base_url: "http://localhost:11434"
  embedding_model: "nomic-embed-text"
  llm_model: "qwen2.5:14b"
  embed_batch_size: 1
  context_window: 8192

chunking:
  strategy: "sentence"
  chunk_size: 256
  chunk_overlap: 32

query:
  similarity_top_k: 10
  use_hybrid_search: true
  use_reranker: true
  reranker_strategy: "embedding"   # "embedding" (Ollama/local) | "cross-encoder" (requires HuggingFace)
  reranker_retrieve_k: 20          # candidates fetched before reranking
  reranker_top_k: 8                # chunks kept after reranking
```

---

### Smart Ingest (Change Detection)

The ingestion system uses **file-level SHA256 hash detection** to avoid re-processing unchanged files:

1. **First run**: All files are ingested; hashes stored in the `file_hashes` ChromaDB collection
2. **Subsequent runs**: Only files whose hash has changed are re-ingested
3. **Rebuild mode** (default): Hashes are cleared and all files are re-processed regardless

```bash
# Initial ingest
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok
# ✅ Ingestion complete: 2649 chunks indexed

# Re-run in append mode (file unchanged — nothing to do)
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --no-rebuild
# ✅ No changes detected - collection unchanged

# Force re-process everything in append mode
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --no-rebuild --force
# ✅ Ingestion complete: 2649 chunks indexed
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `RAG_CHROMA_DIR` | Override the ChromaDB persist directory from `rag_config.yaml` |
| `RAG_DOCS_DIR` | Override the base directory for source document resolution |

---

## Module Structure

```
elt_llm_ingest/
├── config/
│   ├── rag_config.yaml               # Shared RAG settings (ChromaDB, Ollama, chunking)
│   ├── load_rag.yaml                 # Batch meta-config — lists all ingest configs to run
│   ├── ingest_dama_dmbok.yaml        # DAMA-DMBOK ingestion config
│   ├── ingest_fa_data_architecture.yaml
│   ├── ingest_fa_ea_leanix.yaml      # LeanIX XML — split mode (11 collections)
│   └── ingest_fa_handbook.yaml
├── src/elt_llm_ingest/
│   ├── runner.py                     # Main CLI: --cfg, --status, --list, --delete
│   ├── clean_slate.py                # Wipe entire chroma_db directory
│   ├── batch_loader.py               # Parses batch meta-configs (load_rag.yaml)
│   ├── ingest.py                     # Ingestion pipeline (load → chunk → embed → store)
│   ├── preprocessor.py               # Preprocessor framework and LeanIXPreprocessor
│   ├── doc_leanix_parser.py          # LeanIX XML parser (entities + relationships)
│   ├── file_hash.py                  # SHA256 hash tracking for smart ingest
│   └── cli.py                        # Legacy CLI entry point (use runner.py instead)
└── tests/
```

---

## Prerequisites

- Python 3.11, 3.12, or 3.13
- Ollama running locally:
  ```bash
  ollama serve
  ollama pull nomic-embed-text
  ollama pull qwen2.5:14b
  ```

---

## Supported Source Formats

**Via LlamaIndex readers (direct):**
- PDF (`.pdf`)
- Word (`.docx`)
- Text (`.txt`)
- HTML (`.html`)
- Markdown (`.md`)
- CSV (`.csv`)
- JSON (`.json`)

**Via preprocessors:**
- LeanIX draw.io XML (`.xml`) → structured Markdown (single file or one file per domain section)

---

## Troubleshooting

### BM25 column shows ❌ or ⚠️ after ingest

The docstore is written during ingestion. If missing or empty, hybrid search silently falls back to vector-only. Fix by re-ingesting with rebuild:

```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok
uv run python -m elt_llm_ingest.runner --status
```

### "No changes detected" but updates were expected

The file hash matches the stored hash. Use `--force` to bypass:

```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --no-rebuild --force
```

### Collection shows 0 chunks after ingest

Check file paths are accessible and Ollama is running, then re-run with verbose output:

```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok -v
```

### Reset everything and start clean

```bash
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.runner --cfg load_rag
```

### ChromaDB connection errors

Check the `persist_dir` in `config/rag_config.yaml` is writable and the path resolves correctly relative to the config file location.

---

## See Also

- **elt_llm_query/** — Query module (interactive and single-shot queries, multi-collection profiles)
- **elt_llm_core/** — Core RAG utilities, ChromaDB client, query engine
