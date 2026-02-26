# elt-llm-query

Query interface for RAG systems with multi-collection and hybrid vector+keyword search.

## Overview

- Single-query and interactive (REPL) modes
- Queries one or many ChromaDB collections in a single LLM call
- Hybrid search: BM25 keyword retrieval fused with vector similarity (reciprocal rerank)
- Collection prefix resolution — `fa_leanix` expands to all `fa_leanix_*` collections at runtime
- Source attribution with similarity scores in every response
- Query profiles (`llm_rag_profile/*.yaml`) configure which collections and system prompt to use

## Prerequisites

- Python 3.11, 3.12, or 3.13
- Ollama running locally with the required models:
  ```bash
  ollama serve
  ollama pull nomic-embed-text
  ollama pull qwen2.5:14b
  ```
- Collections must be ingested before querying — see [elt_llm_ingest/README.md](../elt_llm_ingest/README.md)

## Installation

```bash
cd elt_llm_query
uv sync
```

---

## Commands

**All commands are run from the repository root.**

### List available profiles

```bash
uv run python -m elt_llm_query.runner --list
```

Shows each profile name, the collections it targets, and usage examples.

### Single query

```bash
uv run python -m elt_llm_query.runner --cfg <profile> -q "Your question here"
```

### Interactive session

```bash
uv run python -m elt_llm_query.runner --cfg <profile>
# Type questions at the prompt — 'quit' or 'exit' to stop
```

### Log level

```bash
# Pipeline detail (retrieval, collection resolution)
uv run python -m elt_llm_query.runner --cfg <profile> -q "..." --log-level INFO

# Full debug (LlamaIndex internals, ChromaDB calls)
uv run python -m elt_llm_query.runner --cfg <profile> -q "..." -v
```

---

## Query Profiles

Profiles live in `llm_rag_profile/`. See [QUERY.md](QUERY.md) for example queries for each profile.

| Profile | Collections queried | Use for |
|---------|-------------------|---------|
| `leanix_relationships` | `fa_leanix_relationships`, `fa_leanix_overview` | The 16 domain-level relationships and cardinalities |
| `leanix_only` | All `fa_leanix_*` (via prefix) | Broad FA conceptual model — entities, domains, structure |
| `leanix_fa_combined` | All `fa_leanix_*` + `fa_handbook` | Gap analysis, handbook enrichment, governance-to-model mapping |
| `fa_data_management` | All `fa_leanix_*` + `fa_handbook` + `fa_data_architecture` + `dama_dmbok` | Full data management programme queries |
| `dama_fa_full` | `dama_dmbok` + `fa_handbook` + `fa_data_architecture` + key `fa_leanix_*` | DAMA-aligned queries with FA architecture context |
| `dama_fa_combined` | `dama_dmbok` + `fa_handbook` | Data management vs FA governance |
| `dama_only` | `dama_dmbok` | DAMA-DMBOK questions |
| `fa_handbook_only` | `fa_handbook` | FA rules, governance, and regulations |
| `all_collections` | All ingested collections | Broadest possible search |
| `architecture_focus` | Specific `fa_leanix_*` | Architecture queries (partial — `fa_ea_sad` not yet ingested) |
| `vendor_assessment` | Specific `fa_leanix_*` | Vendor queries (partial — `supplier_assess` not yet ingested) |

---

## Profile Configuration

### Profile YAML format

```yaml
# Explicit collections
collections:
  - name: "fa_handbook"
  - name: "dama_dmbok"

# Prefix expansion — resolves to all matching collections at runtime
collection_prefixes:
  - name: "fa_leanix"       # → fa_leanix_agreements, fa_leanix_relationships, etc.

query:
  similarity_top_k: 10      # chunks retrieved across all collections combined
  system_prompt: |
    You are a helpful assistant...
```

