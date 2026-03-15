"""Graph traversal — multi-hop relationship queries on the LeanIX conceptual model.

Uses NetworkX (BSD licence) to traverse entity relationships from the
_model.json sidecar or the consolidated relationships output.

Operations:
    neighbors         — 1-hop direct connections
    ego_graph         — all nodes within max_depth hops
    ancestors         — all predecessors (what owns / governs this entity?)
    descendants       — all successors (what does this entity govern?)
    all_shortest_paths — shortest paths to every reachable entity

Usage:
    from elt_llm_agentic.graph_traversal import graph_traversal

    result = graph_traversal("Club", operation="neighbors")
    result = graph_traversal("Player", operation="ego_graph", max_depth=2)
    result = graph_traversal("Club", operation="ancestors")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_SEARCH_DIRS = [
    Path(__file__).parent.parent.parent.parent.parent / ".tmp",
    Path.cwd() / ".tmp",
]


def _load_relationships(search_dirs: list[Path] | None = None) -> list[dict[str, Any]]:
    """Load relationship records from _model.json or consolidated relationships file."""
    dirs = search_dirs or _DEFAULT_SEARCH_DIRS
    relationships: list[dict[str, Any]] = []

    for d in dirs:
        if not d.exists():
            continue
        for json_file in d.glob("*_model.json"):
            try:
                data = json.loads(json_file.read_text())
                if isinstance(data, dict) and "relationships" in data:
                    relationships.extend(data["relationships"])
            except Exception as e:
                logger.warning("Failed to load %s: %s", json_file.name, e)

        rel_file = d / "fa_consolidated_relationships.json"
        if rel_file.exists():
            try:
                data = json.loads(rel_file.read_text())
                if isinstance(data, list):
                    relationships.extend(data)
            except Exception as e:
                logger.warning("Failed to load relationships file: %s", e)

    return relationships


def _build_graph(relationships: list[dict[str, Any]]) -> Any | None:
    """Build a NetworkX DiGraph from relationship records."""
    try:
        import networkx as nx
    except ImportError:
        logger.warning("NetworkX not installed — run: uv add networkx")
        return None

    G = nx.DiGraph()
    for rel in relationships:
        src = rel.get("source_entity") or rel.get("source")
        tgt = rel.get("target_entity") or rel.get("target")
        if not src or not tgt:
            continue
        G.add_edge(src, tgt,
                   relationship_type=rel.get("relationship_type", "related"),
                   cardinality=rel.get("cardinality", ""))
        inv = rel.get("inverse_type", f"inverse_{rel.get('relationship_type', 'related')}")
        G.add_edge(tgt, src, relationship_type=inv, cardinality=rel.get("cardinality", ""))

    logger.debug("Graph: %d nodes, %d edges", G.number_of_nodes(), G.number_of_edges())
    return G


def graph_traversal(
    entity_name: str,
    operation: str = "neighbors",
    relationship_type: str | None = None,
    max_depth: int = 2,
    model_json: Path | None = None,
) -> str:
    """Traverse entity relationships in the LeanIX conceptual model.

    Args:
        entity_name:       Starting entity (e.g. "Club", "Player")
        operation:         neighbors | ego_graph | ancestors | descendants | all_shortest_paths
        relationship_type: Optional filter (e.g. "owns")
        max_depth:         Traversal depth for ego_graph / all_shortest_paths
        model_json:        Explicit path to _model.json (auto-discovered if None)

    Returns:
        JSON-formatted string of results.
    """
    try:
        import networkx as nx
    except ImportError:
        return "Error: NetworkX not installed. Run: uv add networkx"

    search_dirs = [model_json.parent] if model_json else None
    relationships = _load_relationships(search_dirs)
    if not relationships:
        return "No relationships found. Run ingestion first."

    G = _build_graph(relationships)
    if G is None:
        return "Error: could not build graph"

    if entity_name not in G:
        candidates = [n for n in G.nodes() if entity_name.lower() in n.lower()]
        if candidates:
            return json.dumps({"error": f"'{entity_name}' not found", "suggestions": candidates[:5]}, indent=2)
        return json.dumps({"error": f"'{entity_name}' not found", "total_nodes": G.number_of_nodes()}, indent=2)

    if relationship_type:
        G = nx.DiGraph(
            (u, v, d) for u, v, d in G.edges(data=True)
            if relationship_type.lower() in d.get("relationship_type", "").lower()
        )
        if entity_name not in G:
            return json.dumps({"error": f"No '{relationship_type}' relationships for '{entity_name}'"}, indent=2)

    if operation == "neighbors":
        result = {
            "entity": entity_name,
            "operation": "neighbors",
            "neighbors": [
                {"entity": n,
                 "relationship_type": G.edges[entity_name, n].get("relationship_type", ""),
                 "cardinality": G.edges[entity_name, n].get("cardinality", "")}
                for n in G.neighbors(entity_name)
            ],
        }
        result["total"] = len(result["neighbors"])

    elif operation == "ego_graph":
        ego = nx.ego_graph(G, entity_name, radius=max_depth)
        result = {
            "entity": entity_name,
            "operation": "ego_graph",
            "max_depth": max_depth,
            "total_nodes": ego.number_of_nodes(),
            "total_edges": ego.number_of_edges(),
            "nodes": list(ego.nodes())[:50],
            "edges": [
                {"source": u, "target": v, "type": d.get("relationship_type", "")}
                for u, v, d in list(ego.edges(data=True))[:50]
            ],
        }

    elif operation == "ancestors":
        anc = nx.ancestors(G, entity_name)
        result = {"entity": entity_name, "operation": "ancestors",
                  "total": len(anc), "ancestors": list(anc)[:50]}

    elif operation == "descendants":
        desc = nx.descendants(G, entity_name)
        result = {"entity": entity_name, "operation": "descendants",
                  "total": len(desc), "descendants": list(desc)[:50]}

    elif operation == "all_shortest_paths":
        paths = {}
        for tgt in G.nodes():
            if tgt == entity_name:
                continue
            try:
                p = nx.shortest_path(G, source=entity_name, target=tgt)
                if len(p) <= max_depth + 1:
                    paths[tgt] = p
            except nx.NetworkXNoPath:
                pass
        result = {"entity": entity_name, "operation": "all_shortest_paths",
                  "max_depth": max_depth, "total_reachable": len(paths),
                  "paths": dict(list(paths.items())[:20])}

    else:
        return f"Unknown operation '{operation}'. Valid: neighbors, ego_graph, ancestors, descendants, all_shortest_paths"

    return json.dumps(result, indent=2)
