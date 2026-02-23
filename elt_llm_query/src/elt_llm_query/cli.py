"""CLI entry point for querying."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from elt_llm_core.config import RagConfig
from elt_llm_query.query import interactive_query, query_collection, query_collections


def get_examples_dir() -> Path:
    """Get the examples directory path."""
    return Path(__file__).parent.parent / "examples"


def main() -> None:
    """CLI entry point for querying."""
    parser = argparse.ArgumentParser(description="Query RAG index")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to query configuration YAML file (e.g., examples/dama_only.yaml)",
    )
    parser.add_argument(
        "--rag-config",
        "-r",
        type=str,
        default=None,
        help="Path to RAG configuration YAML file",
    )
    parser.add_argument(
        "--collection",
        type=str,
        help="Single collection to query (overrides config)",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Query string (if not provided, runs interactive mode)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available query configs",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    examples_dir = get_examples_dir()

    # List configs mode
    if args.list:
        print("\nAvailable query configs:\n")
        for cfg in sorted(examples_dir.glob("*.yaml")):
            print(f"  {cfg.name}")
        print()
        return

    # Determine config paths
    if args.config:
        config_path = Path(args.config).expanduser()
    else:
        print("Error: --config is required (or use --list to see available configs)")
        raise SystemExit(1)

    if not config_path.exists():
        # Try examples directory
        alt_path = examples_dir / config_path.name
        if alt_path.exists():
            config_path = alt_path

    # Load query configuration
    with open(config_path) as f:
        query_data = yaml.safe_load(f)

    # Load RAG configuration if specified
    rag_config_path = args.rag_config
    if rag_config_path is None:
        # Try to load from same directory or use default
        rag_config_path = config_path.parent.parent / "elt_llm_ingest" / "config" / "rag_config.yaml"

    try:
        rag_config = RagConfig.from_yaml(rag_config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"RAG configuration error: {e}")
        raise SystemExit(1)

    # Get collections to query
    if args.collection:
        collections = [args.collection]
    else:
        collections_data = query_data.get("collections", [])
        collections = [c["name"] for c in collections_data]

    # Get query settings
    query_settings = query_data.get("query", {})
    rag_config.query.similarity_top_k = query_settings.get("similarity_top_k", 5)
    if "system_prompt" in query_settings:
        rag_config.query.system_prompt = query_settings["system_prompt"]

    if args.query:
        # Single query mode
        try:
            if len(collections) == 1:
                result = query_collection(collections[0], args.query, rag_config)
            else:
                result = query_collections(collections, args.query, rag_config)
            print("\n=== Response ===\n")
            print(result.response)
            print("\n=== Sources ===\n")
            for i, source in enumerate(result.source_nodes, 1):
                score = source.get("score", "N/A")
                text = source.get("text", "")[:200]
                print(f"[{i}] Score: {score}")
                print(f"    {text}...\n")
        except Exception as e:
            print(f"Error: {e}")
            raise SystemExit(1)
    else:
        # Interactive mode
        print(f"\nQuery mode: {'Multi-collection' if len(collections) > 1 else 'Single collection'}")
        print(f"Collections: {', '.join(collections)}\n")
        try:
            if len(collections) == 1:
                interactive_query(collections[0], rag_config)
            else:
                interactive_query_collections(collections, rag_config)
        except Exception as e:
            print(f"Error: {e}")
            raise SystemExit(1)


def interactive_query_collections(collections: list[str], rag_config: RagConfig) -> None:
    """Run interactive query session across multiple collections.

    Args:
        collections: List of collection names to query.
        rag_config: RAG configuration.
    """
    print("\n=== RAG Query Interface (Multi-Collection) ===")
    print(f"Collections: {', '.join(collections)}")
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
            result = query_collections(collections, user_input, rag_config)
            print("\n=== Response ===\n")
            print(result.response)
            print(f"\n[Sources: {len(result.source_nodes)}]")
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
