# elt_llm_ingest — Architecture

**Module**: `elt_llm_ingest`  
**Role**: Document ingestion into RAG-ready store

**Start here**: Read [ARCHITECTURE.md](../ARCHITECTURE.md) §5 for the big picture on ingestion strategies and the JSON sidecar pattern. This document covers module-specific implementation details.

---

## Table of Contents

- [1. Purpose](#1-purpose)
- [2. Pipeline Overview](#2-pipeline-overview)
- [3. PDF Ingestion Flow](#3-pdf-ingestion-flow)
- [4. Preprocessors](#4-preprocessors)
- [5. Change Detection](#5-change-detection)
- [6. Configuration](#6-configuration)
- [7. Commands](#7-commands)

---

## 1. Purpose

Ingest heterogeneous documents into a RAG-ready store with:
- Dense vectors in ChromaDB for semantic retrieval
- BM25 docstores on disk for keyword retrieval
- Smart change detection and collection-level rebuilds

---

## 2. Pipeline Overview

```
1. Load files (PDF, PPTX, DOCX, TXT, HTML, CSV/XML via preprocessors)
   - Optional preprocessing (e.g., LeanIX XML → Markdown; Excel inventory enrichment)
   - Scalar-only metadata sanitization to satisfy Chroma constraints

2. Chunk and transform
   - Sentence splitter (configurable `chunk_size`, `chunk_overlap`)

3. Persist two stores
   - ChromaDB vectors (per collection)
   - SimpleDocumentStore persisted to disk for BM25 hybrid search

4. Rebuild / Append
   - `rebuild: true` deletes the collection and resets file-hash tracking
   - `--no-rebuild` appends only changed files (SHA256 detection)
```

---

## 3. PDF Ingestion Flow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. Preprocessing: DoclingPreprocessor                           │
├─────────────────────────────────────────────────────────────────┤
│ Input:  FA_Handbook_2025-26.pdf                                 │
│         ↓ Docling StandardPipeline (DocLayNet + TableFormer)    │
│ Output: per-section .md files (2.5M chars, ~250s)               │
│         - Section splits: fa_handbook_s01 … fa_handbook_s44     │
│         - Tables as markdown pipe-delimited rows                │
│         - Cached at _section_splits/ (re-run skips Docling)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. Document Loading: load_documents()                           │
├─────────────────────────────────────────────────────────────────┤
│ Input:  _clean.md                                               │
│         ↓ LlamaIndex SimpleDirectoryReader                      │
│ Output: List[Document]                                          │
│         - doc.text: markdown content                            │
│         - doc.metadata: {domain, type, source, source_file}     │
│         - Metadata sanitized: only str/int/float/bool/None      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. Chunking: SentenceSplitter                                   │
├─────────────────────────────────────────────────────────────────┤
│ Input:  List[Document]                                          │
│         ↓ SentenceSplitter(chunk_size=512, chunk_overlap=64)    │
│ Output: List[Node] (3,375 nodes for FA Handbook)                │
│         - Each node: text + metadata + node_id                  │
│         - Sentence-aware boundaries                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
┌─────────────────────────┐     ┌─────────────────────────┐
│ 4a. Vector Store        │     │ 4b. BM25 Docstore       │
├─────────────────────────┤     ├─────────────────────────┤
│ ChromaDB                │     │ SimpleDocumentStore     │
│ - Embeddings via Ollama │     │ - Persisted to disk     │
│   (nomic-embed-text)    │     │   (_docstore/)          │
│ - Collection:           │     │ - Keyword search (BM25) │
│   fa_handbook           │     │ - Hybrid retrieval      │
│ - 3,375 nodes           │     │ - Same nodes as ChromaDB│
│ - 768 dimensions        │     │                         │
└─────────────────────────┘     └─────────────────────────┘
```

**Performance (FA Handbook 2025-26)**:
- PDF → Markdown: 64 seconds (2.2M chars)
- Chunking: ~5 seconds (3,375 nodes)
- Embedding: 94 seconds (Ollama, nomic-embed-text)
- **Total**: ~3 minutes

---

## 4. Preprocessors

### 4.1 LeanIXPreprocessor (`output_format: json_md`)

**Source**: LeanIX Conceptual Model (draw.io XML)

**Process**:
- Calls `doc_leanix_parser.py` to parse the XML into corrected domain/subtype/entity structure
- Writes `<stem>_model.json` next to source XML — canonical structured output for consumers
- Writes flat per-entity and per-relationship Markdown → ChromaDB collections (for semantic search)
- Fan-out: single XML parse → JSON sidecar + ChromaDB, not two separate parses

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "json_md"
  collection_prefix: "fa_leanix_dat_enterprise_conceptual_model"
```

---

### 4.2 LeanIXInventoryPreprocessor (`output_format: split`)

**Source**: LeanIX Inventory (Excel)

**Process**:
- Reads all fact sheets from first non-ReadMe sheet (timestamp-named export)
- Groups by `type` field (DataObject, Interface, Application, etc.)
- Generates per-type Markdown files (split mode)
- Writes `<stem>_inventory.json` next to source Excel — keyed by `fact_sheet_id` for O(1) lookup

**Fact Sheet Types**:
| Type | Collection Suffix | Count |
|------|-------------------|-------|
| DataObject | `dataobject` | 229 |
| Interface | `interface` | 271 |
| Application | `application` | 215 |
| BusinessCapability | `capability` | 272 |
| Organization | `organization` | 115 |
| ITComponent | `itcomponent` | 180 |
| Provider | `provider` | 74 |
| Objective | `objective` | 59 |

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXInventoryPreprocessor"
  output_format: "split"
  collection_prefix: "fa_leanix_global_inventory"
```

---

### 4.3 DoclingPreprocessor

**Source**: FA Handbook PDF

**Process**:
- PDF → per-section Markdown via IBM Docling (DocLayNet + TableFormer models)
- First run downloads ~200MB to `~/.cache/docling/`, all subsequent runs are fully offline
- Layout-aware: detects headings, preserves table structure as markdown
- Splits document into sections (s01–s44), each → separate ChromaDB collection
- Output: `_section_splits/<stem>_sections/s*.md` → `fa_handbook_sNN` collections

**Split-mode**: One source → N collections via `collection_prefix` and section mapping

---

## 5. Change Detection

**File**: [`file_hash.py`](src/elt_llm_ingest/file_hash.py)

- Stores per-file SHA256 keyed by `collection_name::file_path` in a dedicated `file_hashes` collection
- Skips unchanged files; supports selective removal on rebuild

---

## 6. Configuration

**Global RAG**: [`rag_config.yaml`](config/rag_config.yaml)

**Ingest configs**: [`config/`](config/)
- `ingest_fa_leanix_dat_enterprise_conceptual_model.yaml`
- `ingest_fa_leanix_global_inventory.yaml`
- `ingest_fa_handbook.yaml`
- `ingest_dama_dmbok.yaml`
- `load_rag.yaml` (batch)

---

## 7. Commands

See [README.md](README.md) for the full command reference.

```bash
# List configs and examples
uv run python -m elt_llm_ingest.runner --list

# Ingest a single config (rebuild on)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook

# Append mode (skip unchanged)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook --no-rebuild

# Batch ingest all collections
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Wipe everything or selective prefixes
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix
```

---

## Notes

- **Local-first**: embeddings via Ollama; ChromaDB persisted under `persist_dir`
- **Metadata**: keep scalar (str/int/float/bool/None) — complex fields are dropped by the sanitizer
- **Per-collection chunking overrides** are supported via `IngestConfig.chunking_override`
