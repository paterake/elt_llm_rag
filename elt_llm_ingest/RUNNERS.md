# RAG Ingestion Runners - Quick Reference

## List Available Configs

```bash
uv run python -m elt_llm_ingest.runner --list
```

---

## Ingest Documents

### DAMA-DMBOK2R (Data Management Body of Knowledge)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

# Append mode (don't rebuild)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild
```

### FA Handbook (Financial Accounting)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg fa_handbook

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg fa_handbook -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --no-rebuild
```

### SAD (Solution Architecture Definition)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg sad

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg sad -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg sad --no-rebuild
```

### LeanIX (Architecture Platform)

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg leanix

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg leanix -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg leanix --no-rebuild
```

### Supplier Assessment

```bash
# Basic ingest
uv run python -m elt_llm_ingest.runner --cfg supplier_assess

# Verbose output
uv run python -m elt_llm_ingest.runner --cfg supplier_assess -v

# Append mode
uv run python -m elt_llm_ingest.runner --cfg supplier_assess --no-rebuild
```

---

## Delete Collections

### DAMA-DMBOK2R

```bash
# Delete (with confirmation)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete

# Delete (force, no confirmation)
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
```

### FA Handbook

```bash
# Delete (with confirmation)
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --delete

# Delete (force)
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --delete -f
```

### SAD

```bash
# Delete (with confirmation)
uv run python -m elt_llm_ingest.runner --cfg sad --delete

# Delete (force)
uv run python -m elt_llm_ingest.runner --cfg sad --delete -f
```

### LeanIX

```bash
# Delete (with confirmation)
uv run python -m elt_llm_ingest.runner --cfg leanix --delete

# Delete (force)
uv run python -m elt_llm_ingest.runner --cfg leanix --delete -f
```

### Supplier Assessment

```bash
# Delete (with confirmation)
uv run python -m elt_llm_ingest.runner --cfg supplier_assess --delete

# Delete (force)
uv run python -m elt_llm_ingest.runner --cfg supplier_assess --delete -f
```

---

## Query Documents

After ingesting, use `elt_llm_query` to query the documents:

```bash
# List query configs
uv run python -m elt_llm_query.runner --list

# Query DAMA-DMBOK
uv run python -m elt_llm_query.runner --cfg dama_only

# Query multiple collections
uv run python -m elt_llm_query.runner --cfg dama_fa_combined

# Single query
uv run python -m elt_llm_query.runner --cfg dama_only -q "What is data governance?"
```

---

## Common Workflows

### First-Time Setup

```bash
# 1. Pull required Ollama models
ollama pull nomic-embed-text
ollama pull llama3.2

# 2. Ingest all documents
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok
uv run python -m elt_llm_ingest.runner --cfg fa_handbook
uv run python -m elt_llm_ingest.runner --cfg sad
uv run python -m elt_llm_ingest.runner --cfg leanix
uv run python -m elt_llm_ingest.runner --cfg supplier_assess

# 3. Query
uv run python -m elt_llm_query.runner --cfg all_collections
```

### Rebuild a Collection

```bash
# Delete and re-ingest
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v
```

### Add New Document Version

```bash
# Append without rebuilding existing data
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild
```
