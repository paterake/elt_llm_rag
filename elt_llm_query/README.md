# elt-llm-query

Query interface for RAG systems with multi-collection support.

## Overview

This package provides a flexible query interface for RAG (Retrieval-Augmented Generation) systems:

- Query single or multiple collections
- Load existing indices from ChromaDB
- Interactive and single-query modes
- Source attribution with scores
- Configurable collection combinations

## Installation

```bash
cd elt_llm_query
uv sync
```

## Usage

### List Available Configs

```bash
uv run python -m elt_llm_query.runner --list
```

### Query Single Collection

```bash
# Interactive mode (DAMA only)
uv run python -m elt_llm_query.runner --cfg dama_only

# Single query
uv run python -m elt_llm_query.runner --cfg dama_only -q "What is data governance?"

# Verbose output
uv run python -m elt_llm_query.runner --cfg dama_only -v
```

### Query Multiple Collections

```bash
# Query DAMA + FA Handbook together
uv run python -m elt_llm_query.runner --cfg dama_fa_combined -q "How does data governance relate to financial controls?"

# Query all collections
uv run python -m elt_llm_query.runner --cfg all_collections -q "..."

# Interactive mode with multiple collections
uv run python -m elt_llm_query.runner --cfg dama_fa_combined
```

## Example Configs

The `examples/` directory includes predefined query configs:

| Config | Collections | Use Case |
|--------|-------------|----------|
| `dama_only.yaml` | DAMA-DMBOK | Data management questions |
| `fa_handbook_only.yaml` | FA Handbook | Financial accounting questions |
| `dama_fa_combined.yaml` | DAMA + FA | Cross-domain questions |
| `all_collections.yaml` | All | General queries across all docs |
| `architecture_focus.yaml` | SAD + LeanIX | Architecture questions |
| `vendor_assessment.yaml` | LeanIX + Supplier | Vendor evaluation |

## Configuration

### Query Config (`examples/*.yaml`)

```yaml
# Collections to query
collections:
  - name: "dama_dmbok"
    weight: 1.0
  - name: "fa_handbook"
    weight: 1.0

# Query settings
query:
  similarity_top_k: 10
  system_prompt: |
    You are a helpful assistant that answers questions based on the provided documents.
    Always ground your answers in the retrieved content.
    Cite the source when relevant.
```

### Creating Custom Query Configs

1. Create a new config in `examples/`:

```yaml
# examples/my_custom.yaml
collections:
  - name: "dama_dmbok"
  - name: "sad"

query:
  similarity_top_k: 10
  system_prompt: |
    Answer based on DAMA-DMBOK and SAD documentation.
```

2. Query:

```bash
uv run python -m elt_llm_query.runner --cfg my_custom -q "..."
```

## Module Structure

```
elt_llm_query/
├── examples/
│   ├── dama_only.yaml           # Query DAMA only
│   ├── fa_handbook_only.yaml    # Query FA only
│   ├── dama_fa_combined.yaml    # Query both
│   ├── all_collections.yaml     # Query all
│   ├── architecture_focus.yaml  # Architecture docs
│   └── vendor_assessment.yaml   # Vendor docs
├── src/elt_llm_query/
│   ├── __init__.py
│   ├── runner.py                # Generic runner (--cfg parameter)
│   └── query.py                 # Query functions
└── tests/
```

## Multi-Collection Querying

When querying multiple collections:

1. Each collection is searched independently
2. Results are combined and sorted by relevance score
3. Top-k results are returned across all collections
4. The LLM response is based on the combined context

This allows you to:
- Ask questions that span multiple domains
- Get unified answers from diverse sources
- Maintain separation of concerns in ingestion

## Dependencies

- `elt_llm_core` - Core RAG infrastructure
- `llama-index` - Index management

## Prerequisites

- Python 3.11, 3.12, or 3.13 (ChromaDB is not yet compatible with Python 3.14)
- Ollama running locally: `ollama serve`
- Required models:
  ```bash
  ollama pull nomic-embed-text
  ollama pull llama3.2
  ```

## Related Packages

- `elt_llm_ingest` - Document ingestion pipeline
- `elt_llm_core` - Core RAG infrastructure
