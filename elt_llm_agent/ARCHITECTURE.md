# ELT LLM Agent Architecture

**Purpose**: Technical architecture documentation for `elt_llm_agent`

**Last Updated**: March 2026

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ INGESTION (elt_llm_ingest) — UNCHANGED                          │
│ - PDF → Markdown + ChromaDB vector/docstore                     │
│ - XML → JSON sidecar (_model.json) + Markdown                   │
│ - Excel → JSON sidecar (_inventory.json) + Markdown             │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (outputs consumed by agent)
┌─────────────────────────────────────────────────────────────────┐
│ AGENT (elt_llm_agent) — ORCHESTRATION LAYER                     │
│ - Reads JSON sidecars (direct lookup)                           │
│ - Queries vector stores (via elt_llm_query)                     │
│ - Traverses relationships (NetworkX in-memory graph)            │
│ - Decides WHICH tools to use WHEN                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (uses for synthesis)
┌─────────────────────────────────────────────────────────────────┐
│ LLM (Ollama qwen3.5:9b) — FINAL SYNTHESIS                       │
│ - Combines tool outputs into coherent answer                    │
│ - Structured output (8-field schema for catalogs)               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
elt_llm_agent/
├── README.md                        # Quick commands (start here)
├── ARCHITECTURE.md                  # This document
├── AGENTIC_RAG_FOR_CATALOGS.md      # Agentic vs traditional for batch
├── AGENTIC_INGESTION_POSSIBILITIES.md # What agentic ingestion means
├── AGENT_VS_CONSUMER.md             # Comparison with elt_llm_consumer
├── QUALITY_GATE.md                  # Quality gate implementation
├── pyproject.toml                   # Package configuration
└── src/elt_llm_agent/
    ├── __init__.py                  # Exports: ReActAgent, AgentConfig
    ├── agent.py                     # ReActAgent orchestrator
    ├── agent_consolidated_catalog.py # Batch catalog generation
    ├── compare_catalogs.py          # Consumer vs agent comparison
    ├── chat.py                      # Interactive chat CLI
    ├── runner.py                    # Batch query runner
    ├── query.py                     # CLI alias (convenience)
    ├── quality_gate.py              # Quality gate for hybrid RAG
    ├── tools/
    │   ├── __init__.py
    │   ├── rag_query.py             # Wraps elt_llm_query (RAG collections)
    │   ├── json_lookup.py           # Direct JSON sidecar access
    │   └── graph_traversal.py       # NetworkX relationship traversal
    ├── planners/
    │   └── __init__.py              # ReAct planner (keyword-based routing)
    └── memory/
        └── __init__.py              # Conversation + Workspace memory
```

---

## Core Components

### 1. ReActAgent (`agent.py`)

**Purpose**: Orchestrates multi-step reasoning

**Pattern**: ReAct (Reason + Act)

```
Query → Plan → Act (Tool Call) → Observe → Reason → Repeat → Synthesize
```

**Key Methods**:
- `query(query, include_trace)` — Execute single query
- `chat(message)` — Chat with conversation memory
- `reset()` — Clear conversation

---

### 2. Tools (`tools/`)

| Tool | Purpose | Access Pattern |
|------|---------|----------------|
| `rag_query_tool` | Query RAG collections | BM25 + Vector → LLM synthesis |
| `json_lookup_tool` | Direct JSON sidecar access | O(1) dict lookup |
| `graph_traversal_tool` | NetworkX relationship traversal | BFS/DFS on in-memory graph |

---

### 3. Batch Catalog (`agent_consolidated_catalog.py`)

**Purpose**: Generate structured catalog (alternative to `elt_llm_consumer`)

**Agentic Approach**:
1. Load entity aliases (from `entity_aliases.yaml`)
2. BM25 section routing for entity + all aliases (dynamic selection)
3. Keyword scan for entity + all aliases (safety net)
4. `query_collections` with selected sections (proven retrieval)
5. Structured prompt (8-field schema)

**Why Agentic**: Decides WHICH sections to query (3-10) instead of all 44

---

### 4. Quality Gate (`quality_gate.py`)

**Purpose**: Hybrid RAG with automatic agent fallback

```
Query → Classic RAG (2-6s) → Quality Gate (<10ms) → Pass? → Return
                              ↓ Fail
                              ↓
                      ReAct Agent (10-30s)
