# Agent vs Consumer: When to Use Each

**Purpose**: Clarify the differences between `elt_llm_agent` (agentic RAG) and `elt_llm_consumer` (structured batch output), and when to use each.

---

## Executive Summary

| Aspect | `elt_llm_consumer` | `elt_llm_agent` |
|--------|-------------------|-----------------|
| **Purpose** | Structured batch output (JSON files) | Interactive multi-step reasoning |
| **Control flow** | Pre-defined pipeline (7 steps) | Dynamic reasoning loop (ReAct) |
| **Output format** | Structured JSON (schema-driven) | Natural language + citations |
| **Runtime** | 45–60 min (full catalog) | 10–30s (single query) |
| **Best for** | Stakeholder deliverables | Exploration, Q&A, discovery |
| **LLM calls** | ~175 entities × 1-2 calls = 175–350 calls | 3–5 calls per query |
| **Human intervention** | None (fully automated) | Interactive (chat-style) |

**Rule of thumb**:
- Use **`elt_llm_consumer`** when you need **structured, reviewable output** (catalogs, gap analysis, model builders)
- Use **`elt_llm_agent`** when you need **interactive exploration** or **ad-hoc queries**

---

## 1. Architecture Comparison

### 1.1 Consumer Pipeline (Pre-Defined)

```
┌─────────────────────────────────────────────────────────────────┐
│ elt_llm_consumer — 7-Step Fixed Pipeline                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Step 1: Load Conceptual Model Entities                          │
│   → Read _model.json (175 entities)                             │
│                                                                 │
│ Step 2: Load Inventory Descriptions                             │
│   → Dict lookup by fact_sheet_id                                │
│                                                                 │
│ Step 3: Extract Handbook Defined Terms                          │
│   → Docstore scan with regex                                    │
│                                                                 │
│ Step 4: Match Terms to Entities                                 │
│   → String matching + alias map                                 │
│                                                                 │
│ Step 5: Extract Handbook Context (RAG+LLM)                      │
│   → For each entity: query_collections()                        │
│   → Prompt: handbook_context.yaml                               │
│   → ~60-90s per entity                                          │
│                                                                 │
│ Step 6: Load Relationships                                      │
│   → Read _model.json["relationships"]                           │
│                                                                 │
│ Step 7: Consolidate                                             │
│   → Merge all sources, classify, write JSON                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                  fa_consolidated_catalog.json
                  (structured, review-ready)
```

**Key characteristics**:
- ✅ **Deterministic** — same input → same output
- ✅ **Complete** — processes all 175 entities systematically
- ✅ **Structured** — JSON schema enforced
- ⚠️ **Slow** — 45–60 minutes for full run
- ⚠️ **Inflexible** — fixed pipeline, hard to modify mid-run

---

### 1.2 Agent Pipeline (Dynamic)

```
┌─────────────────────────────────────────────────────────────────┐
│ elt_llm_agent — ReAct Reasoning Loop                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│ Query: "What data objects flow through Player Registration?"    │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Iteration 1: PLAN                                       │    │
│ │ Keywords: "flow through" → graph_traversal              │    │
│ │           "interface" → json_lookup                     │    │
│ └─────────────────────────────────────────────────────────┘    │
│                          ↓                                      │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Iteration 2: ACT                                        │    │
│ │ Tool: json_lookup_tool(entity_type="interface",         │    │
│ │                       entity_name="Player Registration")│    │
│ └─────────────────────────────────────────────────────────┘    │
│                          ↓                                      │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Iteration 3: OBSERVE                                    │    │
│ │ Result: {fact_sheet_id: "INT-456", ...}                 │    │
│ └─────────────────────────────────────────────────────────┘    │
│                          ↓                                      │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Iteration 4: REASON → ACT                               │    │
│ │ Tool: graph_traversal_tool(entity_name="INT-456",       │    │
│ │                            operation="neighbors")       │    │
│ └─────────────────────────────────────────────────────────┘    │
│                          ↓                                      │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Iteration 5: OBSERVE                                    │    │
│ │ Result: {neighbors: ["Player", "Registration", ...]}    │    │
│ └─────────────────────────────────────────────────────────┘    │
│                          ↓                                      │
│ ┌─────────────────────────────────────────────────────────┐    │
│ │ Iteration 6: SYNTHESIZE                                 │    │
│ │ LLM combines all tool outputs → Natural language answer │    │
│ └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
                  Natural language answer
                  (with citations, sources)
```

