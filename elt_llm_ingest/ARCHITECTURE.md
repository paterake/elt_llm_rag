# elt_llm_ingest — Architecture

## Purpose
Ingest heterogeneous documents into a RAG-ready store with:
- Dense vectors in ChromaDB for semantic retrieval
- BM25 docstores on disk for keyword retrieval
- Smart change detection and collection-level rebuilds

**See also**: [RAG_STRATEGY.md](../RAG_STRATEGY.md) for detailed documentation on how the ingested data is used in hybrid retrieval and reranking.

## Pipeline ([ingest.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/src/elt_llm_ingest/ingest.py))
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

---

## PDF Ingestion Flow (FA Handbook)

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
              ↓                               ↓
              └───────────────┬───────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. Retrieval: Hybrid (BM25 + Vector)                            │
├─────────────────────────────────────────────────────────────────┤
│ Query → BM25 (docstore) + Vector (ChromaDB)                     │
│       → Rerank (cross-encoder or embedding)                     │
│       → Top-k → LLM synthesis                                   │
└─────────────────────────────────────────────────────────────────┘
```

**Performance (FA Handbook 2025-26)**:
- PDF → Markdown: 64 seconds (2.2M chars)
- Chunking: ~5 seconds (3,375 nodes)
- Embedding: 94 seconds (Ollama, nomic-embed-text)
- **Total**: ~3 minutes

---

## Change Detection ([file_hash.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/src/elt_llm_ingest/file_hash.py))
- Stores per-file SHA256 keyed by `collection_name::file_path` in a dedicated `file_hashes` collection
- Skips unchanged files; supports selective removal on rebuild

## Preprocessors ([preprocessor.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/src/elt_llm_ingest/preprocessor.py))

**`LeanIXPreprocessor`** (`output_format: json_md`) — LeanIX Conceptual Model (draw.io XML):
- Calls `doc_leanix_parser.py` to parse the XML into corrected domain/subtype/entity structure
- Writes `<stem>_model.json` next to source XML — canonical structured output for consumers
- Writes flat per-entity and per-relationship Markdown → ChromaDB collections (for semantic search)
- Fan-out: single XML parse → JSON sidecar + ChromaDB, not two separate parses

**`LeanIXInventoryPreprocessor`** (`output_format: split`) — LeanIX Inventory (Excel):
- Reads all fact sheets from Excel export
- Writes `<stem>_inventory.json` next to source Excel — keyed by `fact_sheet_id` for O(1) lookup
- Writes per-type Markdown → per-type ChromaDB collections (`fa_leanix_global_inventory_*`)

**`DoclingPreprocessor`** — FA Handbook PDF:
- PDF → per-section Markdown via IBM Docling (DocLayNet + TableFormer models); first run downloads ~200MB to `~/.cache/docling/`, all subsequent runs are fully offline
- Layout-aware: detects headings, preserves table structure as markdown
- Splits document into sections (s01–s44), each → separate ChromaDB collection
- Output: `_section_splits/<stem>_sections/s*.md` → `fa_handbook_sNN` collections

**Split-mode**: one source → N collections via `collection_prefix` and section mapping

## Configuration
- Global RAG: [rag_config.yaml](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config/rag_config.yaml)
- Ingest configs: [config/](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/config)
  - `ingest_fa_leanix_dat_enterprise_conceptual_model.yaml`
  - `ingest_fa_leanix_global_inventory.yaml`
  - `ingest_fa_handbook.yaml`
  - `ingest_dama_dmbok.yaml`
  - `load_rag.yaml` (batch)

## Commands
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

## Notes
- Local-first: embeddings via Ollama; ChromaDB persisted under `persist_dir`
- Metadata: keep scalar (str/int/float/bool/None) — complex fields are dropped by the sanitizer
- Per-collection chunking overrides are supported via `IngestConfig.chunking_override`

