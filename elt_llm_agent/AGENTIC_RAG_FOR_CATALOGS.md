# Agentic RAG for Batch Catalog Generation

**Purpose**: Explain how agentic RAG differs from traditional RAG when generating structured catalogs (alternative to `elt_llm_consumer`)

**Audience**: Data architects, engineers evaluating whether to use agent-based vs consumer-based catalog generation

---

## Executive Summary

**Traditional RAG Catalog** (`elt_llm_consumer`):
```
For each entity (175 total):
  1. BM25 section routing (all 44 handbook sections)
  2. Keyword scan (verbatim search)
  3. Hybrid retrieval (BM25 + Vector)
  4. Reranking
  5. LLM synthesis (single call, 8-field schema)
  
Runtime: ~45-60 minutes for PARTY domain (28 entities)
Output: fa_consolidated_catalog_party.json (structured, review-ready)
```

**Agentic RAG Catalog** (`elt_llm_agent`):
```
For each entity (175 total):
  1. Agent plans: "Which tools do I need?"
  2. rag_query_tool (dynamic section selection)
  3. json_lookup_tool (LeanIX context)
  4. Agent critiques: "Is this complete?"
  5. Re-retrieve if needed (self-correction)
  6. Synthesize answer (natural language → structured extraction)
  
Runtime: ~10-20 minutes for PARTY domain (28 entities)
Output: fa_agent_catalog_party.json (structured, agent-extracted)
```

**Key difference**: Agent makes **decisions** per entity (which tools, when to re-retrieve), while consumer follows **fixed pipeline** for all entities.

---

## What is Agentic RAG for Catalogs?

### Traditional RAG (Consumer) — Fixed Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ CONSUMER PIPELINE (Same for every entity)                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Entity: "Club Official"                                     │
│   ↓                                                          │
│ [BM25 Section Routing] ← Always runs                        │
│   ↓                                                          │
│ [Keyword Scan] ← Always runs                                │
│   ↓                                                          │
│ [Hybrid Retrieval] ← Always runs                            │
│   ↓                                                          │
│ [Reranking] ← Always runs                                   │
│   ↓                                                          │
│ [LLM Synthesis] ← Single call, 8-field schema              │
│   ↓                                                          │
│ Output: {formal_definition, domain_context, ...}            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Characteristics**:
- ✅ **Systematic** — Same process for all 175 entities
- ✅ **Predictable** — Known runtime (~60-90s per entity)
- ✅ **Structured** — 8-field schema enforced
- ⚠️ **Rigid** — Cannot adapt per entity
- ⚠️ **No recovery** — If retrieval fails, returns empty

---

### Agentic RAG (Agent) — Dynamic Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ AGENT PIPELINE (Adapts per entity)                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ Entity: "Club Official"                                     │
│   ↓                                                          │
│ [Agent Plans] ← "What do I need for this entity?"          │
│   ↓                                                          │
│ [Tool Decision] ← Decision point                            │
│   ├─ rag_query_tool (if handbook content needed)           │
│   ├─ json_lookup_tool (if LeanIX context needed)           │
│   └─ graph_traversal_tool (if relationships needed)        │
│   ↓                                                          │
│ [Agent Critiques] ← "Is this complete?"                    │
│   ├─ YES → Synthesize                                      │
│   └─ NO → Re-retrieve with new query                       │
│   ↓                                                          │
│ Output: {formal_definition, domain_context, ...}            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Characteristics**:
- ✅ **Adaptive** — Different strategy per entity
- ✅ **Self-correcting** — Re-retrieves if incomplete
- ✅ **Faster** — Skips unnecessary steps (~10-20 min total)
- ⚠️ **Non-deterministic** — May vary per run
- ⚠️ **Less structured** — Natural language → extraction

---

## Key Differences

| Aspect | Consumer (Traditional RAG) | Agent (Agentic RAG) |
|--------|---------------------------|---------------------|
| **Control flow** | Fixed pipeline (same for all) | Dynamic (adapts per entity) |
| **Decision-making** | None (predefined steps) | Agent decides tools, when to re-retrieve |
| **Retrieval** | All 44 sections queried | Only relevant sections (BM25 routing) |
| **Error handling** | Returns empty on failure | Re-retrieves, tries alternative tools |
| **Runtime** | ~60-90s per entity | ~10-30s per entity (3-4x faster) |
| **Output schema** | 8 fields (strict) | 8 fields (extracted from NL) |
| **Best for** | Stakeholder review, Purview import | Quick scans, debugging, exploration |