**Key characteristics**:
- ✅ **Flexible** — adapts to query complexity
- ✅ **Fast** — 10–30s per query
- ✅ **Interactive** — supports follow-up questions
- ⚠️ **Non-deterministic** — reasoning path may vary
- ⚠️ **Unstructured** — prose output (not schema-driven)

---

## 2. Detailed Comparison

### 2.1 Control Flow

| Aspect | Consumer | Agent |
|--------|----------|-------|
| **Flow type** | Linear pipeline | Iterative loop |
| **Decision points** | None (pre-defined) | Dynamic (ReAct planner) |
| **Error handling** | Fail-fast, stop on error | Retry, fallback, continue |
| **Modifiability** | Edit code, re-run | Adjust query, retry |

**Consumer** (code-driven):
```python
# fa_consolidated_catalog.py — fixed sequence
def main():
    conceptual_entities = load_conceptual_model()
    inventory_descriptions = load_inventory()
    handbook_terms = extract_handbook_terms()
    handbook_mappings = match_terms_to_entities()
    handbook_context = query_handbook_per_entity(conceptual_entities)
    relationships = load_relationships()
    catalog = consolidate_all(...)
    write_json(catalog)
```

**Agent** (reasoning-driven):
```python
# agent.py — dynamic loop
def query(self, query: str):
    while iteration < max_iterations:
        action = self.planner.next_action(query, history, workspace)
        if action["tool_name"] is None:
            break  # Ready to synthesize
        result = self._tool_executors[action["tool_name"]](**action["tool_input"])
        history.append({"tool": action["tool_name"], "observation": result})
    return self._synthesize(query, history)
```

---

### 2.2 Output Format

| Aspect | Consumer | Agent |
|--------|----------|-------|
| **Format** | JSON (schema-enforced) | Natural language + citations |
| **Structure** | Fixed fields per entity | Free-form prose |
| **Reviewability** | High (diff-able, versionable) | Medium (prose harder to diff) |
| **Downstream use** | Import to Purview, Erwin, Fabric | Human consumption |
| **Example** | See below | See below |

**Consumer output** (structured):
```json
{
  "fact_sheet_id": "412",
  "entity_name": "Club",
  "domain": "PARTY",
  "source": "BOTH",
  "leanix_description": "A football club affiliated with the FA",
  "formal_definition": "A Club means a football club affiliated with the FA...",
  "domain_context": "Clubs are members of the FA under Section A...",
  "governance_rules": "Section A, Rule 12: Clubs must be members...",
  "mapping_confidence": "high",
  "review_status": "PENDING",
  "relationships": [...]
}
```

**Agent output** (prose):
```
Based on the FA conceptual model and Handbook:

**Conceptual Model Definition**:
A Club is an Organisation entity (PARTY domain) that represents a 
football club affiliated with the FA.

**FA Handbook Definition**:
A Club means a football club affiliated with the FA and subject to 
FA Rules and Regulations.

**Governance Rules**:
- Section A, Rule 12: Clubs must be members of the FA
- Section C, Rule 5: Clubs must register all players

**Relationships**:
Clubs are connected to: Players (owns), Competitions (participates_in), 
County FAs (member_of)

Sources:
- LeanIX: fa_leanix_dat_enterprise_conceptual_model.json
- FA Handbook: Sections A, C
```

---

### 2.3 Runtime Performance

| Metric | Consumer | Agent |
|--------|----------|-------|
| **Total runtime** | 45–60 min (full catalog) | 10–30s (single query) |
| **Entities processed** | 175 (all) | 1–5 (query-dependent) |
| **LLM calls** | 175–350 (1–2 per entity) | 3–5 (per query) |
| **Tool calls** | N/A (direct code) | 3–5 (per query) |
| **Parallelization** | Possible (batch entities) | Sequential (reasoning loop) |

