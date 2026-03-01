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

## Change Detection ([file_hash.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/src/elt_llm_ingest/file_hash.py))
- Stores per-file SHA256 keyed by `collection_name::file_path` in a dedicated `file_hashes` collection
- Skips unchanged files; supports selective removal on rebuild

## Preprocessors ([preprocessor.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_ingest/src/elt_llm_ingest/preprocessor.py))
- LeanIX Conceptual Model (draw.io XML) → Markdown sections
- LeanIX Inventory (Excel) enrichment for descriptions and attributes
- Split-mode: one source → N collections via `collection_prefix` and section mapping

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

