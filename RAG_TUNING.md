# RAG Tuning Guide

## The Core Constraint

The FA Handbook (2.2M chars ≈ 550K tokens) can never fit in a single LLM call.
RAG solves this by chunking the document, embedding each chunk, and retrieving
only the most relevant chunks per query (~4–8K tokens) to pass to the LLM.

This means **retrieval quality determines LLM output quality**. Tuning is about
getting the right chunks in front of the LLM, not about making the model bigger.

---

## Hardware Baseline (M3 MacBook, 18GB unified memory)

| Component | Size | Notes |
|---|---|---|
| qwen3.5:9b model weights | 6.6GB | Loaded into unified memory |
| OS + other processes | ~4-5GB | Background baseline |
| Available for KV cache | ~7-8GB | Limits usable context window |

**Practical context window limits:**

| Context window | KV cache | Status |
|---|---|---|
| 8,192 tokens | ~1-2GB | Conservative — safe but underuses model |
| 16,384 tokens | ~3-4GB | **Recommended** — safe, fits 15×512-token chunks |
| 32,768 tokens | ~6-7GB | Tight — risk of pressure under concurrent load |

---

## Configuration File

All retrieval parameters live in [`elt_llm_ingest/config/rag_config.yaml`](elt_llm_ingest/config/rag_config.yaml).

**Current values** (as of 2026-03):

```yaml
context_window:      16384   # M3 18GB safe limit
reranker_retrieve_k: 24      # candidates fetched (BM25 + vector combined)
reranker_top_k:      10      # chunks passed to LLM after reranking
num_queries:         1       # disabled for batch consumer runs (set to 3 for interactive)
chunk_size:          256     # prose chunks (in ingest_fa_handbook.yaml)
chunk_overlap:       32      # 12.5% overlap prevents split-boundary loss
table_chunk_size:    512     # max size for table rows
```

---

## Tuning Levers

### 1. Context Window (`context_window`)

Controls how many tokens the LLM can receive per call (prompt + retrieved chunks + response).

```yaml
context_window: 16384  # current — safe on M3 18GB
```

**Rule of thumb**: `context_window ≥ (reranker_top_k × chunk_size) + prompt_tokens + response_tokens`

For 10 chunks × 256 tokens + ~1K prompt + ~600 tokens response = ~4.2K → 16K is comfortable.

---

### 2. Chunk Size (`ingest_fa_handbook.yaml → chunking.chunk_size`)

Controls how large each indexed unit is.

```yaml
chunk_size: 256   # current — prose chunks
chunk_overlap: 32 # 12.5% overlap prevents split-boundary loss
```

| Chunk size | Effect |
|---|---|
| Too small (128) | Definitions split across chunks; context lost |
| **256 (current)** | Good balance for FA Handbook prose |
| Too large (512+) | Each chunk covers multiple topics; dilutes retrieval signal |

**Table rows**: Handled separately with `table_chunk_size: 512` — keeps definition table rows intact.

**Do not increase chunk size to improve recall** — increase `reranker_retrieve_k` instead.
Re-ingestion is required if chunk size changes.

---

### 3. Retrieval Breadth (`reranker_retrieve_k`, `reranker_top_k`)

```yaml
reranker_retrieve_k: 24  # candidates fetched (BM25 + vector combined)
reranker_top_k:      10  # chunks passed to LLM after reranking
```

The reranker sees 24 candidates and keeps the best 10 for the LLM.

| Parameter | Too low | Too high |
|---|---|---|
| `reranker_retrieve_k` | Misses relevant chunks ranked > N | Marginal cost; set to 24-30 |
| `reranker_top_k` | Misses specialisation chunks | Dilutes LLM context; wastes context window |

---

### 4. Multi-Query Expansion (`num_queries`)

```yaml
num_queries: 1  # disabled for batch consumer runs
```

**For interactive queries**, set to 3 to generate 2 additional query variants per entity.

For entity `Player`, the LLM generates variants such as:
- `"Contract Player registration FA Handbook"`
- `"Academy Player eligibility requirements"`

This directly addresses the **specialisation recall problem** — where the handbook
defines `Contract Player`, `Non-Contract Player`, `Academy Player` as separate chunks
rather than under a single `Player` entry.

| Value | Effect |
|---|---|
| **1 (current)** | Disabled — fastest, best for batch processing |
| 3 | 2 extra LLM calls per query — best balance for interactive use |
| 5 | Diminishing returns; adds latency |

**Note**: Each extra query variant costs 1 LLM call. For a 28-entity domain run,
`num_queries: 3` adds ~56 extra calls vs `num_queries: 1`.

---

### 5. MMR Diversity (`mmr_threshold`)

```yaml
use_mmr: true
mmr_threshold: 0.7  # 70% relevance, 30% diversity
```

Prevents the top-k slots being consumed by near-duplicate adjacent paragraphs.
Effective when a concept appears repeatedly in adjacent handbook sections.

| Value | Effect |
|---|---|
| 1.0 | Pure relevance — may return 10 near-identical chunks |
| **0.7 (current)** | Good balance for FA Handbook |
| 0.0 | Maximum diversity — may include irrelevant chunks |

---

### 6. Lost-in-the-Middle (`use_lost_in_middle`)

```yaml
use_lost_in_middle: true
```

Reorders the final chunk list so the highest-scoring chunks appear at the **start
and end** of the context window. LLM attention is strongest at boundaries; middle
content is attended to less reliably. Leave enabled.

---

## Current Settings Summary

```yaml
# rag_config.yaml (as of 2026-03)
context_window:      16384   # M3 18GB safe limit
reranker_retrieve_k: 24      # candidates before reranking
reranker_top_k:      10      # chunks passed to LLM
num_queries:         1       # disabled for batch runs (set to 3 for interactive)
chunk_size:          256     # prose chunks (in ingest_fa_handbook.yaml)
chunk_overlap:       32
table_chunk_size:    512     # table rows
```

---

## When to Re-ingest

Re-ingestion rebuilds ChromaDB and the BM25 docstore from scratch. Required when:

| Change | Re-ingest needed? |
|---|---|
| `chunk_size` or `chunk_overlap` | **Yes** — chunks in store are a different size |
| `embedding_model` | **Yes** — vector dimensions change |
| Source PDF updated | **Yes** — content changed |
| `context_window`, `reranker_*`, `num_queries` | **No** — retrieval-only, store unchanged |
| `llm_model` | **No** — synthesis only, store unchanged |

```bash
# Re-ingest FA Handbook after chunk size change:
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
```