**Consumer breakdown**:
```
Step 1–4: ~2 min (JSON loading, string matching)
Step 5:   ~45–55 min (RAG+LLM per entity, ~60-90s each)
Step 6–7: ~3 min (relationship loading, consolidation)
────────────────────────────────────────────────────────
Total:    ~45–60 min
```

**Agent breakdown**:
```
Planning:     < 1s (keyword matching)
Tool calls:   3–10s (json_lookup, graph_traversal)
RAG query:    2–6s (rag_query_tool)
Synthesis:    5–15s (LLM response)
────────────────────────────────────────────────────────
Total:        10–30s
```

---

### 2.4 Use Cases

#### When to Use Consumer

| Scenario | Why Consumer |
|----------|-------------|
| **Generate stakeholder review catalog** | Structured JSON, complete coverage |
| **Gap analysis (Model vs Handbook)** | Systematic comparison, retrieval-only scoring |
| **Extract candidate entities from Handbook** | Bootstrap model from governance text |
| **Downstream import (Purview, Erwin)** | Schema-enforced output |
| **Audit trail / compliance** | Versionable, diff-able JSON |

**Example workflow**:
```bash
# Monthly catalog generation
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Output: .tmp/fa_consolidated_catalog.json
# Use: Send to Data Architects for review
```

---

#### When to Use Agent

| Scenario | Why Agent |
|----------|-----------|
| **Ad-hoc Q&A** | Fast, interactive |
| **Explore relationships** | Graph traversal on-demand |
| **Follow-up questions** | Conversation memory |
| **Discovery** | "What entities are in PARTY domain?" |
| **Cross-source synthesis** | "Compare Handbook vs DAMA guidance" |

**Example workflow**:
```bash
# Interactive exploration
uv run python -m elt_llm_agent.chat

# You: "What is a Club?"
# Agent: [answers from JSON + Handbook]

# You: "What about its relationships?"
# Agent: [uses conversation context, calls graph_traversal]

# You: "How does this compare to DAMA's definition?"
# Agent: [queries dama_dmbok collection, synthesizes comparison]
```

---

### 2.5 LLM Usage

| Aspect | Consumer | Agent |
|--------|----------|-------|
| **LLM role** | Synthesis per entity (Step 5) | Final synthesis only |
| **Prompt strategy** | Pre-defined prompts (YAML files) | Dynamic synthesis prompt |
| **Prompt files** | `handbook_context.yaml`, `governance_extraction.yaml` | Built-in (code) |
| **Model override** | `--model qwen3.5:9b` | `--model qwen3.5:9b` |

**Consumer prompts** (config-driven):
```yaml
# handbook_context.yaml
prompt: |
  Find the FA Handbook definition or description for the entity '{entity_name}' 
  in the {domain} domain. Respond using this exact format:
  
  FORMAL_DEFINITION:
  DOMAIN_CONTEXT:
  GOVERNANCE:
```

**Agent synthesis** (code-driven):
```python
# agent.py — simplified synthesis
def _synthesize(self, query: str, observations: list):
    parts = []
    for obs in observations:
        parts.append(f"[{obs['tool'].upper()}]\n{obs['observation']}")
    return f"Based on my analysis: \"{query}\"\n\n" + "\n\n".join(parts)
```

*Note: Current agent uses simple concatenation. Production would use LLM-based synthesis with a prompt.*

---

### 2.6 Tool/Source Access

| Source | Consumer Access | Agent Access |
|--------|-----------------|--------------|
| **LeanIX JSON** | Direct `json.load()` | `json_lookup_tool` |
| **FA Handbook** | `query_collections()` (RAG) | `rag_query_tool` |
| **Relationships** | Direct from `_model.json` | `graph_traversal_tool` (NetworkX) |
| **DAMA-DMBOK** | Via RAG profile | `rag_query_tool(collection="dama_dmbok")` |