---

## How Agent Makes Decisions (Per Entity)

### Entity Type 1: Well-Defined in Handbook (e.g., "Club", "Player")

```
Agent reasoning:
1. "Club" is likely well-documented in handbook
2. Plan: rag_query_tool first
3. Execute: rag_query_tool(collection="fa_handbook", query="Club definition governance")
4. Critique: "Response has definition + governance → Complete!"
5. Synthesize output

Tool calls: 1 (rag_query)
Runtime: ~5-10s
```

### Entity Type 2: Referenced But Not Defined (e.g., "Employees", "Mentor")

```
Agent reasoning:
1. "Employees" may not have formal definition
2. Plan: rag_query_tool + json_lookup_tool
3. Execute: rag_query_tool(...) → "Not defined in handbook"
4. Critique: "Definition missing, but governance found"
5. Execute: json_lookup_tool(entity_type="model", entity_name="Employees")
6. Synthesize: Combine handbook governance + LeanIX context

Tool calls: 2 (rag_query + json_lookup)
Runtime: ~10-15s
```

### Entity Type 3: Thin/No Coverage (e.g., "Customer", "Prospect")

```
Agent reasoning:
1. "Customer" — may be business concept, not governance
2. Plan: rag_query_tool first
3. Execute: rag_query_tool(...) → "No relevant content"
4. Critique: "Handbook has minimal content"
5. Execute: json_lookup_tool(...) → Get LeanIX description
6. Synthesize: "Not in handbook, LeanIX description: ..."

Tool calls: 2 (rag_query + json_lookup)
Runtime: ~10-15s
Classified as: LEANIX_ONLY
```

---

## Why Agent is Faster (3-4x Speedup)

### Consumer Approach (Traditional RAG)

```
Per entity:
  - BM25 scan: 44 sections × ~20ms = ~880ms
  - Keyword scan: 44 sections × ~10ms = ~440ms
  - Hybrid retrieval: 10-44 sections × ~30ms = ~300-1300ms
  - Reranking: ~100ms
  - LLM synthesis: ~60-90s
  
Total per entity: ~62-93s
Total for PARTY (28 entities): ~29-43 minutes
```

### Agent Approach (Agentic RAG)

```
Per entity:
  - Agent planning: ~100ms
  - rag_query_tool: Dynamic section selection (BM25 routing)
    - Only queries 3-10 relevant sections (not all 44)
    - Retrieval: ~200-500ms
  - LLM synthesis: ~5-15s (shorter context)
  - Critique + re-retrieve: ~5-10s (only if needed)
  
Total per entity: ~10-30s
Total for PARTY (28 entities): ~5-14 minutes
```

**Speedup factors**:
1. **Dynamic section selection** — Queries 3-10 sections vs 44 sections
2. **Shorter context** — Agent extracts only what's needed
3. **Early termination** — Skips entities with no handbook coverage faster

---

## When to Use Each

### Use Consumer (Traditional RAG) When:

- ✅ **Stakeholder review** — Need structured, review-ready JSON
- ✅ **Purview/Erwin import** — Schema enforcement required
- ✅ **Systematic coverage** — Must process ALL entities
- ✅ **Audit trail** — Checkpointing, review_status fields
- ✅ **Reproducibility** — Same output every run

**Example workflow**:
```bash
# Monthly catalog generation for stakeholder review
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY

# Output: fa_consolidated_catalog_party.json
# Use: Send to Data Architects for review, import to Purview
```

---

### Use Agent (Agentic RAG) When:

- ✅ **Quick domain scan** — Faster than consumer (3-4x)
- ✅ **Debugging LEANIX_ONLY** — Agent may find missed content
- ✅ **Exploratory analysis** — Natural language output
- ✅ **Complex queries** — Multi-hop reasoning needed
- ✅ **Follow-up questions** — Conversation context

