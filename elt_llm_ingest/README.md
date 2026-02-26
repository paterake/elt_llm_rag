# elt-llm-ingest

Document ingestion pipeline. See [ARCHITECTURE.md](../ARCHITECTURE.md) for design documentation.

**All commands run from the repository root.**

---

## Prerequisites

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
```

---

## Status

```bash
# Compact view — collection name, chunk count, BM25 node count
uv run python -m elt_llm_ingest.runner --status

# Verbose — also shows collection metadata
uv run python -m elt_llm_ingest.runner --status -v
```

---

## Ingest

```bash
# List available configs
uv run python -m elt_llm_ingest.runner --list

# Ingest all collections (batch)
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Ingest a single collection
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_ea_leanix
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_data_architecture

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok -v

# Append mode — only re-ingests changed or new files
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --no-rebuild

# Force re-ingest everything regardless of file hashes
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --force

# Force append — keeps existing data, re-ingests every file unconditionally
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --no-rebuild --force
```

---

## Delete

```bash
# Delete with confirmation prompt
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --delete

# Delete without confirmation
uv run python -m elt_llm_ingest.runner --cfg ingest_dama_dmbok --delete -f

# Delete all fa_leanix_* collections (split-mode config)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_ea_leanix --delete -f
```

---

## Full Reset

```bash
# Wipe all ChromaDB data
uv run python -m elt_llm_ingest.clean_slate

# Rebuild all collections
uv run python -m elt_llm_ingest.runner --cfg load_rag
```