**Consumer** (direct code):
```python
# fa_consolidated_catalog.py
with open(model_json_path, "r") as f:
    model_data = json.load(f)
    entities = model_data["entities"]
```

**Agent** (tool wrapper):
```python
# tools/json_lookup.py
def json_lookup_tool(entity_type: str, entity_name: str):
    sidecars = _load_json_sidecars()
    result = sidecars[entity_type].get(entity_name)
    return json.dumps(result, indent=2)
```

---

## 3. Side-by-Side: Same Query, Different Approaches

### Query: *"What does the FA Handbook say about Club?"*

#### Consumer Approach

```python
# fa_consolidated_catalog.py — Step 5
for entity in conceptual_entities:  # 175 entities
    if entity["name"] == "Club":
        prompt = _load_prompt("handbook_context.yaml")
        prompt = prompt.format(entity_name="Club", domain="PARTY")
        response = query_collections(
            collections=["fa_handbook"],
            query=prompt,
            num_queries=3,  # Multi-query expansion
        )
        handbook_context["Club"] = parse_response(response)
# After loop completes (~60 min later):
write_json({"Club": handbook_context["Club"], ...})
```

**Characteristics**:
- ✅ Processes all 175 entities (complete coverage)
- ✅ Uses multi-query expansion (`num_queries=3`) for better recall
- ⚠️ Must wait for full loop to complete
- ⚠️ Cannot answer follow-up without re-run

**Output**:
```json
{
  "Club": {
    "formal_definition": "A Club means...",
    "domain_context": "Clubs are members...",
    "governance_rules": "Section A, Rule 12..."
  }
}
```

---

#### Agent Approach

```python
# agent.py — reasoning loop
agent = ReActAgent()
response = agent.query("What does the FA Handbook say about Club?")

# Iteration 1:
#   Reasoning: "Need to find Club in conceptual model"
#   Tool: json_lookup_tool(entity_type="model", entity_name="Club")
#   Observation: {fact_sheet_id: "412", domain: "PARTY", ...}

# Iteration 2:
#   Reasoning: "Now get Handbook context"
#   Tool: rag_query_tool(collection="fa_handbook", 
#                        query="Club definition governance PARTY")
#   Observation: "A Club is defined as... Section A, Rule 12..."

# Iteration 3:
#   Reasoning: "Sufficient information gathered"
#   Synthesize final answer
```

**Characteristics**:
- ✅ Answers in 10–30s
- ✅ Can immediately ask follow-up: "What about its relationships?"
- ⚠️ Only processes Club (not systematic)
- ⚠️ Prose output (not schema-driven)

**Output**:
```
Based on my analysis:

[JSON_LOOKUP]
Found: Club (fact_sheet_id: 412, domain: PARTY)

[RAG_QUERY]
A Club is defined in the FA Handbook as a football club affiliated 
with the FA. Governance rules include:
- Section A, Rule 12: Clubs must be members of the FA
- Section C, Rule 5: Clubs must register players

Sources: fa_handbook_section_A, fa_handbook_section_C
```

---

## 4. Complementary Usage Patterns

### Pattern 1: Consumer First, Agent for Exploration

```bash
# Step 1: Generate structured catalog (monthly)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
# Output: fa_consolidated_catalog.json

# Step 2: Review catalog with stakeholders
# Open JSON, identify gaps/questions

# Step 3: Use agent for ad-hoc exploration
uv run python -m elt_llm_agent.chat
# "Tell me more about Club's governance rules"
# "What entities are connected to Competition?"
```

**Why**: Consumer provides complete, structured baseline. Agent enables interactive exploration of specific entities.

---

### Pattern 2: Agent for Discovery, Consumer for Validation

```bash
# Step 1: Use agent to explore
uv run python -m elt_llm_agent.chat
# "What entities are in the PARTY domain?"
# "Which entities have strong Handbook coverage?"

# Step 2: Run consumer for systematic validation
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis
# Output: fa_gap_analysis.json (MATCHED / MODEL_ONLY / HANDBOOK_ONLY)

# Step 3: Review gap analysis, update conceptual model
```

