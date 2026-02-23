"""Generic RAG query runner.

Usage:
    uv run python -m elt_llm_query.runner --cfg <config_name> [-q "query"] [-v]
    uv run python -m elt_llm_query.runner --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from elt_llm_core.config import RagConfig
from elt_llm_query.query import interactive_query, query_collection, query_collections


def get_examples_dir() -> Path:
    """Get the examples directory path."""
    # Try multiple locations: package install and development
    candidates = [
        Path(__file__).parent.parent / "examples",  # Installed package
        Path(__file__).parent.parent.parent.parent / "elt_llm_query" / "examples",  # Development
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Default to development location
    return candidates[1]


def get_ingest_config_dir() -> Path:
    """Get the ingest config directory path."""
    # Try multiple locations
    candidates = [
        Path(__file__).parent.parent.parent / "elt_llm_ingest" / "config",  # Installed
        Path(__file__).parent.parent.parent.parent / "elt_llm_ingest" / "config",  # Development
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[1]


def list_configs() -> int:
    """List available query configurations."""
    examples_dir = get_examples_dir()

    print("\n=== Available RAG Query Configs ===\n")
    print(f"Config directory: {examples_dir}\n")

    configs = []
    for cfg in sorted(examples_dir.glob("*.yaml")):
        config_name = cfg.stem
        configs.append(config_name)

        # Load to show collections
        with open(cfg) as f:
            data = yaml.safe_load(f)
        collections = [c["name"] for c in data.get("collections", [])]

        print(f"  {config_name}")
        print(f"    Collections: {', '.join(collections)}")

    if not configs:
        print("  No configs found.")
        return 1

    print("\n=== Usage ===")
    print("\nInteractive query:")
    for config_name in configs:
        print(f"  uv run python -m elt_llm_query.runner --cfg {config_name}")

    print("\nSingle query:")
    for config_name in configs:
        print(f"  uv run python -m elt_llm_query.runner --cfg {config_name} -q \"Your question\"")

    print("\nVerbose mode:")
    print(f"  uv run python -m elt_llm_query.runner --cfg {configs[0]} -v\n")

    return 0


def query(config_name: str, query_text: str | None = None, verbose: bool = False) -> int:
    """Query using the specified config.

    Args:
        config_name: Name of the config file (without .yaml extension).
        query_text: Optional query string (interactive mode if not provided).
        verbose: Enable verbose logging.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # Configure logging
    import logging

    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    examples_dir = get_examples_dir()
    ingest_config_dir = get_ingest_config_dir()

    # Load query config
    query_path = examples_dir / f"{config_name}.yaml"
    if not query_path.exists():
        print(f"❌ Error: Query config not found: {query_path}")
        return 1

    with open(query_path) as f:
        query_data = yaml.safe_load(f)

    # Load RAG config
    rag_config_path = ingest_config_dir / "rag_config.yaml"
    try:
        rag_config = RagConfig.from_yaml(rag_config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ RAG configuration error: {e}")
        return 1

    # Get collections to query
    collections_data = query_data.get("collections", [])
    collections = [c["name"] for c in collections_data]

    # Apply query settings
    query_settings = query_data.get("query", {})
    rag_config.query.similarity_top_k = query_settings.get("similarity_top_k", 5)
    if "system_prompt" in query_settings:
        rag_config.query.system_prompt = query_settings["system_prompt"]

    if query_text:
        # Single query mode
        try:
            if len(collections) == 1:
                result = query_collection(collections[0], query_text, rag_config)
            else:
                result = query_collections(collections, query_text, rag_config)

            print("\n=== Response ===\n")
            print(result.response)
            print("\n=== Sources ===\n")
            for i, source in enumerate(result.source_nodes, 1):
                score = source.get("score", "N/A")
                text = source.get("text", "")[:200]
                print(f"[{i}] Score: {score}")
                print(f"    {text}...\n")
            return 0
        except Exception as e:
            print(f"❌ Error: {e}")
            return 1
    else:
        # Interactive mode
        print(f"\n=== RAG Query Interface ===")
        print(f"Config: {config_name}")
        print(f"Collections: {', '.join(collections)}")
        print("Type 'quit' or 'exit' to stop\n")

        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if user_input.lower() in ("quit", "exit", "q"):
                print("Goodbye!")
                break

            if not user_input:
                continue

            try:
                if len(collections) == 1:
                    result = query_collection(collections[0], user_input, rag_config)
                else:
                    result = query_collections(collections, user_input, rag_config)

                print("\n=== Response ===\n")
                print(result.response)
                print(f"\n[Sources: {len(result.source_nodes)}]")
            except Exception as e:
                print(f"❌ Error: {e}")

        return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generic RAG query runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available configs
  uv run python -m elt_llm_query.runner --list

  # Interactive query (DAMA only)
  uv run python -m elt_llm_query.runner --cfg dama_only

  # Single query
  uv run python -m elt_llm_query.runner --cfg dama_only -q "What is data governance?"

  # Query multiple collections
  uv run python -m elt_llm_query.runner --cfg dama_fa_combined -q "How does X relate to Y?"

  # Verbose output
  uv run python -m elt_llm_query.runner --cfg dama_only -v
        """,
    )
    parser.add_argument(
        "--cfg",
        type=str,
        help="Config name (without .yaml extension), e.g., 'dama_only'",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available query configs",
    )
    parser.add_argument(
        "--query",
        "-q",
        type=str,
        help="Query string (if not provided, runs interactive mode)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # List mode
    if args.list:
        return list_configs()

    # Require --cfg for query operations
    if not args.cfg:
        print("❌ Error: --cfg is required (or use --list to see available configs)")
        parser.print_help()
        return 1

    # Query mode
    return query(args.cfg, query_text=args.query, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
