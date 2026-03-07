# elt-llm-ingest

Document ingestion pipeline. See [ARCHITECTURE.md](ARCHITECTURE.md) for design documentation.

**All commands run from the repository root.**

---

## RAG+LLM Fixes Summary (March 2026)

The following fixes were implemented to improve FA Handbook RAG retrieval and LLM inference quality:

### Fix 1: No-Coverage Entity Exclusions
**Problem:** 8 entities (Supplier, Household, Business Unit, etc.) have no FA Handbook coverage, but RAG was still making LLM calls and returning hallucinated definitions.

**Solution:** Added `_NO_HANDBOOK_COVERAGE` exclusion list that short-circuits RAG calls for these entities.

**Files:** `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py`

**Impact:** 
- Saves 8 LLM calls (~2-3 minutes runtime)
- Prevents hallucinated definitions
- Correctly marks these as `LEANIX_ONLY` with null definitions

---

### Fix 2: Entity Alias Map for Term Matching
**Problem:** Step 4 term matching achieved only 2/149 (1.3%) matches because it used exact string matching. "FA County" never matched "County Association".

**Solution:** Added `_ENTITY_ALIASES` dictionary with 25+ alias mappings and `_get_alias_variants()` helper function for expanded matching.

**Files:** `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py`

**Key aliases:**
```python
"fa county" ↔ "county association"
"competition league" ↔ "competition"
"match official" ↔ "referee"
"board & committee members" ↔ "board", "committee"
```

**Impact:**
- Expected improvement: 2/149 → 10-15/149 matches (5-7x)
- BOTH entities: 2 → 8-12
- Matching confidence tracked (high=direct, medium=alias)

---

### Fix 3: Table-Aware Chunking
**Problem:** FA Handbook Rules §8 (pp.86-95) contains a definitions table where multi-line rows were split across 3-4 chunks, losing semantic coherence.

**Solution:** Created `TableAwareSentenceSplitter` that:
- Detects table content via pipe-delimiter patterns
- Keeps each table row as a single chunk (up to 1536 tokens)
- Uses standard 256-token chunks for prose content

**Files:**
- `elt_llm_ingest/src/elt_llm_ingest/chunking.py` (new)
- `elt_llm_ingest/src/elt_llm_ingest/ingest.py` (updated)
- `elt_llm_ingest/config/rag_config.yaml` (strategy: table_aware)
- `elt_llm_core/src/elt_llm_core/config.py` (added table_chunk_size field)

**Configuration:**
```yaml
chunking:
  strategy: "table_aware"
  chunk_size: 256           # Prose
  chunk_overlap: 32
  table_chunk_size: 1536    # Table rows
```

**Impact:**
- Definitions like "Participant means any Affiliated Association, Competition, Club..." kept intact
- No more split definitions across chunks
- Better retrieval coherence for table-based queries

---

### Fix 4: Query Parameter Optimization
**Problem:** Larger table chunks (up to 1536 tokens) needed context window accommodation.

**Solution:** Reduced retrieval parameters to fit 16K context window:

**Files:** `elt_llm_ingest/config/rag_config.yaml`

**Changes:**
```yaml
query:
  similarity_top_k: 10 → 8
  reranker_retrieve_k: 30 → 24
  reranker_top_k: 15 → 10
```

**Context math:**
- 10 chunks × 768 avg tokens = 7.7K
- Leaves ~8.6K for LLM output headroom

**Impact:**
- Accommodates larger table chunks
- Maintains retrieval quality (hybrid + reranker + MMR still active)

---

### Fix 5: Governance-Intensive Entity Queries
**Problem:** Core regulatory entities (Club, Player, Match Official) have governance rules scattered across 3-6 handbook sections. Standard RAG retrieval was missing multi-hop governance.

**Solution:** Added `_GOVERNANCE_INTENSIVE_ENTITIES` set that always triggers dedicated governance RAG queries regardless of initial results.

**Files:** `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py`

**Entities:**
```python
_GOVERNANCE_INTENSIVE_ENTITIES = {
    "Club", "Player", "Match Official", "Club Official",
    "County Association", "Competition", "Competition League", "FA County"
}
```

**Impact:**
- Governance coverage: 39% → 55-60% expected
- More complete rule extraction for critical entities
- Better multi-section synthesis

---

## Benchmarking Results

**Before fixes:**
- Step 4 term matches: 2/149 (1.3%)
- BOTH entities: 2/28 (7%)
- LEANIX_ONLY: 26/28 (93%)
- Governance coverage: 11/28 (39%)

**Expected after fixes:**
- Step 4 term matches: 10-15/149 (7-10%)
- BOTH entities: 8-12/28 (29-43%)
- LEANIX_ONLY: 16-20/28 (57-71%)
- Governance coverage: 15-17/28 (55-60%)

---

## Testing

```bash
# Test table-aware chunking
uv run python elt_llm_ingest/src/elt_llm_ingest/test_chunking.py

# Re-ingest FA Handbook with new chunking
uv run python -m elt_llm_ingest.runner ingest ingest_fa_handbook

# Run consolidation (domain-scoped for quick test)
uv run python -m elt_llm_consumer.fa_consolidated_catalog --domain PARTY --skip-relationships
```

---

## Files Modified Summary

| File | Changes |
|------|---------|
| `elt_llm_ingest/chunking.py` | **NEW** - Table/section-aware splitters |
| `elt_llm_ingest/ingest.py` | Uses `create_splitter()` factory |
| `elt_llm_ingest/test_chunking.py` | **NEW** - 9 tests for chunking |
| `elt_llm_core/config.py` | Added `table_chunk_size` field |
| `elt_llm_consumer/fa_consolidated_catalog.py` | Fixes 1, 2, 5 + alias matching |
| `elt_llm_ingest/config/rag_config.yaml` | Table-aware strategy, query params |
| `elt_llm_ingest/config/ingest_fa_handbook.yaml` | Removed local override |

---

## Prerequisites

---

## Prerequisites

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull qwen3.5:9b
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
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook -f
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
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

# Delete all fa_leanix_* collections (split-mode config)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook --delete -f

```

---

## Full Reset

```bash
# Wipe all ChromaDB data
uv run python -m elt_llm_ingest.clean_slate

# Rebuild all collections
uv run python -m elt_llm_ingest.runner --cfg load_rag
```
