# ELT LLM Agent Architecture

**Workspace**: `elt_llm_agent`
**Purpose**: Agentic RAG orchestration — multi-step reasoning with tool use
**Last Updated**: March 2026

**Start here**: This document explains how the agent works, how it differs from traditional RAG, and how it uses your existing ingestion outputs.

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [1. What is Agentic RAG?](#1-what-is-agentic-rag)
  - [1.1 Traditional RAG vs Agentic RAG](#11-traditional-rag-vs-agentic-rag)
  - [1.2 When to Use Agentic RAG](#12-when-to-use-agentic-rag)
- [2. System Architecture](#2-system-architecture)
  - [2.1 Module Structure](#21-module-structure)
  - [2.2 Relationship to Existing Modules](#22-relationship-to-existing-modules)
- [3. How Agentic RAG Works](#3-how-agentic-rag-works)
  - [3.1 The ReAct Pattern](#31-the-react-pattern)
  - [3.2 Example: Single Entity Query](#32-example-single-entity-query)
  - [3.3 Example: Multi-Hop Relationship Query](#33-example-multi-hop-relationship-query)
- [4. Agent Components](#4-agent-components)
  - [4.1 ReActAgent (Orchestrator)](#41-reactagent-orchestrator)
  - [4.2 ReActPlanner (Decision Logic)](#42-reactplanner-decision-logic)
  - [4.3 Tools (RAG, JSON, Graph)](#43-tools-rag-json-graph)
  - [4.4 Memory (Conversation + Workspace)](#44-memory-conversation--workspace)
- [5. Tool Decision Logic](#5-tool-decision-logic)
  - [5.1 Keyword-Based Tool Selection](#51-keyword-based-tool-selection)
  - [5.2 Iterative Reasoning Loop](#52-iterative-reasoning-loop)
- [6. Usage Patterns](#6-usage-patterns)
  - [6.1 Interactive Chat](#61-interactive-chat)
  - [6.2 Single Query](#62-single-query)
  - [6.3 Batch Catalog Generation](#63-batch-catalog-generation)
  - [6.4 Comparison with Consumer](#64-comparison-with-consumer)
- [7. Data Flow](#7-data-flow)
  - [7.1 What Data Sources Does the Agent Use?](#71-what-data-sources-does-the-agent-use)
  - [7.2 Do I Need to Re-Ingest Data?](#72-do-i-need-to-re-ingest-data)
- [8. Technology Stack](#8-technology-stack)
- [9. Performance Characteristics](#9-performance-characteristics)
- [10. Open-Source Compliance](#10-open-source-compliance)
- [11. FAQ](#11-faq)
- [References](#references)

---

## Executive Summary

**Challenge**: Traditional RAG (`elt_llm_query`) performs single-shot retrieval — one query, one collection, one synthesis. Complex queries requiring multi-hop reasoning across multiple data sources (LeanIX JSON + FA Handbook + relationships) cannot be handled.

**Solution**: Agentic RAG (`elt_llm_agent`) adds an **orchestration layer** that:
1. Receives natural language questions (no collection name needed)
2. Plans multi-step reasoning loops (which tools to call, in what order)
3. Executes tools (JSON lookup, graph traversal, RAG queries)
4. Synthesizes final answer from multiple sources with citations

**Key Design Principle**: **No re-ingestion required** — the agent consumes outputs from `elt_llm_ingest` (JSON sidecars, vector stores) without modification.

**Commands**:
```bash
# Interactive chat
uv run python -m elt_llm_agent.chat

# Single query
uv run python -m elt_llm_agent.query \
  -q "What data objects flow through the Player Registration interface?"

# Batch catalog generation (alternative to elt_llm_consumer)
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Compare agent vs consumer outputs
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```

**New capabilities (March 2026)**:
- ✅ **Batch catalog generation** — `agent_consolidated_catalog.py` as alternative to `elt_llm_consumer`
- ✅ **Comparison tools** — `compare_catalogs.py` for side-by-side quality analysis
- ✅ **Quality gate** — Hybrid RAG with automatic agent fallback for poor results

---

## 1. What is Agentic RAG?

### 1.1 Traditional RAG vs Agentic RAG

| Aspect | Traditional RAG (`elt_llm_query`) | Agentic RAG (`elt_llm_agent`) |
|--------|-----------------------------------|-------------------------------|
| **Input** | Query + collection name | Query only (agent picks collection) |
| **Retrieval** | Single pass (BM25 + Vector) | Multi-step (multiple tool calls) |
| **Data sources** | One collection at a time | Multiple sources (JSON + RAG + Graph) |
| **Reasoning** | None (direct retrieval) | Agent decides which tool, when |
| **Control flow** | Linear: retrieve → rerank → synthesize | Iterative: reason → act → observe → repeat |
| **Best for** | Grounded Q&A within one collection | Complex, multi-hop queries across sources |

**Traditional RAG Flow**:
```
Query → Hybrid Retrieval (BM25 + Vector) → Reranker → Top-K Chunks → LLM → Answer
```

**Agentic RAG Flow**:
```
Query → Plan → [Tool: JSON Lookup] → [Tool: Graph Traversal] → [Tool: RAG Query]
   → Reason → Observe → Repeat → Synthesize → Answer
```

---

### 1.2 When to Use Agentic RAG

| Use Case | Traditional RAG | Agentic RAG |
|----------|-----------------|-------------|
| Simple Q&A (one collection) | ✅ Best | ⚠️ Overkill |
| Governance lookup | ✅ Best | ⚠️ Slower |
| Multi-hop reasoning | ❌ Cannot | ✅ Best |
| Cross-source synthesis | ⚠️ Manual | ✅ Automatic |
| Relationship queries | ❌ Cannot | ✅ Best |
| Entity discovery | ⚠️ Manual | ✅ Automatic |

**Example queries where Agentic RAG excels**:
- *"What data objects flow through the Player Registration interface, and what governance rules apply?"*
- *"Show me all entities connected to 'Club' in the conceptual model, and what the FA Handbook says about each"*
- *"Compare DAMA-DMBOK's data governance guidance with FA Handbook governance structures"*

---

## 2. System Architecture

### 2.1 Module Structure

```
elt_llm_agent/
├── ARCHITECTURE.md                  # This document
├── README.md                        # Quick start and usage
├── AGENT_VS_CONSUMER.md             # Detailed comparison with elt_llm_consumer
├── QUALITY_GATE.md                  # Quality gate implementation
├── pyproject.toml                   # Package configuration
└── src/elt_llm_agent/
    ├── __init__.py                  # Exports: ReActAgent, AgentConfig, Memory
    ├── agent.py                     # ReActAgent orchestrator
    ├── chat.py                      # Interactive chat CLI
    ├── runner.py                    # Batch query runner
    ├── query.py                     # CLI alias (convenience)
    ├── agent_consolidated_catalog.py # Batch catalog generation (consumer alternative)
    ├── compare_catalogs.py          # Consumer vs agent comparison tool
    ├── test_consumer_vs_agent.py    # Test script for comparison
    ├── quality_gate.py              # Quality gate for hybrid RAG
    ├── tools/
    │   ├── __init__.py
    │   ├── rag_query.py             # Wraps elt_llm_query (RAG collections)
    │   ├── json_lookup.py           # Direct JSON sidecar access
    │   └── graph_traversal.py       # NetworkX relationship traversal
    ├── planners/
    │   └── __init__.py              # ReAct + Plan-and-Execute planners
    ├── enhancements/                # Optional enhancements (Phase 1+)
    │   ├── answer_critic.py         # LLM-based answer quality evaluation
    │   └── query_reformulator.py    # Question → affirmative query
    └── memory/
        └── __init__.py              # Conversation + Workspace memory
```

**New components (March 2026)**:
- `agent_consolidated_catalog.py` — Batch catalog generation (alternative to `elt_llm_consumer`)
- `compare_catalogs.py` — Side-by-side comparison of consumer vs agent outputs
- `quality_gate.py` — Hybrid RAG with quality-based agent fallback

---

### 2.2 Relationship to Existing Modules

```
┌─────────────────────────────────────────────────────────────────┐
│ INGESTION (elt_llm_ingest) — UNCHANGED                          │
│ - PDF → Markdown + ChromaDB vector/docstore                     │
│ - XML → JSON sidecar (_model.json) + Markdown                   │
│ - Excel → JSON sidecar (_inventory.json) + Markdown             │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (outputs consumed by agent)
┌─────────────────────────────────────────────────────────────────┐
│ AGENT (elt_llm_agent) — NEW ORCHESTRATION LAYER                 │
│ - Reads JSON sidecars (direct lookup)                           │
│ - Queries vector stores (via elt_llm_query)                     │
│ - Traverses relationships (NetworkX in-memory graph)            │
│ - Decides WHICH tool to use WHEN                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (uses for synthesis)
┌─────────────────────────────────────────────────────────────────┐
│ LLM (Ollama qwen3.5:9b) — FINAL SYNTHESIS                       │
│ - Combines tool outputs into coherent answer                    │
│ - Adds citations and source attribution                         │
└─────────────────────────────────────────────────────────────────┘
```

**Key point**: The agent **does not replace** existing modules — it **orchestrates** them.

| Module | Role | Changed for Agent? |
|--------|------|-------------------|
| `elt_llm_ingest` | Creates JSON sidecars, vector stores | ❌ No |
| `elt_llm_query` | RAG retrieval + synthesis | ❌ No (used as tool) |
| `elt_llm_consumer` | Batch structured output | ❌ No |
| `elt_llm_api` | Interactive GUI | ❌ No |
| `elt_llm_agent` 🆕 | Multi-step orchestration | ✅ New |

---

## 3. How Agentic RAG Works

### 3.1 The ReAct Pattern

The agent implements the **ReAct (Reason + Act)** pattern:

```
1. Reason: Analyze the query and determine what information is needed
2. Act: Call appropriate tools to gather information
3. Observe: Process tool outputs
4. Repeat: Continue until sufficient information gathered
5. Synthesize: Generate final answer
```

**State machine**:
```
┌──────────────┐
│   START      │
└──────┬───────┘
       │
       ↓
┌──────────────┐     No      ┌──────────────┐
│  Sufficient  │────────────→│  Reason:     │
│  information?│             │  What's next?│
└──────┬───────┘             └──────┬───────┘
       │ Yes                        │
       │                            ↓
       │                     ┌──────────────┐
       │                     │  Act:        │
       │                     │  Call tool   │
       │                     └──────┬───────┘
       │                            │
       │                            ↓
       │                     ┌──────────────┐
       │                     │  Observe:    │
       └────────────────────←│  Process     │
                             │  result      │
                             └──────────────┘
```

---

### 3.2 Example: Single Entity Query

**Query**: *"What is a Club in the FA conceptual model, and what does the FA Handbook say about it?"*

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 0: RECEIVE QUERY                                           │
│ Query: "What is a Club in the FA conceptual model..."           │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: PLAN (ReActPlanner.plan)                                │
│ Analyzes keywords: "conceptual model" → json_lookup             │
│                      "FA Handbook" → rag_query                  │
│ Plan: [json_lookup, rag_query]                                  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: REASON → ACT (Iteration 1)                              │
│ Reasoning: "First, find Club in the conceptual model JSON"      │
│ Tool call: json_lookup_tool(                                    │
│   entity_type="model",                                          │
│   entity_name="Club"                                            │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: OBSERVE (Tool Output)                                   │
│ Result from .tmp/fa_leanix_dat_enterprise_conceptual_model.json:│
│ {                                                               │
│   "fact_sheet_id": "412",                                       │
│   "name": "Club",                                               │
│   "domain": "PARTY",                                            │
│   "subtype": "Organisation",                                    │
│   "description": "A football club affiliated with the FA"       │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: REASON → ACT (Iteration 2)                              │
│ Reasoning: "Now get FA Handbook context for Club"               │
│ Tool call: rag_query_tool(                                      │
│   collection="fa_handbook",                                     │
│ query="What is a Club? definition and governance rules"         │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: OBSERVE (RAG + LLM Synthesis)                           │
│ Result from elt_llm_query (ChromaDB + LLM):                     │
│ "A Club is defined in the FA Handbook as...                     │
│  Governance rules: Section A, Rule 12...                        │
│  Sources: [fa_handbook_section_A, fa_handbook_section_C]"       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: SYNTHESIZE (Final Answer)                               │
│ Agent combines both tool outputs:                               │
│                                                                 │
│ "Based on the FA conceptual model and Handbook:                 │
│                                                                 │
│ **Conceptual Model Definition**:                                │
│ A Club is an Organisation entity (PARTY domain) that...         │
│                                                                 │
│ **FA Handbook Definition**:                                     │
│ A Club means a football club affiliated with the FA...          │
│                                                                 │
│ **Governance Rules**:                                           │
│ - Section A, Rule 12: Clubs must be members of the FA           │
│ - Section C, Rule 5: Clubs must register players...             │
│                                                                 │
│ **Sources**:                                                    │
│ - LeanIX: fa_leanix_dat_enterprise_conceptual_model.json        │
│ - FA Handbook: Sections A, C                                    │
└─────────────────────────────────────────────────────────────────┘
```

---

### 3.3 Example: Multi-Hop Relationship Query

**Query**: *"What data objects flow through the Player Registration interface?"*

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: PLAN                                                    │
│ Keywords: "flow through" → graph_traversal                      │
│           "interface", "data objects" → json_lookup             │
│ Plan: [json_lookup, graph_traversal, rag_query]                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: ACT (Iteration 1)                                       │
│ Tool: json_lookup_tool(                                         │
│   entity_type="interface",                                      │
│   entity_name="Player Registration"                             │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: OBSERVE                                                 │
│ Result: {                                                       │
│   "fact_sheet_id": "INT-456",                                   │
│   "name": "Player Registration System",                         │
│   "type": "Interface",                                          │
│   "applications": ["Workday", "SAP"]                            │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: ACT (Iteration 2)                                       │
│ Tool: graph_traversal_tool(                                     │
│   entity_name="Player Registration System",                     │
│   operation="neighbors",                                        │
│   relationship_type="flows_to"                                  │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: OBSERVE                                                 │
│ Result: {                                                       │
│   "neighbors": [                                                │
│     {"entity": "Player", "type": "flows_to"},                   │
│     {"entity": "Registration", "type": "flows_to"},             │
│     {"entity": "County FA", "type": "flows_to"}                 │
│   ]                                                             │
│ }                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: ACT (Iteration 3)                                       │
│ Tool: rag_query_tool(                                           │
│   collection="fa_handbook",                                     │
│   query="governance rules for Player data, Registration data"   │
│ )                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 7: SYNTHESIZE                                              │
│ "The Player Registration interface connects to 3 data objects:  │
│                                                                 │
│ 1. **Player** — Stores personal details...                      │
│    Governance: FA Handbook Section C, Rule 8...                 │
│                                                                 │
│ 2. **Registration** — Stores registration records...            │
│    Governance: FA Handbook Section C, Rule 12...                │
│                                                                 │
│ 3. **County FA** — Stores county association data...            │
│                                                                 │
│ Sources: LeanIX model, FA Handbook Sections C                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 4. Agent Components

### 4.1 ReActAgent (Orchestrator)

**File**: `agent.py`

**Purpose**: Main agent class that orchestrates the reasoning loop.

**Key methods**:
```python
class ReActAgent:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.conversation_memory = ConversationMemory()
        self.workspace_memory = WorkspaceMemory()
        self.planner = ReActPlanner(...)
        self._tool_executors = {
            "rag_query": rag_query_tool,
            "json_lookup": json_lookup_tool,
            "graph_traversal": graph_traversal_tool,
        }

    def query(self, query: str, include_trace: bool = True) -> AgentResponse:
        """Execute a query using ReAct reasoning loop."""

    def chat(self, message: str) -> str:
        """Chat with the agent (maintains conversation context)."""

    def reset(self) -> None:
        """Reset agent memory (start fresh conversation)."""
```

**Configuration** (`AgentConfig`):
```python
@dataclass
class AgentConfig:
    model: str = "qwen3.5:9b"          # LLM for synthesis
    max_iterations: int = 10            # Max reasoning loops
    verbose: bool = True                # Show detailed logging
    tools: list[BaseTool] | None = None # Custom tools (optional)
```

---

### 4.2 ReActPlanner (Decision Logic)

**File**: `planners/__init__.py`

**Purpose**: Implements reasoning logic for tool selection.

**Key methods**:
```python
class ReActPlanner:
    def plan(self, query: str, context: dict) -> dict:
        """Create initial plan based on query keywords."""

    def next_action(self, query: str, history: list, workspace: dict) -> dict:
        """Determine next action based on what's been gathered."""
```

**Decision logic** (simplified):
```python
def next_action(self, query, history, workspace):
    # Check what information we have
    has_entity_data = any("entity" in str(h.get("observation", "")) for h in history)
    has_relationships = any("relationship" in str(h.get("observation", "")) for h in history)
    has_governance = any("governance" in str(h.get("observation", "")) for h in history)

    # Determine what's missing
    if not has_entity_data:
        return {"tool_name": "json_lookup", ...}

    if "relationship" in query.lower() and not has_relationships:
        return {"tool_name": "graph_traversal", ...}

    if not has_governance:
        return {"tool_name": "rag_query", ...}

    # All information gathered — ready to synthesize
    return {"tool_name": None, ...}
```

---

### 4.3 Tools (RAG, JSON, Graph)

#### rag_query_tool

**File**: `tools/rag_query.py`

**Purpose**: Wrap `elt_llm_query` for agent use.

**Signature**:
```python
def rag_query_tool(collection: str, query: str) -> str:
    """Query a RAG collection using hybrid retrieval + LLM synthesis."""
```

**Collections**:
- `"fa_handbook"` — FA Handbook rules and governance
- `"fa_leanix_dat_enterprise_conceptual_model"` — Conceptual data model
- `"fa_leanix_global_inventory"` — Asset inventory
- `"dama_dmbok"` — DAMA-DMBOK data management knowledge
- `"all"` — Query all collections (slower)

---

#### json_lookup_tool

**File**: `tools/json_lookup.py`

**Purpose**: Direct access to LeanIX JSON sidecars (no RAG, no LLM).

**Signature**:
```python
def json_lookup_tool(
    entity_type: str,
    entity_id: str | None = None,
    entity_name: str | None = None,
    filter_field: str | None = None,
    filter_value: str | None = None,
) -> str:
    """Lookup entities in LeanIX JSON sidecars by ID, name, or field filter."""
```

**Entity types**:
- `"model"` — Conceptual model entities (from `_model.json`)
- `"inventory"` — Asset inventory (from `_inventory.json`)
- Specific domain: `"party"`, `"agreements"`, `"dataobject"`, `"interface"`, etc.

**Performance**: O(1) lookup by fact_sheet_id — instant response.

---

#### graph_traversal_tool

**File**: `tools/graph_traversal.py`

**Purpose**: Traverse entity relationships using NetworkX (open-source graph library).

**Signature**:
```python
def graph_traversal_tool(
    entity_name: str,
    relationship_type: str | None = None,
    max_depth: int = 2,
    operation: str = "neighbors",
) -> str:
    """Traverse entity relationships in the LeanIX conceptual model graph."""
```

**Operations**:
| Operation | Description | Example |
|-----------|-------------|---------|
| `neighbors` | Direct 1-hop neighbors | "What entities are connected to Club?" |
| `ego_graph` | Multi-hop ego network | "Show me the full network around Player (2 hops)" |
| `ancestors` | All predecessors | "What owns/controls this entity?" |
| `descendants` | All successors | "What does this entity own/control?" |
| `all_shortest_paths` | Shortest paths to all nodes | "How is Club connected to Competition?" |

**Technology**: NetworkX (BSD license) — pure Python, no external database.

---

### 4.4 Memory (Conversation + Workspace)

**File**: `memory/__init__.py`

#### ConversationMemory

**Purpose**: Short-term conversation history for contextual follow-up.

```python
@dataclass
class ConversationMemory:
    messages: list[dict[str, Any]]  # Conversation turns
    max_messages: int = 50          # FIFO eviction

    def add_message(self, role: str, content: str, **kwargs) -> None: ...
    def get_history(self) -> list[dict[str, Any]]: ...
    def clear(self) -> None: ...
```

**Use case**: Enable follow-up questions like "What about its relationships?" after asking about an entity.

---

#### WorkspaceMemory

**Purpose**: Long-term working memory for intermediate results and reasoning traces.

```python
@dataclass
class WorkspaceMemory:
    workspace: dict[str, Any]  # Key-value store
    traces: list[dict[str, Any]]  # Reasoning traces for debugging

    def set(self, key: str, value: Any) -> None: ...
    def get(self, key: str, default: Any = None) -> Any: ...
    def add_trace(self, step: str, action: str, result: str, ...) -> None: ...
    def export_traces(self) -> str: ...
```

**Use case**: Store extracted entity IDs, intermediate results, audit trail.

---

## 5. Tool Decision Logic

### 5.1 Keyword-Based Tool Selection

The agent uses **simple keyword matching** (not LLM inference) to select tools:

```python
# From ReActPlanner.plan()
query_lower = query.lower()

if any(word in query_lower for word in ["governance", "rule", "policy", "handbook"]):
    required_tools.append("rag_query")

if any(word in query_lower for word in ["entity", "data object", "interface", "application", "inventory"]):
    required_tools.append("json_lookup")

if any(word in query_lower for word in ["relationship", "connected", "flow", "traverse"]):
    required_tools.append("graph_traversal")

# Default to all tools if unclear
if not required_tools:
    required_tools = ["rag_query", "json_lookup", "graph_traversal"]
```

**Why rule-based, not LLM-based?**
- ✅ Deterministic (same query → same plan)
- ✅ Fast (no LLM call for planning)
- ✅ Debuggable (clear rules)
- ✅ No prompt injection risk

---

### 5.2 Iterative Reasoning Loop

The agent loops until it has sufficient information:

```python
# From ReActAgent.query()
iteration = 0
observations = []

while iteration < self.config.max_iterations:
    iteration += 1

    # Determine next action
    action = self.planner.next_action(query, observations, self.workspace_memory.workspace)

    # Check if ready to synthesize
    if action["tool_name"] is None:
        break  # Sufficient information gathered

    # Execute tool call
    tool_name = action["tool_name"]
    tool_params = action["tool_input"]
    result = self._tool_executors[tool_name](**tool_params)

    observations.append({"tool": tool_name, "observation": result[:500]})
    self.workspace_memory.set(f"last_{tool_name}_result", result)

# Synthesize final answer
response = self._synthesize(query, observations)
```

**Termination conditions**:
1. All required information gathered (detected by `next_action()` returning `tool_name=None`)
2. Max iterations reached (`max_iterations=10` default)

---

## 6. Usage Patterns

### 6.1 Interactive Chat

**Use case**: Exploratory Q&A with conversation memory

**Command**:
```bash
uv run python -m elt_llm_agent.chat
```

**Example session**:
```
You: What does the FA Handbook say about Club Official?
Agent: [Retrieves from fa_handbook, synthesizes answer]

You: What about its relationships?
Agent: [Uses conversation context, calls graph_traversal]

You: How does this compare to DAMA's guidance?
Agent: [Queries dama_dmbok collection, synthesizes comparison]
```

**Commands**:
- `/reset` — Clear conversation
- `/trace` — Show reasoning trace
- `/exit` — Exit

---

### 6.2 Single Query

**Use case**: One-off queries without chat session

**Command**:
```bash
uv run python -m elt_llm_agent.query \
  -q "What does the FA Handbook say about Club Official?"
```

**Options**:
- `-q, --query` — Query string (required)
- `-v, --verbose` — Show reasoning trace
- `--model` — Override LLM model (default: qwen3.5:9b)
- `--max-iterations` — Max tool calls (default: 5)

---

### 6.3 Batch Catalog Generation

**Use case**: Generate structured catalog for entire domain (alternative to `elt_llm_consumer`)

**Command**:
```bash
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY
```

**Options**:
- `--domain` — Filter to single domain (e.g. PARTY, AGREEMENTS)
- `--entity` — Filter to specific entities (comma-separated)
- `--output-dir` — Output directory (default: .tmp)
- `--model-json` — Path to LeanIX model JSON
- `--inventory-json` — Path to LeanIX inventory JSON

**Output**: `.tmp/fa_agent_catalog_{domain}.json`

**Comparison with Consumer**:
| Aspect | Agent Catalog | Consumer Catalog |
|--------|--------------|------------------|
| **Approach** | Agentic RAG (multi-step reasoning) | Traditional RAG (systematic) |
| **Runtime** | ~10-20 min per domain | ~45-60 min per domain |
| **Output format** | Structured JSON (agent-extracted fields) | Structured JSON (8-field schema) |
| **Best for** | Exploration, debugging thin coverage | Stakeholder review, Purview import |
| **Quality** | Good for well-defined entities | Better for systematic coverage |

**When to use**:
- ✅ Quick domain scan (faster than consumer)
- ✅ Debugging LEANIX_ONLY entities (agent may find missed content)
- ✅ Exploratory analysis (natural language output)
- ❌ Stakeholder review (use consumer for structured output)

---

### 6.4 Comparison with Consumer

**Use case**: Compare agent vs consumer output quality

**Command**:
```bash
# First run both catalogs
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Then compare
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```

**Output**: Side-by-side comparison showing:
- Entities where both found good content
- Entities where consumer found content but agent didn't
- Entities where agent found content but consumer didn't (LEANIX_ONLY recovery)
- Entities where both returned empty

**Output files**: `.tmp/comparison_*.json` (detailed per-entity comparison)

---

## 7. Data Flow

### 7.1 What Data Sources Does the Agent Use?

| Data Source | Ingested By | Agent Access |
|-------------|-------------|--------------|
| **FA Handbook PDF** | `elt_llm_ingest` → ChromaDB | `rag_query_tool(collection="fa_handbook")` |
| **LeanIX Conceptual Model XML** | `elt_llm_ingest` → `_model.json` | `json_lookup_tool(entity_type="model")` |
| **LeanIX Asset Inventory Excel** | `elt_llm_ingest` → `_inventory.json` | `json_lookup_tool(entity_type="inventory")` |
| **DAMA-DMBOK PDF** | `elt_llm_ingest` → ChromaDB | `rag_query_tool(collection="dama_dmbok")` |
| **Relationships** | Extracted from XML → `_model.json["relationships"]` | `graph_traversal_tool()` |

**All data sources are outputs from `elt_llm_ingest`** — the agent does not create new data.

---

### 7.2 Do I Need to Re-Ingest Data?

**Short answer**: ❌ **No** — your current ingestion outputs are sufficient.

| Data Source | Re-Ingestion Needed? | Reason |
|-------------|----------------------|--------|
| **LeanIX Conceptual Model** | ❌ No | Relationships already extracted to JSON |
| **LeanIX Asset Inventory** | ❌ No | JSON sidecars already created |
| **FA Handbook** | ❌ No | Vector store + docstore already populated |
| **DAMA-DMBOK** | ❌ No | Already ingested |

**When would re-ingestion be needed?**

| Enhancement | Requires Re-Ingestion? | Why |
|-------------|------------------------|-----|
| **Basic agentic RAG** | ❌ No | Uses existing JSON + vector stores |
| **GraphRAG with NetworkX** | ❌ No | Relationships already in JSON |
| **Metadata enrichment** | ✅ Yes (FA Handbook only) | Need to extract section numbers, rule types during ingestion |
| **Parent-child chunking** | ✅ Yes (FA Handbook only) | Different chunking strategy |
| **Explicit relationship triples** | ⚠️ Optional | Could extract from Handbook, but not required |

---

## 8. Technology Stack

| Component | Technology | License | Purpose |
|-----------|------------|---------|---------|
| **Agent framework** | LlamaIndex | MIT | ReAct agent, tool wrappers |
| **Graph library** | NetworkX | BSD | In-memory relationship traversal |
| **LLM** | Ollama (qwen3.5:9b) | Proprietary (local) | Final synthesis |
| **Embeddings** | Ollama (nomic-embed-text) | Apache 2.0 | RAG retrieval |
| **Vector store** | ChromaDB | Apache 2.0 | Semantic search (via `elt_llm_query`) |
| **JSON storage** | File system (`.tmp/`) | N/A | Structured data lookup |

**Open-source compliance**: All components are open-source (BSD, MIT, Apache 2.0) except the local LLM (Ollama), which runs entirely on-premises.

See [OPEN_SOURCE_GRAPH_OPTIONS.md](OPEN_SOURCE_GRAPH_OPTIONS.md) for graph technology choices.

---

## 9. Performance Characteristics

### Single Query Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| `json_lookup_tool` | < 100ms | O(1) dict lookup |
| `graph_traversal_tool` | < 500ms | NetworkX BFS on 175 nodes |
| `rag_query_tool` | 2–6s | Hybrid retrieval + LLM synthesis |
| Full reasoning loop (3 tools) | 10–30s | 3–5 tool calls typical |
| Complex multi-hop (5+ tools) | 30–60s | 5–10 tool calls |

---

### Batch Catalog Generation Performance

| Domain | Entities | Agent Runtime | Consumer Runtime | Speedup |
|--------|----------|--------------|------------------|---------|
| PARTY | 28 | ~10-20 min | ~45-60 min | 3-4x faster |
| AGREEMENTS | 42 | ~15-30 min | ~60-90 min | 3-4x faster |
| All domains | 175 | ~60-90 min | ~3-4 hours | 3-4x faster |

**Why agent is faster for batch**:
- Agent queries only relevant sections (BM25 routing)
- Consumer queries all 44 handbook sections per entity
- Agent skips entities with no handbook coverage (faster failure)

**When consumer is better**:
- Systematic coverage (processes ALL entities)
- Structured 8-field schema (review-ready)
- Checkpointing (resume from interruption)

---

**Optimization tips**:
- Reduce `max_iterations` for faster responses
- Use `--quiet` mode to skip trace output
- For batch jobs, parallelize independent queries
- Use agent for quick scans, consumer for final review

---

## 10. Open-Source Compliance

All dependencies are open-source:

| Dependency | License | Commercial Use |
|------------|---------|----------------|
| LlamaIndex | MIT | ✅ Yes |
| NetworkX | BSD | ✅ Yes |
| ChromaDB | Apache 2.0 | ✅ Yes |
| Ollama | Proprietary (local) | ✅ Yes (self-hosted) |

**No proprietary graph databases required** — NetworkX (pure Python) handles your scale (175 entities) with 570x headroom.

See [OPEN_SOURCE_GRAPH_OPTIONS.md](OPEN_SOURCE_GRAPH_OPTIONS.md) for detailed comparison.

---

## 11. FAQ

### Q: Does the agent replace `elt_llm_query`?

**A**: No — the agent **uses** `elt_llm_query` as a tool (`rag_query_tool`). Use `elt_llm_query` directly for simple single-collection queries; use the agent for multi-hop, multi-source queries.

---

### Q: Do I need to re-ingest my data for agentic RAG?

**A**: ❌ No — the agent consumes existing outputs from `elt_llm_ingest` (JSON sidecars, vector stores). Re-ingestion is only needed if you want to add new metadata fields or change chunking strategies.

---

### Q: How does the agent decide which tools to call?

**A**: **Keyword matching** (rule-based), not LLM inference. The `ReActPlanner` analyzes query keywords:
- "governance", "rule" → `rag_query`
- "entity", "data object" → `json_lookup`
- "relationship", "connected" → `graph_traversal`

This is deterministic and debuggable.

---

### Q: Can the agent handle follow-up questions?

**A**: Yes — `ConversationMemory` maintains context. After asking "What is a Club?", you can ask "What about its relationships?" and the agent will understand the reference.

---

### Q: What graph database does the agent use?

**A**: **None** — it uses NetworkX (pure Python, BSD license) to build an in-memory graph from JSON sidecars. No external database server required. This works for your scale (175 entities) with 570x headroom.

---

### Q: Can I add custom tools?

**A**: Yes — pass custom tools via `AgentConfig`:
```python
from elt_llm_agent import ReActAgent, AgentConfig
from llama_index.core.tools import FunctionTool

def my_custom_tool(param: str) -> str:
    """My custom tool."""
    return f"Result: {param}"

config = AgentConfig(
    tools=[
        create_rag_query_tool(),
        create_json_lookup_tool(),
        create_graph_traversal_tool(),
        FunctionTool.from_defaults(fn=my_custom_tool),
    ]
)
agent = ReActAgent(config)
```

---

### Q: How do I debug agent reasoning?

**A**: Enable verbose mode and export traces:
```bash
# Verbose mode
uv run python -m elt_llm_agent.chat --log-level DEBUG

# Export trace programmatically
agent = ReActAgent()
response = agent.query("...")
print(response.reasoning_trace)
print(agent.export_trace())
```

---

## References

- [README.md](README.md) — Quick start and usage
- [OPEN_SOURCE_GRAPH_OPTIONS.md](OPEN_SOURCE_GRAPH_OPTIONS.md) — Graph technology choices
- [ARCHITECTURE.md](../ARCHITECTURE.md) — Overall system architecture
- [RAG_STRATEGY.md](../RAG_STRATEGY.md) — RAG retrieval strategy
- `elt_llm_query/README.md` — Traditional RAG queries
- `elt_llm_ingest/README.md` — Ingestion pipelines
