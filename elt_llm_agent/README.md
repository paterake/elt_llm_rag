# elt-llm-agent

Agentic RAG orchestration layer — multi-step reasoning with tool use.

**Start here**: This module adds an **agentic reasoning layer** on top of your existing RAG infrastructure. It does NOT replace `elt_llm_query` or `elt_llm_ingest` — it uses them as tools.

---

## What is Agentic RAG?

**Traditional RAG** (your current `elt_llm_query`):
```
Query → Retrieve → Rerank → Synthesize → Answer
```
Single-shot retrieval. Good for grounded Q&A.

**Agentic RAG** (this module):
```
Query → Plan → [Tool: RAG] → [Tool: JSON Lookup] → [Tool: Graph Traversal] → Reason → Synthesize → Answer
```
Multi-step reasoning loop. Good for complex, multi-hop queries.

---

## When to Use Agentic RAG

| Use Case | Traditional RAG (`elt_llm_query`) | Agentic RAG (`elt_llm_agent`) |
|----------|-----------------------------------|-------------------------------|
| Simple Q&A | ✅ Best | ⚠️ Overkill |
| Governance lookup | ✅ Best | ⚠️ Slower |
| Multi-hop reasoning | ❌ Cannot | ✅ Best |
| Cross-source synthesis | ⚠️ Manual | ✅ Automatic |
| Relationship queries | ❌ Cannot | ✅ Best |

**Example queries where Agentic RAG excels**:
- *"What data objects flow through the Player Registration interface, and what governance rules apply?"*
- *"Show me all entities connected to 'Club' in the conceptual model, and what the FA Handbook says about each"*
- *"Compare DAMA-DMBOK's data governance guidance with FA Handbook governance structures"*

---

## Installation

```bash
cd elt_llm_rag
uv sync --package elt-llm-agent
```

### Prerequisites

```bash
# Ollama running
ollama serve
ollama pull nomic-embed-text
ollama pull qwen3.5:9b

# Ingested collections (required for tools to work)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
```

---

## Quick Start

### Interactive Chat

```bash
# Start interactive agent chat
uv run python -m elt_llm_agent.chat

# With different model
uv run python -m elt_llm_agent.chat --model qwen3.5:9b

# Quiet mode (no reasoning trace)
uv run python -m elt_llm_agent.chat --quiet
```

**Chat commands**:
- `/reset` — Clear conversation memory
- `/trace` — Show reasoning trace from last query
- `/history` — Show conversation history
- `/exit` — Exit chat

### Batch Query

```bash
# Single query
uv run python -m elt_llm_agent.query \
  -q "What data objects flow through the Player Registration interface?"

# Batch queries from file
uv run python -m elt_llm_agent.query --file queries.json --output results.json

# Verbose mode (show full reasoning trace)
uv run python -m elt_llm_agent.query -q "..." -v
```

---

## Architecture

### Module Structure