```

**Quality Checks** (rule-based, <10ms):
- Has citations? (`len(source_nodes) > 0`)
- Not empty? (no "not defined", "LEANIX_ONLY")
- Not too short? (`len(response) > 100` chars)
- Not generic? (no "the provided documents")

---

## Data Flow

### Single Query Flow

```
User Query
    ↓
ReActAgent.query()
    ↓
Planner.next_action() — Decides which tool
    ↓
Tool Execution (RAG/JSON/Graph)
    ↓
Observation added to workspace
    ↓
Planner.next_action() — Ready to synthesize?
    ↓
LLM Synthesis (combines tool outputs)
    ↓
AgentResponse (response + reasoning_trace)
```

---

### Batch Catalog Flow

```
For each entity:
    ↓
1. Get aliases (_get_alias_variants)
    ↓
2. BM25 section routing (entity + aliases)
    ↓
3. Keyword scan (entity + aliases)
    ↓
4. Merge sections (deduplicated)
    ↓
5. query_collections(selected sections, structured prompt)
    ↓
6. Parse response (8 fields by label)
    ↓
7. Write to catalog JSON
```

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **LLM** | Ollama (qwen3.5:9b) | Synthesis, reasoning |
| **Embeddings** | Ollama (nomic-embed-text) | Vector retrieval |
| **Vector Store** | ChromaDB | Semantic search |
| **Docstore** | LlamaIndex JSON | BM25 retrieval |
| **Graph** | NetworkX | Relationship traversal |
| **Agent Framework** | LlamaIndex tools | Tool orchestration |

---

## Performance Characteristics

### Single Query

| Operation | Latency | Notes |
|-----------|---------|-------|
| `json_lookup_tool` | < 100ms | O(1) dict lookup |
| `graph_traversal_tool` | < 500ms | NetworkX BFS on 175 nodes |
| `rag_query_tool` | 2–6s | Hybrid retrieval + LLM |
| Full reasoning loop (3 tools) | 10–30s | 3–5 tool calls typical |

---

### Batch Catalog

| Domain | Entities | Agent Runtime | Consumer Runtime | Speedup |
|--------|----------|--------------|------------------|---------|
| PARTY | 28 | ~10-20 min | ~45-60 min | 3-4x |
| AGREEMENTS | 42 | ~15-30 min | ~60-90 min | 3-4x |
| All domains | 175 | ~60-90 min | ~3-4 hours | 3-4x |

**Why faster**: Agent queries 3-10 relevant sections, consumer queries all 44

---

## Design Principles

1. **No re-ingestion required** — Consumes existing `elt_llm_ingest` outputs
2. **Dynamic section selection** — BM25 routing instead of querying all sections
3. **Alias-aware retrieval** — Queries entity name + all aliases
4. **Structured output** — 8-field schema for catalog generation
5. **Conversation memory** — Context-aware follow-up questions

---

## References

- [README.md](README.md) — Quick commands
- [AGENTIC_RAG_FOR_CATALOGS.md](AGENTIC_RAG_FOR_CATALOGS.md) — Agentic vs traditional for batch
- [AGENTIC_INGESTION_POSSIBILITIES.md](AGENTIC_INGESTION_POSSIBILITIES.md) — What agentic ingestion means
- [AGENT_VS_CONSUMER.md](AGENT_VS_CONSUMER.md) — Detailed comparison with consumer
- [QUALITY_GATE.md](QUALITY_GATE.md) — Quality gate implementation
