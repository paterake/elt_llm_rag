"""RAG query tool — wraps elt_llm_query for agent use."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)


@dataclass
class RAGQueryResult:
    """Result from RAG query tool."""

    response: str
    collection: str
    sources: list[dict[str, Any]] | None = None


def rag_query_tool(collection: str, query: str) -> str:
    """Query a RAG collection using hybrid retrieval + LLM synthesis.

    This tool queries the FA knowledge base (FA Handbook, LeanIX conceptual model,
    DAMA-DMBOK) using semantic + keyword search.

    Args:
        collection: Collection to query. Options:
            - "fa_handbook": FA Handbook rules and governance
            - "fa_leanix_dat_enterprise_conceptual_model": Conceptual data model
            - "fa_leanix_global_inventory": Asset inventory (applications, interfaces, etc.)
            - "dama_dmbok": DAMA-DMBOK data management knowledge
            - "all": Query all collections (slower)
        query: Natural language query

    Returns:
        LLM-synthesized answer with citations

    Example:
        >>> result = rag_query_tool(
        ...     collection="fa_handbook",
        ...     query="What are the governance rules for player registration?"
        ... )
    """
    try:
        from elt_llm_query.query import query_collections

        # Map collection to collection prefix
        collection_map = {
            "fa_handbook": ["fa_handbook"],
            "fa_leanix_dat_enterprise_conceptual_model": ["fa_leanix_dat_enterprise_conceptual_model"],
            "fa_leanix_global_inventory": ["fa_leanix_global_inventory"],
            "dama_dmbok": ["dama_dmbok"],
            "all": None,  # Will query all available
        }

        collections = collection_map.get(collection, ["fa_handbook"])

        logger.info(
            "RAG query: collection=%s, query=%s",
            collection,
            query[:100],
        )

        # Import config to get RAG config - use absolute path from project root
        from elt_llm_core.config import load_config
        from pathlib import Path
        project_root = Path(__file__).parent.parent.parent.parent.parent  # Goes to elt_llm_rag/
        rag_config = load_config(project_root / "elt_llm_ingest" / "config" / "rag_config.yaml")

        result = query_collections(
            collection_names=collections if collections else ["fa_handbook"],
            query=query,
            rag_config=rag_config,
            iterative=False,
        )

        # Format with sources if available
        output = [result.response]
        if hasattr(result, 'source_nodes') and result.source_nodes:
            output.append("\n\n--- Sources ---")
            for i, source in enumerate(result.source_nodes[:5], 1):
                collection_name = source.node.metadata.get("collection", "unknown") if hasattr(source, 'node') else "unknown"
                output.append(f"[{i}] ({collection_name})")

        return "\n".join(output)

    except ImportError as e:
        logger.error("elt_llm_query not available: %s", e)
        return f"Error: RAG query tool unavailable — {e}"
    except Exception as e:
        logger.exception("RAG query failed")
        return f"Error: {e}"


def create_rag_query_tool() -> FunctionTool:
    """Create LlamaIndex FunctionTool for RAG queries."""
    return FunctionTool.from_defaults(
        fn=rag_query_tool,
        name="rag_query",
        description="Query FA knowledge base (Handbook, LeanIX, DAMA) using semantic search. Use for governance rules, entity definitions, and conceptual model queries.",
    )


# Export as RAGQueryTool class for consistency
RAGQueryTool = create_rag_query_tool