```
elt_llm_agent/
├── agent.py              # ReActAgent orchestrator
├── chat.py               # Interactive chat CLI
├── runner.py             # Batch query runner
├── tools/
│   ├── rag_query.py      # Wraps elt_llm_query
│   ├── json_lookup.py    # Direct JSON sidecar access
│   └── graph_traversal.py # Relationship traversal
├── planners/
│   └── __init__.py       # ReAct + Plan-and-Execute planners
└── memory/
    ├── __init__.py       # Conversation + Workspace memory
```

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│ AGENT (elt_llm_agent)                                           │
│                                                                  │
│  1. Receive query: "What data objects flow through Player Reg?" │
│                                                                  │
│  2. Plan:                                                        │
│     - Step 1: Lookup interface in JSON sidecar                 │
│     - Step 2: Traverse graph for connected data objects        │
│     - Step 3: Query FA Handbook for governance                 │
│                                                                  │
│  3. Execute tools:                                              │
│     ┌──────────────────────────────────────────────────────┐   │
│     │ json_lookup_tool()                                    │   │
│     │   → Reads: .tmp/*_model.json (from elt_llm_ingest)   │   │
│     │   → Returns: Interface entity with fact_sheet_id     │   │
│     └──────────────────────────────────────────────────────┘   │
│     ┌──────────────────────────────────────────────────────┐   │
│     │ graph_traversal_tool()                                │   │
│     │   → Reads: .tmp/*_model.json relationships           │   │
│     │   → Returns: Connected data objects                  │   │
│     └──────────────────────────────────────────────────────┘   │
│     ┌──────────────────────────────────────────────────────┐   │
│     │ rag_query_tool()                                      │   │
│     │   → Uses: elt_llm_query (ChromaDB + LLM)             │   │
│     │   → Returns: Governance context from FA Handbook     │   │
│     └──────────────────────────────────────────────────────┘   │
│                                                                  │
│  4. Synthesize: Combine all results into final answer          │
└─────────────────────────────────────────────────────────────────┘
```

### Tools

| Tool | Purpose | Uses |
|------|---------|------|
| `rag_query_tool` | Query RAG collections | `elt_llm_query` |
| `json_lookup_tool` | Direct JSON sidecar lookup | `.tmp/*_model.json`, `*_inventory.json` |
| `graph_traversal_tool` | Relationship traversal | `.tmp/*_model.json` relationships |

**Key point**: All tools consume outputs from `elt_llm_ingest` — no new ingestion required.

---

## Usage Examples

### Example 1: Multi-Hop Relationship Query

**Query**: *"What data objects flow through the Player Registration interface?"*

**Agent reasoning**:
1. Lookup "Player Registration" interface in JSON sidecar
2. Extract `fact_sheet_id`
3. Traverse graph to find connected data objects
4. Synthesize answer

```bash
uv run python -m elt_llm_agent.query \
  -q "What data objects flow through the Player Registration interface?"
```

**Output**:
```
Based on my analysis:

[JSON_LOOKUP]
Found interface: "Player Registration System" (fact_sheet_id: INT-456)

[GRAPH_TRAVERSAL]
Connected data objects (2 hops):
- Player (DO-001)
- Registration (DO-002)
- County FA (DO-003)

[SYNTHESIS]
The Player Registration interface connects to 3 data objects:
1. Player — stores player personal details...
2. Registration — stores registration records...
3. County FA — stores county association data...
```

---

### Example 2: Cross-Source Governance Query

**Query**: *"What governance rules apply to Player data, and how does this map to DAMA-DMBOK guidance?"*

**Agent reasoning**:
1. Lookup "Player" entity in conceptual model (JSON)
2. Query FA Handbook for governance rules (RAG)
3. Query DAMA-DMBOK for data governance guidance (RAG)
4. Synthesize comparison

```bash
uv run python -m elt_llm_agent.query \
  -q "What governance rules apply to Player data, and how does this map to DAMA-DMBOK guidance?" \
  -v
```

---

### Example 3: Programmatic Usage

```python
from elt_llm_agent import ReActAgent, AgentConfig

# Create agent
config = AgentConfig(
    model="qwen3.5:9b",
    max_iterations=10,
    verbose=True,
)
agent = ReActAgent(config)

# Query
response = agent.query(
    "What data objects flow through the Player Registration interface?"
)

# Access results
print(response.response)
print(response.tool_calls)
print(response.reasoning_trace)

# Chat (maintains context)
response = agent.chat("What about Club data?")
print(response.response)

# Reset conversation
agent.reset()
```

---

## Configuration

### AgentConfig

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | str | `"qwen3.5:9b"` | LLM model for reasoning |
| `max_iterations` | int | `10` | Maximum reasoning loops |
| `verbose` | bool | `True` | Show detailed logging |
| `tools` | list | `None` | Custom tools (default: standard RAG tools) |

### Tool Parameters

#### rag_query_tool

| Parameter | Description |
|-----------|-------------|
| `collection` | Collection to query: `"fa_handbook"`, `"fa_leanix_*"`, `"dama_dmbok"`, `"all"` |
| `query` | Natural language query |

#### json_lookup_tool

| Parameter | Description |
|-----------|-------------|
| `entity_type` | `"model"`, `"inventory"`, or specific domain |
| `entity_id` | Lookup by fact_sheet_id |
| `entity_name` | Search by name |
| `filter_field` | Filter by field name |
| `filter_value` | Filter value |

#### graph_traversal_tool

| Parameter | Description |
|-----------|-------------|
| `entity_name` | Starting entity |
| `relationship_type` | Optional filter (e.g., "owns", "flows_to") |
| `max_depth` | Maximum traversal depth (default: 2) |

---

## Integration with Existing Modules

### Uses (No Refactoring Required)

| Module | How Agent Uses It |
|--------|-------------------|
| `elt_llm_ingest` | Consumes JSON sidecars, vector stores |
| `elt_llm_query` | Wraps as `rag_query_tool` |
| `elt_llm_consumer` | Uses JSON output patterns |

### Does NOT Replace

| Module | Why |
|--------|-----|
| `elt_llm_query` | Still best for single-shot RAG queries |
| `elt_llm_consumer` | Still best for batch structured output |
| `elt_llm_api` | Still best for interactive GUI |

**Agent complements existing modules** — it's an orchestration layer, not a replacement.

---

## Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Single tool call | 1–5s | Depends on tool (RAG slower than JSON lookup) |
| Full reasoning loop | 10–30s | 3–5 tool calls typical |
| Complex multi-hop | 30–60s | 5–10 tool calls |

**Optimization tips**:
- Reduce `max_iterations` for faster responses
- Use `--quiet` mode to skip trace output
- For batch jobs, parallelize independent queries

---

## Debugging

### Enable Verbose Logging

```bash
uv run python -m elt_llm_agent.chat --log-level DEBUG
```

### Export Reasoning Trace

```python
agent = ReActAgent()
response = agent.query("...")
print(response.reasoning_trace)
print(agent.export_trace())
```

### Check Tool Outputs

```python
from elt_llm_agent.tools import json_lookup_tool, rag_query_tool

# Test JSON lookup
result = json_lookup_tool(entity_type="model", entity_name="Club")
print(result)

# Test RAG query
result = rag_query_tool(collection="fa_handbook", query="What is a Club?")
print(result)
```

---

## Roadmap

### Phase 1 (Current)
- ✅ ReAct agent with 3 tools
- ✅ Conversation + workspace memory
- ✅ Interactive chat + batch query CLI

### Phase 2 (Planned)
- ⬜ LLM-based synthesis (currently simple concatenation)
- ⬜ GraphRAG integration (Neo4j backend)
- ⬜ Plan-and-execute pattern for batch workflows
- ⬜ Self-correction / retry logic

### Phase 3 (Future)
- ⬜ Multi-agent collaboration (specialist agents per domain)
- ⬜ Human-in-the-loop for uncertain queries
- ⬜ Caching for repeated tool calls

---

## Troubleshooting

### "No JSON sidecars found"

Run ingestion first:
```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
```

### "elt_llm_query not available"

Ensure `elt_llm_query` is installed:
```bash
uv sync --package elt-llm-query
```

### Agent takes too long

Reduce iterations:
```bash
uv run python -m elt_llm_agent.query -q "..." --max-iterations 5
```

---

## References

- [ARCHITECTURE.md](../ARCHITECTURE.md) — Overall system architecture
- [RAG_STRATEGY.md](../RAG_STRATEGY.md) — RAG retrieval strategy
- `elt_llm_query/README.md` — Traditional RAG queries
- `elt_llm_ingest/README.md` — Ingestion pipelines
