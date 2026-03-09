"""Graph traversal tool — relationship traversal using NetworkX (open-source)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"


def _load_relationships() -> list[dict[str, Any]]:
    """Load relationship data from JSON sidecars.

    Returns:
        List of relationship records with source/target entity info
    """
    relationships = []

    search_dirs = [DEFAULT_OUTPUT_DIR, Path.cwd() / ".tmp"]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        # Load from _model.json files (relationships embedded)
        for json_file in search_dir.glob("*_model.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                # Extract relationships if present
                if isinstance(data, dict) and "relationships" in data:
                    rels = data["relationships"]
                    if isinstance(rels, list):
                        relationships.extend(rels)
                        logger.debug(
                            "Loaded %d relationships from %s", len(rels), json_file.name
                        )

                # Also check for list of entities with relationships
                if isinstance(data, list):
                    for entity in data:
                        if "relationships" in entity:
                            for rel in entity["relationships"]:
                                rel["source_entity"] = entity.get("name")
                                relationships.append(rel)

            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load relationships from %s: %s", json_file.name, e)

        # Load from consolidated relationships file
        rel_file = search_dir / "fa_consolidated_relationships.json"
        if rel_file.exists():
            try:
                with open(rel_file, "r") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    relationships.extend(data)
                    logger.debug(
                        "Loaded %d relationships from fa_consolidated_relationships.json",
                        len(data),
                    )
            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load consolidated relationships: %s", e)

    return relationships


def _build_graph(relationships: list[dict[str, Any]]):
    """Build NetworkX directed graph from relationships.

    Args:
        relationships: List of relationship records

    Returns:
        NetworkX DiGraph with entity relationships
    """
    try:
        import networkx as nx
    except ImportError:
        logger.warning("NetworkX not installed — falling back to dict-based graph")
        return None

    G = nx.DiGraph()

    for rel in relationships:
        source = rel.get("source_entity") or rel.get("source") or rel.get("source_name")
        target = rel.get("target_entity") or rel.get("target") or rel.get("target_name")

        if not source or not target:
            continue

        # Add edge with relationship metadata
        G.add_edge(
            source,
            target,
            relationship_type=rel.get("relationship_type", "related"),
            cardinality=rel.get("cardinality", ""),
            source_file=rel.get("source", "unknown"),
            inverse_type=rel.get("inverse_type", ""),
        )

        # Add inverse edge for bidirectional traversal
        inverse_type = rel.get("inverse_type", f"{rel.get('relationship_type', 'related')} (inverse)")
        G.add_edge(
            target,
            source,
            relationship_type=inverse_type,
            cardinality=rel.get("cardinality", ""),
            source_file=rel.get("source", "unknown"),
            is_inverse=True,
        )

    logger.debug("Built graph: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def graph_traversal_tool(
    entity_name: str,
    relationship_type: str | None = None,
    max_depth: int = 2,
    operation: str = "neighbors",
) -> str:
    """Traverse entity relationships in the LeanIX conceptual model graph.

    This tool performs graph traversal to find connected entities, supporting
    multi-hop relationship queries that are difficult with vector search alone.

    Uses NetworkX (BSD license, open-source) for efficient graph operations.

    Args:
        entity_name: Name of the entity to start traversal from (e.g., "Club", "Player")
        relationship_type: Optional filter for relationship type (e.g., "owns", "participates_in")
        max_depth: Maximum traversal depth (default: 2 hops)
        operation: Graph operation to perform:
            - "neighbors": Find direct neighbors (1-hop)
            - "ego_graph": Find ego network up to max_depth
            - "all_shortest_paths": Find all shortest paths to other entities
            - "ancestors": Find all ancestors (predecessors)
            - "descendants": Find all descendants (successors)

    Returns:
        JSON-formatted string of connected entities and relationships

    Example:
        >>> # Find all entities connected to "Club"
        >>> result = graph_traversal_tool(entity_name="Club")

        >>> # Find ego network (2 hops)
        >>> result = graph_traversal_tool(
        ...     entity_name="FA",
        ...     operation="ego_graph",
        ...     max_depth=2
        ... )

        >>> # Find ancestors (what owns this entity?)
        >>> result = graph_traversal_tool(
        ...     entity_name="Player",
        ...     operation="ancestors"
        ... )
    """
    try:
        import networkx as nx
    except ImportError:
        return "Error: NetworkX not installed. Run: uv add networkx"

    relationships = _load_relationships()

    if not relationships:
        return "No relationships found. Run ingestion first: uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model"

    G = _build_graph(relationships)

    if G is None:
        return "Error: Failed to build graph"

    # Check if entity exists
    if entity_name not in G:
        # Try fuzzy match
        fuzzy_matches = [name for name in G.nodes() if entity_name.lower() in name.lower()]
        if fuzzy_matches:
            return f"Entity '{entity_name}' not found. Did you mean: {fuzzy_matches[:5]}?"
        return f"Entity '{entity_name}' not found in graph. Available entities: {list(G.nodes())[:20]}..."

    # Filter graph by relationship type if specified
    if relationship_type:
        filtered_G = nx.DiGraph()
        for u, v, data in G.edges(data=True):
            if relationship_type.lower() in data.get("relationship_type", "").lower():
                filtered_G.add_edge(u, v, **data)
        G = filtered_G

        if entity_name not in G:
            return f"No relationships of type '{relationship_type}' found for entity '{entity_name}'"

    result = {}

    if operation == "neighbors":
        # Direct neighbors (1-hop)
        neighbors = list(G.neighbors(entity_name))
        result = {
            "entity": entity_name,
            "operation": "neighbors",
            "total_neighbors": len(neighbors),
            "neighbors": [
                {
                    "entity": neighbor,
                    "relationship_type": G.edges[entity_name, neighbor].get("relationship_type", ""),
                    "cardinality": G.edges[entity_name, neighbor].get("cardinality", ""),
                }
                for neighbor in neighbors
            ],
        }

    elif operation == "ego_graph":
        # Ego network (multi-hop)
        ego = nx.ego_graph(G, entity_name, radius=max_depth)
        nodes = list(ego.nodes())
        edges = [(u, v, d) for u, v, d in ego.edges(data=True)]

        result = {
            "entity": entity_name,
            "operation": "ego_graph",
            "max_depth": max_depth,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": nodes[:50],  # Limit output
            "edges": [
                {"source": u, "target": v, "type": d.get("relationship_type", "")}
                for u, v, d in edges[:50]
            ],
        }

    elif operation == "ancestors":
        # All ancestors (predecessors)
        ancestors = nx.ancestors(G, entity_name)
        result = {
            "entity": entity_name,
            "operation": "ancestors",
            "total_ancestors": len(ancestors),
            "ancestors": list(ancestors)[:50],
        }

    elif operation == "descendants":
        # All descendants (successors)
        descendants = nx.descendants(G, entity_name)
        result = {
            "entity": entity_name,
            "operation": "descendants",
            "total_descendants": len(descendants),
            "descendants": list(descendants)[:50],
        }

    elif operation == "all_shortest_paths":
        # Shortest paths to all other nodes
        paths = {}
        for target in G.nodes():
            if target != entity_name:
                try:
                    path = nx.shortest_path(G, source=entity_name, target=target)
                    if len(path) <= max_depth + 1:  # Respect max_depth
                        paths[target] = path
                except nx.NetworkXNoPath:
                    pass

        result = {
            "entity": entity_name,
            "operation": "all_shortest_paths",
            "max_depth": max_depth,
            "total_reachable": len(paths),
            "paths": {k: v for k, v in list(paths.items())[:20]},  # Limit output
        }

    else:
        return f"Unknown operation: {operation}. Valid: neighbors, ego_graph, ancestors, descendants, all_shortest_paths"

    return json.dumps(result, indent=2)


def create_graph_traversal_tool() -> FunctionTool:
    """Create LlamaIndex FunctionTool for graph traversal."""
    return FunctionTool.from_defaults(
        fn=graph_traversal_tool,
        name="graph_traversal",
        description="Traverse LeanIX conceptual model graph using NetworkX. Operations: neighbors (1-hop), ego_graph (multi-hop), ancestors, descendants. Use for relationship queries.",
    )


GraphTraversalTool = create_graph_traversal_tool