| Field | Description |
|-------|-------------|
| `collections[].name` | Exact ChromaDB collection name |
| `collection_prefixes[].name` | Prefix — resolves to all `{prefix}_*` collections at runtime |
| `query.similarity_top_k` | Total chunks kept after merging results from all collections |
| `query.use_hybrid_search` | Enable BM25 + vector fusion (default: `true`) |
| `query.use_reranker` | Enable embedding reranker after retrieval (default: `true`) |
| `query.reranker_strategy` | `"embedding"` (Ollama cosine similarity, local) or `"cross-encoder"` (requires HuggingFace) |
| `query.reranker_retrieve_k` | Number of candidates to retrieve before reranking (default: `20`) |
| `query.reranker_top_k` | Number of chunks to keep after reranking (default: `8`) |
| `query.system_prompt` | System prompt for every LLM call under this profile |

### Creating a custom profile

```bash
cat > elt_llm_query/llm_rag_profile/my_profile.yaml << 'EOF'
collections:
  - name: "fa_handbook"

collection_prefixes:
  - name: "fa_leanix"

query:
  similarity_top_k: 10
  system_prompt: |
    You are a helpful assistant...
EOF

uv run python -m elt_llm_query.runner --cfg my_profile -q "Your question"
```

---

## How Multi-Collection Retrieval Works

1. **Retrieve** — each collection is searched independently using hybrid BM25 + vector search
2. **Merge** — chunks from all collections are combined and sorted by score
3. **Trim** — the top `similarity_top_k` chunks are kept across all collections
4. **Rerank** — an embedding reranker re-scores candidates using fresh cosine similarity, replacing flat RRF scores with discriminative relevance scores
5. **Synthesise** — a single LLM call receives all combined chunks as context

The Sources section in the output shows which collection each chunk came from and its similarity score, making it straightforward to verify which source drove each part of the response.

---

## Module Structure

```
elt_llm_query/
├── llm_rag_profile/
│   ├── leanix_relationships.yaml    # 16 domain relationships — targeted retrieval
│   ├── leanix_only.yaml             # All fa_leanix_* via prefix
│   ├── leanix_fa_combined.yaml      # LeanIX + FA Handbook
│   ├── fa_data_management.yaml      # LeanIX + Handbook + Data Arch + DAMA
│   ├── dama_fa_full.yaml            # DAMA + Handbook + Data Arch + key LeanIX
│   ├── dama_fa_combined.yaml        # DAMA + FA Handbook
│   ├── dama_only.yaml
│   ├── fa_handbook_only.yaml
│   ├── all_collections.yaml
│   ├── architecture_focus.yaml      # partial — fa_ea_sad not yet ingested
│   └── vendor_assessment.yaml       # partial — supplier_assess not yet ingested
├── QUERY.md                         # All example and validation queries
├── src/elt_llm_query/
│   ├── runner.py                    # Main CLI: --cfg, --list, -q, --log-level
│   ├── query.py                     # Query functions, hybrid retriever, prefix resolution
│   └── cli.py                       # Legacy CLI entry point (use runner.py)
└── tests/
```

---

## Troubleshooting

### "No collections found" or empty response

Check collections are ingested:

```bash
uv run python -m elt_llm_ingest.runner --status
```

### Relationships missing from response

`fa_leanix_relationships` should show 4 chunks and 4 BM25 nodes. If not, re-ingest:

```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_ea_leanix
```

### FA Handbook absent from combined query sources

With `leanix_fa_combined`, frame the question to explicitly span both sources — e.g. *"...and what does the FA Handbook say about..."*

### Slow responses

Response time is dominated by the Ollama LLM call. Reduce `similarity_top_k` in the profile to give the LLM less context.

---

## See Also

- **[QUERY.md](QUERY.md)** — all example and validation queries, organised by profile
- **[elt_llm_ingest/README.md](../elt_llm_ingest/README.md)** — ingestion, clean slate, batch rebuild, status
- **elt_llm_core/** — ChromaDB client, query engine, BM25 hybrid retriever
