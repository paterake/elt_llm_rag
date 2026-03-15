# ELT LLM Agent

**Purpose**: Interactive Q&A with conversation memory. For batch catalog generation use `elt_llm_agentic`.

---

## Interactive Chat

```bash
uv run python -m elt_llm_agent.chat
```

Exploratory Q&A with conversation memory.

---

## Single Query

```bash
uv run python -m elt_llm_agent.query -q "What does the FA Handbook say about Club Official?"
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Agent architecture, tools, planners |

---

## Batch Catalog (Legacy)

The batch catalog command below is superseded by `elt_llm_agentic`, which implements a proper LLM-driven ReAct loop. Use `elt_llm_agentic` for catalog generation and comparison against `elt_llm_consumer`.

```bash
# Superseded — use elt_llm_agentic instead
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY
```
