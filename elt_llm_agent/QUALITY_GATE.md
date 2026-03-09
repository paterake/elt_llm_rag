# Quality Gate for Hybrid Agentic RAG

**Purpose**: Implement fast, rule-based quality checks to decide whether to use classic RAG (fast path) or activate the agent (slow path).

**Design Principle**: *"Don't pay for loops unless your task routinely fails in one pass."* — Towards Data Science

---

## Architecture

### Hybrid Flow

```
USER QUERY
    ↓
┌─────────────────────────────────────────────────────────────┐
│ TIER 1: CLASSIC RAG (Fast Path)                             │
│ query_collections(["fa_handbook"], query)                   │
│ Latency: 2-6s                                               │
└─────────────────────────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────────────────────────┐
│ QUALITY GATE (Rule-Based, <10ms)                            │
│ ✓ Has citations?                                            │
│ ✓ Not "LEANIX_ONLY" or empty?                               │
│ ✓ Not too short (>100 chars)?                               │
│ ✓ Not generic/boilerplate?                                  │
└─────────────────────────────────────────────────────────────┘
    ↓
    ├──────────────┬──────────────┐
    │ PASS (80%)   │ FAIL (20%)   │
    ↓              ↓              │
┌────────┐   ┌───────────────────┴───────────────────┐
│RETURN  │   │ TIER 2: AGENTIC RAG (Slow Path)       │
│RESULT  │   │ ReActAgent.query()                    │
│(2-6s)  │   │ Tools: RAG → JSON → Graph             │
└────────┘   │ Latency: 10-30s                       │
             └───────────────────────────────────────┘
```

---

## Quality Checks

### 1. Citation Check

**Purpose**: Ensure answer has source attribution

**Check**: `len(result.source_nodes) > 0`

**Rationale**: Answers without citations may be hallucinated or generic

---

### 2. Empty Content Check

**Purpose**: Detect hedged or empty responses

**Check**: Response contains phrases like:
- "not defined"
- "not documented"
- "not found"
- "no information"
- "unable to"
- "outside governance scope"
- "leanix_only"

**Rationale**: These phrases indicate retrieval failure or missing content

---

### 3. Response Length Check

**Purpose**: Filter out too-short responses

**Check**: `len(result.response) < 100`

**Rationale**: Substantive answers typically exceed 100 characters

---

### 4. Generic Response Check

**Purpose**: Detect boilerplate responses

**Check**: Response contains phrases like:
- "the provided documents"
- "the handbook does not"
- "no entities found"
- "based on the provided context"

**Rationale**: Generic phrases suggest template responses, not specific answers

---

### 5. Confidence Score (Informational)

**Purpose**: Estimate retrieval quality

**Calculation**: Average cosine similarity of source nodes, normalized to 0-1

**Typical range**: 0.3-0.9

**Use**: Logging/monitoring, not gate decision

---

## Usage

### Basic Usage

```python
from elt_llm_agent import query_with_quality_gate

# Query with automatic quality gate
result = query_with_quality_gate(
    query="What does the FA Handbook say about Club Official?"
)

# Check which path was used
if result["source"] == "classic_rag":
    print(f"Fast answer (2-6s): {result['result'].response}")
    print(f"Quality: {result['quality_check'].passed}")
else:
    print(f"Agent answer (10-30s): {result['result'].response}")
```

### Batch Queries

```python
from elt_llm_agent import batch_query_with_quality_gate

queries = [
    "What is a Club?",
    "What are governance rules for Match Officials?",
    "Tell me about Club Official",
    "What about Board & Committee Members?",
]

results = batch_query_with_quality_gate(queries)

# Summary
classic_count = sum(1 for r in results if r["source"] == "classic_rag")
agent_count = len(results) - classic_count

print(f"Classic RAG: {classic_count} ({classic_count/len(results)*100:.0f}%)")
print(f"Agentic RAG: {agent_count} ({agent_count/len(results)*100:.0f}%)")
```

### Manual Quality Checks

```python
from elt_llm_agent.quality_gate import run_quality_checks
from elt_llm_query.query import query_collections

# Run classic RAG
result = query_collections(...)

# Check quality
qc = run_quality_checks(result)

print(f"Passed: {qc.passed}")
print(f"Citations: {qc.has_citations}")
print(f"Empty: {qc.is_empty}")
print(f"Too short: {qc.is_too_short}")
print(f"Generic: {qc.is_generic}")
print(f"Confidence: {qc.confidence_score:.2f}")
print(f"Reasons: {', '.join(qc.reasons)}")
```

---

## Performance

### Latency Breakdown

| Component | Latency | Notes |
|-----------|---------|-------|
| Classic RAG | 2-6s | Hybrid retrieval + LLM synthesis |
| Quality Gate | <10ms | Rule-based checks (no LLM) |
| Agent (fallback) | 10-30s | Multi-step reasoning loop |

### Expected Distribution

Based on typical RAG workloads:

| Path | Percentage | Avg Latency |
|------|------------|-------------|
| Classic RAG (pass) | 70-90% | 2-6s |
| Agent (fail + fallback) | 10-30% | 10-30s |

**Overall average**: 4-8s per query (vs 10-30s for always-using-agent)

---

## Tuning

### Adjust Sensitivity

**Make gate MORE strict** (more agent fallbacks):
```python
# Increase minimum length
from elt_llm_agent.quality_gate import check_response_length
check_response_length(result, min_length=200)  # Was 100

# Add more empty phrases
from elt_llm_agent.quality_gate import check_empty_content
# Edit empty_phrases list to include more patterns
```

