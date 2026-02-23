"""Query interface for RAG systems."""

from __future__ import annotations

import logging

from llama_index.core import VectorStoreIndex, Settings

from elt_llm_core.config import RagConfig
from elt_llm_core.models import create_embedding_model, create_llm_model
from elt_llm_core.query_engine import QueryConfig, QueryResult, create_query_engine
from elt_llm_core.vector_store import (
    ChromaConfig,
    create_chroma_client,
    create_storage_context,
)

logger = logging.getLogger(__name__)


def load_index(
    collection_name: str,
    rag_config: RagConfig,
) -> VectorStoreIndex:
    """Load an existing vector index from Chroma.

    Args:
        collection_name: Name of the Chroma collection.
        rag_config: RAG configuration.

    Returns:
        VectorStoreIndex loaded from storage.
    """
    logger.info("Loading index from Chroma: %s", collection_name)

    # Create Chroma client
    chroma_client = create_chroma_client(rag_config.chroma)

    # Create storage context
    storage_context = create_storage_context(
        chroma_client,
        collection_name,
    )

    # Set embedding model
    embed_model = create_embedding_model(rag_config.ollama)
    Settings.embed_model = embed_model

    # Load index from storage
    index = VectorStoreIndex.from_vector_store(
        storage_context.vector_store,
        storage_context=storage_context,
    )

    logger.info("Index loaded successfully")
    return index


def load_indices(
    collection_names: list[str],
    rag_config: RagConfig,
) -> list[VectorStoreIndex]:
    """Load multiple vector indices from Chroma.

    Args:
        collection_names: List of collection names.
        rag_config: RAG configuration.

    Returns:
        List of VectorStoreIndex instances.
    """
    indices = []
    for name in collection_names:
        try:
            index = load_index(name, rag_config)
            indices.append(index)
            logger.info("Loaded index for collection: %s", name)
        except Exception as e:
            logger.warning("Failed to load collection '%s': %s", name, e)
    return indices


def query_collection(
    collection_name: str,
    query: str,
    rag_config: RagConfig,
) -> QueryResult:
    """Query a collection.

    Args:
        collection_name: Name of the Chroma collection.
        query: Query string.
        rag_config: RAG configuration.

    Returns:
        QueryResult with response and source nodes.
    """
    logger.info("Querying collection '%s': %s", collection_name, query)

    # Load index
    index = load_index(collection_name, rag_config)

    # Create query config
    query_config = QueryConfig(
        similarity_top_k=rag_config.query.similarity_top_k,
        system_prompt=rag_config.query.system_prompt,
    )

    # Execute query
    result = query_index(index, query, rag_config, query_config)

    logger.info("Query complete")
    return result


def query_collections(
    collection_names: list[str],
    query: str,
    rag_config: RagConfig,
) -> QueryResult:
    """Query multiple collections and combine results.

    Args:
        collection_names: List of collection names to query.
        query: Query string.
        rag_config: RAG configuration.

    Returns:
        QueryResult with combined response and source nodes.
    """
    logger.info("Querying %d collections: %s", len(collection_names), collection_names)

    # Load all indices
    indices = load_indices(collection_names, rag_config)

    if not indices:
        return QueryResult(
            response="No collections found. Please ingest documents first.",
            source_nodes=[],
        )

    # Create query config
    query_config = QueryConfig(
        similarity_top_k=rag_config.query.similarity_top_k,
        system_prompt=rag_config.query.system_prompt,
    )

    # Query each index and combine results
    all_results = []
    for index in indices:
        result = query_index(index, query, rag_config, query_config)
        all_results.append(result)

    # Combine responses (use first response as primary)
    combined_response = all_results[0].response if all_results else "No results found."

    # Combine all source nodes
    combined_sources = []
    for result in all_results:
        combined_sources.extend(result.source_nodes)

    # Sort by score (highest first)
    combined_sources.sort(key=lambda x: x.get("score", 0) or 0, reverse=True)

    # Limit to top_k
    top_k = rag_config.query.similarity_top_k
    combined_sources = combined_sources[:top_k]

    return QueryResult(
        response=combined_response,
        source_nodes=combined_sources,
    )


def query_index(
    index: VectorStoreIndex,
    query: str,
    rag_config: RagConfig,
    query_config: QueryConfig,
) -> QueryResult:
    """Query an index.

    Args:
        index: VectorStoreIndex to query.
        query: Query string.
        rag_config: RAG configuration.
        query_config: Query configuration.

    Returns:
        QueryResult with response and source nodes.
    """
    from elt_llm_core.query_engine import query_index as core_query

    return core_query(index, query, rag_config.ollama, query_config)


def interactive_query(
    collection_name: str,
    rag_config: RagConfig,
) -> None:
    """Run interactive query session.

    Args:
        collection_name: Name of the Chroma collection.
        rag_config: RAG configuration.
    """
    print("\n=== RAG Query Interface ===")
    print(f"Collection: {collection_name}")
    print("Type 'quit' or 'exit' to stop\n")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        try:
            result = query_collection(collection_name, user_input, rag_config)
            print("\n=== Response ===\n")
            print(result.response)
            print(f"\n[Sources: {len(result.source_nodes)}]")
        except Exception as e:
            print(f"Error: {e}")


def interactive_query_collections(
    collection_names: list[str],
    rag_config: RagConfig,
) -> None:
    """Run interactive query session across multiple collections.

    Args:
        collection_names: List of collection names.
        rag_config: RAG configuration.
    """
    print("\n=== RAG Query Interface (Multi-Collection) ===")
    print(f"Collections: {', '.join(collection_names)}")
    print("Type 'quit' or 'exit' to stop\n")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        try:
            result = query_collections(collection_names, user_input, rag_config)
            print("\n=== Response ===\n")
            print(result.response)
            print(f"\n[Sources: {len(result.source_nodes)}]")
        except Exception as e:
            print(f"Error: {e}")
