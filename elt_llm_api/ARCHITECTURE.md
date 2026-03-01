# elt_llm_api — Architecture

## Purpose
Lightweight user interfaces on top of the RAG system:
- Gradio web UI for interactive querying
- Programmatic API for embedding into tools and automations

## Components
- Gradio App ([app.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_api/src/elt_llm_api/app.py))
  - Local web server (default: http://localhost:7860)
  - Select profile, ask questions, view sources
- Programmatic API ([api.py](file:///Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/elt_llm_api/src/elt_llm_api/api.py))
  - Example `ask_dama(question)` convenience function that loads `RagConfig` and queries the `dama_dmbok` collection

## Commands
```bash
# Start the Gradio app
uv run python -m elt_llm_api.app

# Programmatic usage (as a library)
python -c "from elt_llm_api.api import ask_dama; print(ask_dama('What is data governance?').response)"
```

## Notes
- All querying ultimately delegates to `elt_llm_query.query`, which handles hybrid retrieval and reranking according to `rag_config.yaml`.
- The API module is intentionally small; expand with HTTP endpoints (e.g., FastAPI) when needed.