**Make gate LESS strict** (fewer agent fallbacks):
```python
# Remove checks
qc = run_quality_checks(result)
qc.passed = qc.has_citations  # Only require citations
```

### Custom Quality Logic

```python
from elt_llm_agent.quality_gate import run_quality_checks

def custom_quality_check(result) -> bool:
    """Custom quality logic for your use case."""
    qc = run_quality_checks(result)
    
    # Your custom logic
    if "Club" in query and qc.confidence_score < 0.5:
        return False  # Force agent for low-confidence Club queries
    
    return qc.passed
```

---

## Monitoring

### Log Quality Metrics

```python
import logging
from elt_llm_agent import query_with_quality_gate

logging.basicConfig(level=logging.INFO)

result = query_with_quality_gate(query, verbose=True)

# Logs will show:
# - Quality gate: passed=True/False
# - Quality check details (citations, empty, short, generic)
# - Confidence score
# - Which path taken (classic vs agent)
```

### Track Fallback Rate

```python
from elt_llm_agent import batch_query_with_quality_gate

results = batch_query_with_quality_gate(queries)

fallback_rate = sum(
    1 for r in results if r["source"] == "agentic_rag"
) / len(results)

print(f"Fallback rate: {fallback_rate:.0%}")

# If >30%: Consider improving classic RAG retrieval
# If <5%: Quality gate may be too lenient
```

---

## Integration with Consumer

### Re-run Problematic Entities with Agent

```python
import json
from elt_llm_agent import query_with_quality_gate

# Load consumer output
with open(".tmp/fa_consolidated_catalog_party.json") as f:
    catalog = json.load(f)

# Find LEANIX_ONLY or empty entities
party = catalog.get("PARTY", {})
for subtype, data in party.get("subtypes", {}).items():
    for entity in data.get("entities", []):
        if entity.get("source") == "LEANIX_ONLY" or not entity.get("formal_definition"):
            # Re-query with agent
            query = f"What does the FA Handbook say about {entity['entity_name']}?"
            result = query_with_quality_gate(query)
            
            if result["source"] == "agentic_rag":
                print(f"✓ Agent found content for {entity['entity_name']}")
                print(f"  {result['result'].response[:200]}...")
```

---

## Comparison: Before vs After

### Before (Always Agent)

```python
from elt_llm_agent import ReActAgent

agent = ReActAgent()

# Every query pays agent cost (10-30s)
result = agent.query("What is a Club?")  # 10-30s
result = agent.query("Tell me about Match Officials")  # 10-30s
result = agent.query("What about Club Official?")  # 10-30s

# Total: 30-90s for 3 queries
```

### After (Quality Gate)

```python
from elt_llm_agent import query_with_quality_gate

# Simple queries → classic RAG (2-6s)
result = query_with_quality_gate("What is a Club?")  # 2-6s, PASS

# Complex queries → agent fallback (10-30s)
result = query_with_quality_gate("Tell me about Match Officials")  # 2-6s, PASS
result = query_with_quality_gate("What about Club Official?")  # 15s, FAIL → agent

# Total: 19-37s for 3 queries (37-66% faster)
```

---

## Files Created

| File | Purpose |
|------|---------|
| `elt_llm_agent/src/elt_llm_agent/quality_gate.py` | Quality gate implementation |
| `test_quality_gate.py` | Test suite for quality gate |
| `QUALITY_GATE.md` | This documentation |

---

## Next Steps

### 1. Test with Your Queries

```bash
uv run python test_quality_gate.py
```

Review which queries trigger agent fallback — those are the ones where consumer returned "LEANIX_ONLY" or empty results.

### 2. Tune Thresholds

Adjust quality check parameters based on your results:
- Increase `min_length` if short answers are acceptable
- Add more empty phrases if specific patterns fail
- Adjust confidence threshold based on retrieval quality

### 3. Integrate with Consumer Workflow

```bash
# Step 1: Run consumer (baseline)
uv run python -m elt_llm_consumer.fa_consolidated_catalog --domain PARTY

# Step 2: Re-query problematic entities with quality gate
uv run python -c "
from elt_llm_agent import query_with_quality_gate
import json

# Load and find LEANIX_ONLY entities
with open('.tmp/fa_consolidated_catalog_party.json') as f:
    catalog = json.load(f)

# Re-query with agent fallback
for entity in find_leanix_only_entities(catalog):
    result = query_with_quality_gate(f'What does the Handbook say about {entity}?')
    if result['source'] == 'agentic_rag':
        print(f'✓ Agent found content for {entity}')
"
```

### 4. Monitor Performance

Track:
- **Fallback rate**: % of queries that trigger agent
- **Average latency**: Should be 4-8s (not 10-30s)
- **Quality improvement**: Does agent find content that classic RAG misses?

---

## Summary

**Quality Gate Benefits**:
- ✅ **Faster average latency**: 4-8s vs 10-30s
- ✅ **Cost-effective**: Only pay for agent when needed
- ✅ **Rule-based**: No LLM overhead for gate decisions
- ✅ **Transparent**: Clear reasons for pass/fail
- ✅ **Tunable**: Adjust sensitivity for your use case

**Recommended Workflow**:
1. Default to quality gate (not always agent)
2. Monitor fallback rate (target: 10-30%)
3. Re-query consumer's "LEANIX_ONLY" entities with agent
4. Merge agent results back into consumer output