**Example workflows**:
```bash
# Quick scan before running consumer
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Debug why entity returned LEANIX_ONLY
uv run python -m elt_llm_agent.chat
# Ask: "What does the handbook say about Customer?"

# Compare outputs
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```

---

## Output Comparison

### Consumer Output (Structured Schema)

```json
{
  "entity_name": "Club Official",
  "source": "BOTH",
  "formal_definition": "any Director of any Club, and/or in respect of any Club...",
  "domain_context": "Club Officials are bound by The Association's Code of Conduct...",
  "governance_rules": "Club Officials are bound by The Association's Code of Conduct...",
  "mapping_confidence": "high",
  "mapping_rationale": "Direct name match",
  "review_status": "PENDING",
  "relationships": []
}
```

### Agent Output (Extracted from Natural Language)

```json
{
  "entity_name": "Club Official",
  "source": "BOTH",
  "formal_definition": "any Director of any Club, and/or in respect of any Club...",
  "domain_context": "Club Officials are bound by The Association's Code of Conduct...",
  "governance_rules": "Club Officials are bound by The Association's Code of Conduct...",
  "handbook_term": null,
  "mapping_confidence": "",
  "mapping_rationale": "",
  "review_status": "PENDING",
  "review_notes": "Agent-based extraction (compare with consumer)",
  "relationships": []
}
```

**Key difference**: Agent extracts from natural language synthesis, consumer has strict 8-field schema from LLM prompt.

---

## Quality Comparison

### Metrics to Compare

| Metric | Consumer | Agent | Winner |
|--------|----------|-------|--------|
| **Definition completeness** | High (prompt-enforced) | Medium (extracted) | Consumer |
| **Governance extraction** | High (systematic) | Medium-High (adaptive) | Comparable |
| **LEANIX_ONLY recovery** | Low (returns empty) | Medium (may find thin content) | Agent |
| **Runtime** | ~60-90s/entity | ~10-30s/entity | Agent (3-4x faster) |
| **Reproducibility** | High (deterministic) | Medium (may vary) | Consumer |
| **Output structure** | Strict 8-field schema | Extracted fields | Consumer |

---

## Recommended Workflow

### Phase 1: Quick Scan with Agent

```bash
# Run agent catalog (fast, 10-20 min)
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Review output
cat .tmp/fa_agent_catalog_party.json | python -m json.tool | head -100

# Identify LEANIX_ONLY entities
python3 -c "
import json
with open('.tmp/fa_agent_catalog_party.json') as f:
    data = json.load(f)
for e in data['entities']:
    if e.get('source') == 'LEANIX_ONLY':
        print(f\"LEANIX_ONLY: {e['entity_name']}\")
"
```

### Phase 2: Debug Thin Coverage

```bash
# Query problematic entities with agent chat
uv run python -m elt_llm_agent.chat

# Ask: "What does the handbook say about Customer?"
# Agent may find content that batch missed
```

### Phase 3: Run Consumer for Final Output

```bash
# Run consumer catalog (systematic, 45-60 min)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY

# Compare outputs
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs

# Review comparison
cat .tmp/comparison_*.json | python -m json.tool
```

### Phase 4: Stakeholder Review

```bash
# Use consumer output for review (structured, schema-enforced)
# fa_consolidated_catalog_party.json

# Send to Data Architects
# Import to Purview/Erwin
```

---

## Summary

| Question | Answer |
|----------|--------|
| **What is agentic RAG for catalogs?** | Dynamic, adaptive pipeline (agent decides tools per entity) |
| **How is it different from consumer?** | Consumer: fixed pipeline; Agent: dynamic, self-correcting |
| **When should I use agent?** | Quick scans, debugging, exploration, complex queries |
| **When should I use consumer?** | Stakeholder review, Purview import, systematic coverage |
| **Is agent better?** | Faster (3-4x), but consumer has better structure |
| **Can I use both?** | ✅ Yes — recommended workflow above |

---

## Commands

```bash
# Agent catalog (fast scan)
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Consumer catalog (systematic)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY

# Compare outputs
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```

---

**Bottom line**: Agentic RAG for catalogs is **faster and adaptive**, while traditional RAG (consumer) is **systematic and structured**. Use both in complementary workflow for best results.
