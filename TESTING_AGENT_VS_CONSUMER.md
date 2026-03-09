# Testing Agentic RAG vs Consumer

**Purpose**: Compare the agent's output quality against the consumer for the same entity queries.

## Current Issue with Consumer

Running:
```bash
uv run python -m elt_llm_consumer.fa_consolidated_catalog --domain PARTY --skip-relationships
```

**Problems observed**:
1. Many entities return "Not defined in FA Handbook" (empty results)
2. Governance rules are thin or missing
3. No conversation context - each entity processed independently

## Agent Improvements

The agent (`elt_llm_agent`) offers:
1. **Multi-step reasoning** - Can try multiple approaches if one fails
2. **Conversation context** - Remembers previous queries in a session
3. **Tool flexibility** - Can use JSON lookup, RAG, or graph traversal as needed
4. **Loop detection** - Prevents infinite retries on failed tools

## Test Setup

### Files Created

| File | Purpose |
|------|---------|
| `test_agent_quick.py` | Quick test with 3 sample queries |
| `test_agent_rag_only.py` | Compare agent vs direct RAG (consumer approach) |
| `elt_llm_agent/test_agent_vs_consumer.py` | Full comparison script |

### Agent Fixes Applied

1. **Loop detection** - Stops after 2 consecutive same-tool calls
2. **Error handling** - Detects "no data" responses and switches strategy
3. **RAG-first strategy** - Starts with RAG query (more reliable than JSON lookup)
4. **Config loading** - Fixed path to rag_config.yaml

## How to Test

### Option 1: Quick Test

```bash
cd /Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag
uv run python test_agent_quick.py
```

This tests 3 entities:
- Club Official
- Match Official
- Club

### Option 2: Interactive Chat

```bash
uv run python -m elt_llm_agent.chat --max-iterations 5

# Then ask:
# "What does the FA Handbook say about Club Official?"
# "What are the governance rules for Match Officials?"
# /exit
```

### Option 3: Full Comparison

```bash
# First run consumer to generate baseline
uv run python -m elt_llm_consumer.fa_consolidated_catalog --domain PARTY --skip-relationships

# Then run agent comparison
uv run python -m elt_llm_agent.test_agent_vs_consumer
```

## Expected Agent Behavior

### Query: "What does the FA Handbook say about Club Official?"

**Agent reasoning loop**:
1. **Step 1**: `rag_query(collection="fa_handbook", query="...")` 
   - Queries FA Handbook directly
   - Returns RAG retrieval + LLM synthesis
   
2. **Step 2**: Checks if response has sufficient content
   - If yes → Synthesize final answer
   - If no → Try `json_lookup` for entity context

3. **Synthesis**: Combines tool outputs into natural language answer

**Expected output structure**:
```
Based on my analysis:

[RAG_QUERY]
Club Official is referenced in the FA Handbook in the context of...
Governance: Section 10(A)(1) specifies advertising rules...
Sources: fa_handbook_section_10, fa_handbook_section_A

---
Note: This is a simplified synthesis. Enable LLM-based synthesis for better answers.
```

## Comparison Metrics

| Metric | Consumer | Agent |
|--------|----------|-------|
| **Runtime per entity** | ~60-90s | ~10-20s |
| **Output format** | Structured JSON | Natural language |
| **Error handling** | Fails silently ("Not defined") | Tries alternative tools |
| **Context awareness** | None (stateless) | Conversation memory |
| **Best for** | Batch processing, stakeholder review | Exploration, Q&A |

## Next Steps

### 1. Run Consumer First (Baseline)
```bash
uv run python -m elt_llm_consumer.fa_consolidated_catalog --domain PARTY --skip-relationships
```

### 2. Review Consumer Output
```bash
cat .tmp/fa_consolidated_catalog_party.json | python -m json.tool | head -100
```

Look for entities with:
- `"source": "LEANIX_ONLY"` (no handbook coverage)
- Empty `formal_definition` or `governance_rules`

### 3. Test Same Entities with Agent
```bash
uv run python -m elt_llm_agent.chat

# Ask about problematic entities:
# "What does the FA Handbook say about Board & Committee Members?"
# "What are the governance rules for Coach Developer?"
```

### 4. Compare Results

**Consumer output** (from JSON):
```json
{
  "entity_name": "Club Official",
  "formal_definition": "...",
  "governance_rules": "..."
}
```

**Agent output** (from chat):
```
Club Official is defined in the FA Handbook as...
Governance rules include Section 10(A)(1)...
```

### 5. Decision

**Use Consumer if**:
- You need structured, reviewable JSON output
- Processing all 175 entities systematically
- Output will be imported to Purview/Erwin

**Use Agent if**:
- You need fast answers for specific entities
- Exploring/hunting for governance rules
- Want to ask follow-up questions

## Known Issues

### Agent Issues
1. **JSON sidecars not available** - Agent expects `_model.json` files that aren't created by default
   - **Fix**: Run full ingestion first OR use RAG-only mode
   
2. **Simple synthesis** - Current agent concatenates tool outputs (no LLM synthesis)
   - **Fix**: Add LLM-based synthesis prompt (future enhancement)

### Consumer Issues
1. **Empty results** - Many entities return "Not defined in FA Handbook"
   - **Cause**: Prompt may be too specific, or retrieval not finding relevant chunks
   - **Investigation needed**: Check RAG retrieval quality

## Recommendations

### Immediate Actions

1. **Test agent with problematic entities**
   - Run agent chat for entities that returned LEANIX_ONLY in consumer
   - Compare output quality

2. **Improve agent synthesis**
   - Add LLM-based synthesis (currently just concatenates)
   - Better citation formatting

3. **Fix consumer empty results**
   - Review retrieval parameters (top_k, reranker settings)
   - Check if prompt is too restrictive

### Long-term Enhancements

1. **Hybrid workflow**:
   - Consumer generates baseline catalog
   - Agent re-queries entities with "LEANIX_ONLY" or thin coverage
   - Merge results

2. **Agent improvements**:
   - Add structured output mode (JSON schema)
   - Batch mode for systematic entity processing
   - Better LLM synthesis prompt

## Files Modified

| File | Change |
|------|--------|
| `elt_llm_agent/agent.py` | Added loop detection, error handling |
| `elt_llm_agent/planners/__init__.py` | RAG-first strategy, error-aware planning |
| `elt_llm_agent/tools/rag_query.py` | Fixed imports, config loading |
| `elt_llm_agent/tools/__init__.py` | Exported factory functions |
| `test_agent_quick.py` | New test script |
| `AGENT_VS_CONSUMER.md` | Detailed comparison doc |
| `elt_llm_agent/ARCHITECTURE.md` | Full agent architecture |
