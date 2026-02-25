# Fixes Required for LLM Collection Instantiation

## Summary

The RAG system has **two separate config systems** that need to be aligned:

| System | Location | Purpose |
|--------|----------|---------|
| **Ingestion** | `elt_llm_ingest/config/ingest_*.yaml` | Defines what to embed + collection name |
| **Query** | `elt_llm_query/examples/*_collections.yaml` | Defines which collections to search |

---

## Issue 1: Collection Name Mismatch

### Problem
```yaml
# ingest_fa_ea_leanix.yaml
collection_name: "fa_ea_leanix"  # ← Ingestion uses this name

# leanix_only.yaml
collections:
  - name: "leanix"  # ← Query looks for this name (MISMATCH!)
```

### Fix Required

**Option A: Update query configs to match ingestion** (Recommended)
```yaml
# elt_llm_query/examples/leanix_only.yaml
collections:
  - name: "fa_ea_leanix"  # Match ingestion config
```

**Option B: Update ingestion to match query**
```yaml
# elt_llm_ingest/config/ingest_fa_ea_leanix.yaml
collection_name: "leanix"  # Match query config
```

**Action:** Update `elt_llm_query/examples/*.yaml` to use correct collection names:
- `leanix` → `fa_ea_leanix`
- Verify `fa_handbook`, `dama_dmbok`, `sad`, `supplier_assess` match ingestion configs

---

## Issue 2: No Collection Validation

### Problem
Query runner doesn't check if collections exist before querying:
```python
# query.py:query_collections()
indices = load_indices(collection_names, rag_config)
if not indices:
    return QueryResult(response="No collections found...")
```

If a collection name is wrong, it silently fails and queries fewer collections.

### Fix Required

Add collection validation in `query.py`:

```python
# elt_llm_query/src/elt_llm_query/query.py

def validate_collections(collection_names: list[str], rag_config: RagConfig) -> list[str]:
    """Validate that collections exist in ChromaDB.
    
    Returns list of valid collection names (subset of input).
    """
    from elt_llm_core.vector_store import create_chroma_client
    
    chroma_client = create_chroma_client(rag_config.chroma)
    existing = [c.name for c in chroma_client.list_collections()]
    
    valid = []
    invalid = []
    for name in collection_names:
        if name in existing:
            valid.append(name)
        else:
            invalid.append(name)
    
    if invalid:
        logger.warning("Collections not found: %s. Available: %s", invalid, existing)
    
    return valid
```

Then use in `query_collections()`:
```python
def query_collections(...) -> QueryResult:
    # Validate collections first
    valid_collections = validate_collections(collection_names, rag_config)
    if not valid_collections:
        return QueryResult(response="No valid collections found...", source_nodes=[])
    
    indices = load_indices(valid_collections, rag_config)
    ...
```

---

## Issue 3: Unused Weight Parameter

### Problem
```yaml
# all_collections.yaml
collections:
  - name: "dama_dmbok"
    weight: 1.0  # ← Defined but never used
```

### Fix Required (Optional Enhancement)

If you want weighted retrieval:

```python
# In query_collections()
weighted_nodes = []
for index, name, coll_data in zip(indices, collection_names, collections_data):
    weight = coll_data.get("weight", 1.0)
    nodes = retriever.retrieve(query)
    # Apply weight to scores
    for node in nodes:
        node.score = (node.score or 0.0) * weight
    weighted_nodes.extend(nodes)

# Sort by weighted score
weighted_nodes.sort(key=lambda x: x.score, reverse=True)
all_nodes = weighted_nodes[:top_k]
```

**Decision:** Do you want weighted retrieval, or remove the weight field?

---

## Issue 4: Config Discovery

### Problem
Query runner has to guess where configs are:
```python
def get_examples_dir() -> Path:
    # Tries multiple locations...
```

### Fix Required

Add a query config section to `rag_config.yaml`:

```yaml
# rag_config.yaml
query_configs:
  dir: "./elt_llm_query/examples"
  default_config: "all_collections"
```

Or create a registry:
```yaml
# New file: elt_llm_query/configs/registry.yaml
configs:
  leanix_only:
    path: "leanix_only.yaml"
    description: "Query LeanIX EA model only"
    collections: ["fa_ea_leanix"]
  
  fa_handbook_only:
    path: "fa_handbook_only.yaml"
    description: "Query FA Handbook only"
    collections: ["fa_handbook"]
  
  all_collections:
    path: "all_collections.yaml"
    description: "Query all ingested collections"
    collections: ["dama_dmbok", "fa_handbook", "sad", "fa_ea_leanix", "supplier_assess"]
```

---

## Issue 5: LLM Model Configuration

### Problem
Query configs can override system prompt but not LLM model:
```yaml
# leanix_only.yaml
query:
  similarity_top_k: 5
  system_prompt: "..."  # Can override
  # llm_model: ???  # Can't override - uses rag_config default
```

### Fix Required (Optional)

Add LLM override support:

```yaml
# Query config
query:
  similarity_top_k: 5
  system_prompt: "..."
  llm_model: "qwen2.5:14b"  # Override default
  context_window: 8192  # Override default
```

```python
# In query.py
if "llm_model" in query_settings:
    rag_config.ollama.llm_model = query_settings["llm_model"]
if "context_window" in query_settings:
    rag_config.ollama.context_window = query_settings["context_window"]

# Re-create LLM with new settings
llm = create_llm_model(rag_config.ollama)
Settings.llm = llm
```

---

## Recommended Actions

### Immediate (Required)
1. **Fix collection names** - Update query configs to match ingestion configs
2. **Add collection validation** - Warn if collection doesn't exist
3. **Document collection names** - Create a README section listing all collections

### Short-term (Recommended)
4. **Create config registry** - Central registry of query configs with descriptions
5. **Add collection status command** - `uv run python -m elt_llm_query.runner --status`

### Long-term (Optional)
6. **Weighted retrieval** - Implement weight-based scoring
7. **LLM override** - Allow per-config LLM model selection

---

## Collection Name Reference

| Ingestion Config | Collection Name | Query Configs Using It |
|-----------------|-----------------|------------------------|
| `ingest_dama_dmbok.yaml` | `dama_dmbok` | `dama_only.yaml`, `all_collections.yaml` |
| `ingest_fa_handbook.yaml` | `fa_handbook` | `fa_handbook_only.yaml`, `all_collections.yaml` |
| `ingest_fa_data_architecture.yaml` | `fa_data_architecture` | `fa_data_management.yaml`, `dama_fa_data_arch.yaml` |
| `ingest_fa_ea_leanix.yaml` | `fa_ea_leanix` | `leanix_only.yaml` ⚠️, `leanix_fa_combined.yaml` ⚠️ |
| `ingest_fa_ea_sad.yaml` | `fa_ea_sad` | (none?) |
| `ingest_fa_supplier_assess.yaml` | `supplier_assess` | `vendor_assessment.yaml`, `all_collections.yaml` |

⚠️ = **MISMATCH** - Query config uses wrong name

---

## Files to Update

1. `elt_llm_query/examples/leanix_only.yaml` - Change `leanix` → `fa_ea_leanix`
2. `elt_llm_query/examples/leanix_fa_combined.yaml` - Change `leanix` → `fa_ea_leanix`
3. `elt_llm_query/examples/all_collections.yaml` - Change `leanix` → `fa_ea_leanix`, add `sad` or remove
4. `elt_llm_query/src/elt_llm_query/query.py` - Add collection validation
5. `elt_llm_ingest/README.md` - Document collection names and query usage
