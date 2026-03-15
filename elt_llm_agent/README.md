# ELT LLM Agent

**Purpose**: Agentic RAG for interactive Q&A and batch catalog generation

---

## Quick Commands

### Interactive Chat
```bash
uv run python -m elt_llm_agent.chat
```
Exploratory Q&A with conversation memory

---

### Single Query
```bash
uv run python -m elt_llm_agent.query -q "What does the FA Handbook say about Club Official?"
```
One-off query without chat session

---

### Batch Catalog Generation
```bash
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY
```
Generate structured catalog for entire domain (alternative to `elt_llm_consumer`)

**Options**:
- `--domain PARTY` — Filter to single domain
- `--entity "Club,Player"` — Filter to specific entities
- `--output-dir .tmp` — Output directory

**Output**: `.tmp/fa_agent_catalog_{domain}.json`

---

### Compare Agent vs Consumer
```bash
# First run both catalogs
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Then compare
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```
Side-by-side quality comparison

---

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | System architecture, components, data flow |
| [AGENTIC_RAG_FOR_CATALOGS.md](AGENTIC_RAG_FOR_CATALOGS.md) | Agentic vs traditional RAG for batch processing |
| [AGENT_VS_CONSUMER.md](AGENT_VS_CONSUMER.md) | Detailed comparison with `elt_llm_consumer` |
| [QUALITY_GATE.md](QUALITY_GATE.md) | Quality gate implementation |
| [INDUSTRY_BEST_PRACTICES.md](INDUSTRY_BEST_PRACTICES.md) | How we compare to industry standards |
| [OPEN_SOURCE_GRAPH_OPTIONS.md](OPEN_SOURCE_GRAPH_OPTIONS.md) | Graph technology choices |

---

## When to Use

| Use Case | Tool |
|----------|------|
| Batch catalog generation (stakeholder review) | `elt_llm_consumer` |
| Quick domain scan | `elt_llm_agent` |
| Debugging LEANIX_ONLY entities | `elt_llm_agent` |
| Interactive Q&A | `elt_llm_agent.chat` |
| Purview/Erwin import | `elt_llm_consumer` output |

---

## Performance

| Domain | Entities | Agent Runtime | Consumer Runtime |
|--------|----------|--------------|------------------|
| PARTY | 28 | ~10-20 min | ~45-60 min |
| All domains | 175 | ~60-90 min | ~3-4 hours |

**Agent is 3-4x faster** (dynamic section selection vs querying all 44 sections)
