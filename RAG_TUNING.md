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

---

## Tuning Levers

### 1. Context Window (`context_window`)

Controls how many tokens the LLM can receive per call (prompt + retrieved chunks + response).

```yaml
context_window: 16384  # current — safe on M3 18GB
```

**Rule of thumb**: `context_window ≥ (reranker_top_k × chunk_size) + prompt_tokens + response_tokens`

For 15 chunks × 512 tokens + ~1K prompt + ~1K response = ~9.5K → 16K is comfortable.

---

### 2. Chunk Size (`ingest_fa_handbook.yaml → chunking.chunk_size`)

Controls how large each indexed unit is.

```yaml
chunk_size: 512   # current — keeps full FA Handbook rule paragraphs together
chunk_overlap: 64 # 12% overlap prevents split-boundary loss
```

| Chunk size | Effect |
|---|---|
| Too small (128-256) | Definitions split across chunks; context lost |
| **512 (current)** | Full rule paragraphs fit; good embedding specificity |
| Too large (1024+) | Each chunk covers multiple topics; dilutes retrieval signal |

**Do not increase chunk size to improve recall** — increase `reranker_top_k` instead.
Re-ingestion is required if chunk size changes.

---

### 3. Retrieval Breadth (`reranker_retrieve_k`, `reranker_top_k`)

```yaml
reranker_retrieve_k: 30  # candidates fetched (BM25 + vector combined)
reranker_top_k: 15       # chunks passed to LLM after reranking
```

The reranker sees 30 candidates and keeps the best 15 for the LLM.

| Parameter | Too low | Too high |
|---|---|---|
| `reranker_retrieve_k` | Misses relevant chunks ranked > N | Marginal cost; set to 30-40 |
| `reranker_top_k` | Misses specialisation chunks | Dilutes LLM context; wastes context window |

---

### 4. Multi-Query Expansion (`num_queries`)

```yaml
num_queries: 3  # generates 2 additional query variants per entity
```

For entity `Player`, the LLM generates variants such as:
- `"Contract Player registration FA Handbook"`
- `"Academy Player eligibility requirements"`

This directly addresses the **specialisation recall problem** — where the handbook
defines `Contract Player`, `Non-Contract Player`, `Academy Player` as separate chunks
rather than under a single `Player` entry.

| Value | Effect |
|---|---|
| 1 | Disabled — fastest, lowest recall for compound concepts |
| **3 (current)** | 2 extra LLM calls per query — best balance for this use case |
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
| 1.0 | Pure relevance — may return 15 near-identical chunks |
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
reranker_retrieve_k: 30      # candidates before reranking
reranker_top_k:      15      # chunks passed to LLM
num_queries:         3       # query expansion for specialisation recall
chunk_size:          512     # FA Handbook (in ingest_fa_handbook.yaml)
chunk_overlap:       64
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