**Why**: Agent helps identify areas of interest. Consumer provides systematic, auditable analysis.

---

### Pattern 3: Parallel Workflows

| Team | Tool | Purpose |
|------|------|---------|
| **Data Architects** | Agent (chat) | Daily exploration, Q&A |
| **Data Modelling** | Consumer (batch) | Monthly catalog generation |
| **Governance Lead** | Both | Agent for ad-hoc queries, Consumer for compliance reports |

**Why**: Different teams have different needs — interactive vs. structured.

---

## 5. Enhancement Opportunities

### Consumer → Agent Ideas

| Enhancement | Benefit |
|-------------|---------|
| **Dynamic entity prioritization** | Skip low-value entities based on agent reasoning |
| **Adaptive multi-query** | Use `num_queries=1` for well-covered entities, `num_queries=3` for thin coverage |
| **Interactive review** | Chat-based catalog review ("Show me all entities with THIN coverage") |

---

### Agent → Consumer Ideas

| Enhancement | Benefit |
|-------------|---------|
| **Structured output mode** | Agent produces JSON matching consumer schema |
| **Batch mode** | Agent processes entity list systematically |
| **Citation forcing** | Require source IDs in every answer |

---

## 6. Decision Matrix

| Requirement | Consumer | Agent | Neither (use elt_llm_query) |
|-------------|----------|-------|----------------------------|
| **Structured JSON output** | ✅ Yes | ❌ No | ❌ No |
| **Complete entity coverage** | ✅ Yes | ❌ No | ❌ No |
| **Interactive Q&A** | ❌ No | ✅ Yes | ✅ Yes |
| **Fast response (<30s)** | ❌ No (45–60 min) | ✅ Yes | ✅ Yes (2–6s) |
| **Follow-up questions** | ❌ No | ✅ Yes | ⚠️ Manual context |
| **Graph traversal** | ❌ No (direct lookup) | ✅ Yes (NetworkX) | ❌ No |
| **Gap analysis** | ✅ Yes (retrieval-only) | ⚠️ Manual | ❌ No |
| **Downstream import** | ✅ Yes (schema-enforced) | ❌ No | ❌ No |
| **Single collection Q&A** | ❌ Overkill | ⚠️ Overkill | ✅ Yes |

---

## 7. Summary

### Consumer Strengths

✅ **Systematic** — processes all entities  
✅ **Structured** — JSON schema enforced  
✅ **Auditable** — versionable, diff-able  
✅ **Complete** — 100% coverage  
✅ **Downstream-ready** — Purview, Erwin import  

**Best for**: Stakeholder catalogs, gap analysis, compliance reports

---

### Agent Strengths

✅ **Interactive** — chat-style Q&A  
✅ **Fast** — 10–30s per query  
✅ **Flexible** — adapts to query complexity  
✅ **Multi-source** — JSON + RAG + Graph  
✅ **Follow-up questions** — conversation memory  

**Best for**: Exploration, discovery, ad-hoc queries, relationship analysis

---

### When to Use Each

| Goal | Tool |
|------|------|
| "Generate the catalog for stakeholder review" | `elt_llm_consumer` |
| "What entities are in the PARTY domain?" | `elt_llm_agent` |
| "Compare Handbook coverage vs conceptual model" | `elt_llm_consumer` (coverage-validator) |
| "What data objects flow through Player Registration?" | `elt_llm_agent` |
| "Import reviewed catalog to Purview" | `elt_llm_consumer` output |
| "Tell me about Club's governance rules" | Either (consumer for complete, agent for fast) |
| "What does DAMA say about data governance?" | `elt_llm_query` (single collection) |

---

## References

- [elt_llm_agent/ARCHITECTURE.md](elt_llm_agent/ARCHITECTURE.md) — Agent architecture
- [elt_llm_consumer/ARCHITECTURE.md](elt_llm_consumer/ARCHITECTURE.md) — Consumer architecture
- [ARCHITECTURE.md](ARCHITECTURE.md) §7 — Consumer layer overview
- [README.md](README.md) — Quick start commands
