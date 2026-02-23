"""Query engine and retrieval interface."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from llama_index.core import VectorStoreIndex, Settings
from llama_index.core.query_engine import RetrieverQueryEngine

from elt_llm_core.models import OllamaConfig, create_embedding_model, create_llm_model
from elt_llm_core.vector_store import StorageContext

logger = logging.getLogger(__name__)


@dataclass
class QueryConfig:
    """Query engine configuration.

    Attributes:
        similarity_top_k: Number of similar chunks to retrieve.
        system_prompt: Optional system prompt for the LLM.
        response_mode: Response mode (default: "default").
    """

    similarity_top_k: int = 5
    system_prompt: str | None = None
    response_mode: str = "default"


def create_query_engine(
    index: VectorStoreIndex,
    ollama_config: OllamaConfig,
    query_config: QueryConfig,
) -> RetrieverQueryEngine:
    """Create a query engine from an index.

    Args:
        index: VectorStoreIndex to query.
        ollama_config: Ollama configuration.
        query_config: Query configuration.

    Returns:
        RetrieverQueryEngine for querying.
    """
    logger.info("Creating query engine (similarity_top_k=%d)", query_config.similarity_top_k)

    # Create and set LLM
    llm = create_llm_model(ollama_config)
    Settings.llm = llm

    # Create retriever
    retriever = index.as_retriever(similarity_top_k=query_config.similarity_top_k)

    # Create query engine
    query_engine = RetrieverQueryEngine(
        retriever=retriever,
        llm=llm,
    )

    logger.info("Query engine created")
    return query_engine


def query_index(
    index: VectorStoreIndex,
    query: str,
    ollama_config: OllamaConfig,
    query_config: QueryConfig,
) -> QueryResult:
    """Query a vector index.

    Args:
        index: VectorStoreIndex to query.
        query: Query string.
        ollama_config: Ollama configuration.
        query_config: Query configuration.

    Returns:
        QueryResult with response and source nodes.
    """
    logger.info("Querying index: %s", query)

    # Create query engine
    query_engine = create_query_engine(index, ollama_config, query_config)

    # Execute query
    response = query_engine.query(query)

    # Format source nodes
    source_nodes = []
    for node in response.source_nodes:
        source_nodes.append(
            {
                "text": node.node.text,
                "metadata": node.node.metadata,
                "score": node.score,
            }
        )

    return QueryResult(
        response=str(response),
        source_nodes=source_nodes,
    )


@dataclass
class QueryResult:
    """Query result with response and sources.

    Attributes:
        response: The LLM response text.
        source_nodes: List of source nodes with text, metadata, and scores.
    """

    response: str
    source_nodes: list[dict[str, Any]] = field(default_factory=list)

    def format_response(self) -> str:
        """Format the response with sources.

        Returns:
            Formatted response string.
        """
        output = [self.response, "\n\n--- Sources ---\n"]
        for i, source in enumerate(self.source_nodes, 1):
            score = source.get("score", "N/A")
            text = source.get("text", "")[:200]
            output.append(f"[{i}] Score: {score}\n    {text}...\n")
        return "\n".join(output)
