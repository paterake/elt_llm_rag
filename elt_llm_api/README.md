# elt-llm-api

Gradio GUI and programmatic API for the RAG system. See [ARCHITECTURE.md](../ARCHITECTURE.md) for design documentation.

**All commands run from the repository root.**

---

## GUI

```bash
# Install
cd elt_llm_api && uv sync && cd ..

# Launch
uv run python -m elt_llm_api.app
# → http://localhost:7860
```

Two tabs:
- **Query** — select a knowledge base profile, chat with the RAG system
- **Ingest** — trigger document ingestion, refresh ChromaDB status

---

## Programmatic API

```python
from elt_llm_api.api import ask_dama

result = ask_dama("What is data governance?")
print(result.response)
```
