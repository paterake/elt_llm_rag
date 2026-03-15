# elt-llm-agentic

**Purpose**: Agentic RAG catalog generation — LLM-driven iterative retrieval for comparison against `elt_llm_consumer`

**All commands run from `elt_llm_agentic/` subfolder.**

---

## Prerequisites

```bash
ollama serve
ollama pull qwen3.5:9b
ollama pull nomic-embed-text
```

FA Handbook and LeanIX collections must be ingested first — see [elt_llm_ingest/README.md](../elt_llm_ingest/README.md).

---

## Interactive Chat

```bash
# Default: FA Handbook only
uv run --package elt-llm-agentic elt-llm-agentic-chat

# Broader profile (LeanIX + Handbook)
uv run --package elt-llm-agentic elt-llm-agentic-chat --profile fa_enterprise_architecture
```

Commands in chat: `/reset`, `/history`, `/graph <entity> [operation]`, `/exit`

---

## Graph Traversal

```bash
# From Python
from elt_llm_agentic.graph_traversal import graph_traversal

graph_traversal("Club", operation="neighbors")
graph_traversal("Player", operation="ego_graph", max_depth=2)
graph_traversal("Club", operation="ancestors")
```

Or from the chat session: `/graph Club neighbors`

---

## Generate Agentic Catalog

```bash
# Full PARTY domain
uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY

# Single entity
uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY --entity "Club Official"

# With per-iteration trace (shows LLM reasoning at each step)
uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY --verbose

# Increase max iterations per entity (default: 5)
uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY --max-iterations 7
```

**Output**: `.tmp/fa_agentic_catalog_party.json`

---

## Compare with Consumer

```bash
# Run consumer (naive pipeline)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY --skip-relationships

# Run agentic
uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY

# Outputs side-by-side:
#   .tmp/fa_consolidated_catalog_party.json   ← consumer
#   .tmp/fa_agentic_catalog_party.json         ← agentic
```

---

## How it differs from elt_llm_consumer

| | Consumer (naive) | Agentic |
|--|-----------------|---------|
| Step 5 retrieval | Fixed: BM25 route → single query | Iterative: LLM decides next query from what's been found |
| Iteration count | 1 per entity | 1–5 per entity (LLM-controlled) |
| Decision logic | Deterministic pipeline | LLM reads observations and picks RETRIEVE / KEYWORD / DONE |
| `agentic_trace` field | No | Yes — full per-iteration log |

Steps 1–4 and 6–7 are identical to `elt_llm_consumer`.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | AgenticRetriever design, ReAct loop, comparison with consumer |
