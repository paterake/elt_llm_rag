# elt-llm-query

Query interface for RAG collections. See [ARCHITECTURE.md](../ARCHITECTURE.md) for design documentation.

**All commands run from the repository root.**

---

## Prerequisites

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull qwen2.5:14b
```

Collections must be ingested first — see [elt_llm_ingest/README.md](../elt_llm_ingest/README.md).

---

## Query

```bash
cd elt_llm_query
uv sync

# List available profiles
uv run python -m elt_llm_query.runner --list

# Interactive session
uv run python -m elt_llm_query.runner --cfg <profile>

# Single query
uv run python -m elt_llm_query.runner --cfg <profile> -q "Your question here"

# Pipeline detail (retrieval, collection resolution)
uv run python -m elt_llm_query.runner --cfg <profile> -q "..." --log-level INFO

# Full debug (LlamaIndex internals, ChromaDB calls)
uv run python -m elt_llm_query.runner --cfg <profile> -q "..." -v
```

---

## Profiles

| Profile | Collections |
|---------|-------------|
| `leanix_relationships` | `fa_leanix_relationships`, `fa_leanix_overview` |
| `leanix_only` | All `fa_leanix_*` (via prefix) |
| `leanix_fa_combined` | All `fa_leanix_*` + `fa_handbook` |
| `fa_data_management` | All `fa_leanix_*` + `fa_handbook` + `fa_data_architecture` + `dama_dmbok` |
| `dama_fa_full` | `dama_dmbok` + `fa_handbook` + `fa_data_architecture` + key `fa_leanix_*` |
| `dama_fa_combined` | `dama_dmbok` + `fa_handbook` |
| `dama_only` | `dama_dmbok` |
| `fa_handbook_only` | `fa_handbook` |
| `all_collections` | All ingested collections |

See [QUERY.md](QUERY.md) for example queries by profile.
