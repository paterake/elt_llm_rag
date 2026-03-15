"""elt_llm_agentic — LLM-driven iterative RAG retrieval.

Implements a true ReAct (Reason + Act) retrieval loop where the LLM decides
at each step what to query next, based on what has been retrieved so far.

This is the agentic counterpart to elt_llm_consumer's fixed pipeline:

  elt_llm_consumer  — static 7-step pipeline, retrieval parameters fixed upfront
  elt_llm_agentic   — iterative loop, LLM decides query strategy per entity

Primary entry point:
    AgenticRetriever.retrieve_entity_context(entity_name, domain) -> dict

Batch catalog:
    uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY
"""

from elt_llm_agentic.retriever import AgenticRetriever, RetrieverConfig

__all__ = ["AgenticRetriever", "RetrieverConfig"]
