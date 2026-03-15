# Agent vs Consumer: When to Use Each

**Purpose**: Clarify differences between `elt_llm_agent` and `elt_llm_consumer`

---

## Executive Summary

| Aspect | `elt_llm_consumer` | `elt_llm_agent` |
|--------|-------------------|-----------------|
| **Purpose** | Structured batch output (JSON) | Interactive Q&A + fast batch |
| **Control flow** | Pre-defined pipeline (7 steps) | Dynamic reasoning (ReAct loop) |
| **Output format** | Structured JSON (8-field schema) | Natural language OR structured JSON |
| **Runtime** | 45–60 min (full PARTY domain) | 10–20 min (3-4x faster) |
| **Best for** | Stakeholder review, Purview import | Quick scans, debugging, exploration |

**Rule of thumb**:
- Use **consumer** for production catalogs (stakeholder review)
- Use **agent** for exploration, debugging, quick scans

---

## Architecture Comparison

### Consumer (Traditional RAG)

```
For each entity (systematic):
  1. BM25 section routing (all 44 sections)
  2. Keyword scan (verbatim search)
  3. Hybrid retrieval (BM25 + Vector)
  4. Reranking
  5. LLM synthesis (single call, 8-field schema)
  
Output: fa_consolidated_catalog.json (structured, review-ready)
```

**Characteristics**:
- ✅ Systematic — Same process for all entities
- ✅ Predictable — Known runtime (~60-90s per entity)
- ✅ Structured — 8-field schema enforced
- ⚠️ Rigid — Cannot adapt per entity

---

### Agent (Agentic RAG)

```
For each entity (adaptive):
  1. Load entity aliases (from entity_aliases.yaml)
  2. BM25 section routing (entity + aliases) — selects 3-10 sections
  3. Keyword scan (entity + aliases) — safety net
  4. query_collections (selected sections only)
  5. LLM synthesis (structured prompt)
  
Output: fa_agent_catalog.json (structured, agent-extracted)
```

**Characteristics**:
- ✅ Adaptive — Dynamic section selection (3-10, not 44)
- ✅ Faster — 3-4x speedup (10-30s per entity)
- ✅ Alias-aware — Queries multiple terms
- ⚠️ Less systematic — May miss edge cases

---

## Key Differences

| Aspect | Consumer | Agent |
|--------|----------|-------|
| **Section selection** | All 44 sections | BM25 selects 3-10 relevant |
| **Alias querying** | Yes (entity_aliases.yaml) | Yes (same) |
| **Keyword injection** | Yes (_extract_around_mention) | Yes (same) |
| **Prompt** | Structured 8-field | Structured 8-field |
| **Retrieval** | query_collections | query_collections |
| **Runtime** | ~60-90s/entity | ~10-30s/entity |
| **Output schema** | Strict 8-field | 8-field (extracted) |

**Same retrieval, different section selection strategy**

---

## Quality Comparison (PARTY Domain Test)

| Metric | Consumer | Agent | Verdict |
|--------|----------|-------|---------|
| **Formal definitions** | 12/28 (43%) | 8/28 (29%) | Consumer better |
| **Governance rules** | 20/28 (71%) | 26/28 (93%) | **Agent better** |
| **Total runtime** | ~45-60 min | ~10-20 min | **Agent 3-4x faster** |

**Analysis**:
- Agent has higher governance coverage (alias querying finds more)
- Consumer has more definitions (Step 3 pre-extraction vs LLM-only)
- Both use same retrieval infrastructure

---

## When to Use Each

### Use Consumer When:

- ✅ **Stakeholder review** — Need structured, review-ready JSON
- ✅ **Purview/Erwin import** — Schema enforcement required
- ✅ **Systematic coverage** — Must process ALL entities
- ✅ **Audit trail** — Checkpointing, review_status fields
- ✅ **Reproducibility** — Same output every run

**Example**:
```bash
# Monthly catalog generation
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY

# Output: fa_consolidated_catalog_party.json
# Use: Send to Data Architects for review
```

---

### Use Agent When:

- ✅ **Quick domain scan** — 3-4x faster than consumer
- ✅ **Debugging LEANIX_ONLY** — Agent may find missed content
- ✅ **Exploratory analysis** — Natural language output
- ✅ **Complex queries** — Multi-hop reasoning needed
- ✅ **Follow-up questions** — Conversation context

**Examples**:
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

## Recommended Workflow

### Phase 1: Quick Scan with Agent

```bash
# Run agent catalog (fast, 10-20 min)
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

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

---

### Phase 2: Debug Thin Coverage

```bash
# Query problematic entities with agent chat
uv run python -m elt_llm_agent.chat

# Ask: "What does the handbook say about Customer?"
# Agent may find content that batch missed
```

---

### Phase 3: Run Consumer for Final Output

```bash
# Run consumer catalog (systematic, 45-60 min)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY

# Compare outputs
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```

---

### Phase 4: Stakeholder Review

```bash
# Use consumer output for review (structured, schema-enforced)
# fa_consolidated_catalog_party.json

# Send to Data Architects
# Import to Purview/Erwin
```

---

## Output Comparison

### Consumer Output

```json
{
  "entity_name": "Club Official",
  "source": "BOTH",
  "formal_definition": "any Director of any Club...",
  "domain_context": "Club Officials are bound by...",
  "governance_rules": "Club Officials are bound by...",
  "mapping_confidence": "high",
  "mapping_rationale": "Direct name match",
  "review_status": "PENDING",
  "relationships": []
}
```

---

### Agent Output

```json
{
  "entity_name": "Club Official",
  "source": "BOTH",
  "formal_definition": "any Director of any Club...",
  "domain_context": "Club Officials are bound by...",
  "governance_rules": "Club Officials are bound by...",
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

## Summary

| Question | Answer |
|----------|--------|
| **Which is better?** | Depends on use case |
| **When to use consumer?** | Production catalogs, stakeholder review |
| **When to use agent?** | Quick scans, debugging, exploration |
| **Can I use both?** | ✅ Yes — recommended workflow above |
| **Is agent production-ready?** | ✅ Yes — for exploration, not final review |

---

## Commands

```bash
# Consumer (production)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY

# Agent (quick scan)
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Compare
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```
