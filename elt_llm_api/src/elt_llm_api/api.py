from __future__ import annotations

import os
from pathlib import Path

from elt_llm_core.config import RagConfig
from elt_llm_core.query_engine import QueryResult
from elt_llm_query.query import query_collection

_DEFAULT_COLLECTION = os.environ.get("RAG_DEFAULT_COLLECTION", "dama_dmbok")


def ask_dama(
    question: str,
    rag_config_path: str | Path | None = None,
    collection: str = _DEFAULT_COLLECTION,
) -> QueryResult:
    if rag_config_path is None:
        base_dir = Path(__file__).resolve().parents[3]
        rag_config_path = base_dir / "elt_llm_ingest" / "config" / "rag_config.yaml"
    rag_config = RagConfig.from_yaml(rag_config_path)
    return query_collection(collection, question, rag_config)

