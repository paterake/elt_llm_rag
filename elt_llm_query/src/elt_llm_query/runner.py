"""Generic RAG query runner.

Usage:
    uv run python -m elt_llm_query.runner --cfg <config_name> [-q "query"] [-v]
    uv run python -m elt_llm_query.runner --list
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
import itertools
from pathlib import Path
from typing import ContextManager

import yaml

from elt_llm_core.config import RagConfig
from elt_llm_query.query import (
    interactive_query,
    query_collection,
    query_collections,
    resolve_collection_prefixes,
)


class Spinner(ContextManager):
    """Simple terminal spinner."""

    def __init__(self, message: str = "Processing..."):
        self.message = message
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._spin)

    def _spin(self) -> None:
        spinner = itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"])
        while not self.stop_event.is_set():
            sys.stdout.write(f"\r{next(spinner)} {self.message}")
            sys.stdout.flush()
            time.sleep(0.1)
        sys.stdout.write(f"\r{' ' * (len(self.message) + 2)}\r")
        sys.stdout.flush()

    def __enter__(self) -> "Spinner":
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_event.set()
        self.thread.join()


def get_examples_dir() -> Path:
    """Get the llm_rag_profile directory path."""
    # Try multiple locations: package install and development
    candidates = [
        Path(__file__).parent.parent / "llm_rag_profile",  # Installed package
        Path(__file__).parent.parent.parent.parent / "elt_llm_query" / "llm_rag_profile",  # Development
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
        prefixes = [p["name"] for p in data.get("collection_prefixes", [])]

        print(f"  {config_name}")
        parts = []
        if collections:
            parts.append(", ".join(collections))
        if prefixes:
            parts.append("prefixes: " + ", ".join(f"{p}_*" for p in prefixes))
        print(f"    Collections: {' | '.join(parts) if parts else '(none)'}")

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


def query(config_name: str, query_text: str | None = None, log_level: str = "CRITICAL") -> int:
    """Query using the specified config.

    Args:
        config_name: Name of the config file (without .yaml extension).
        query_text: Optional query string (interactive mode if not provided).
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).

    Returns:
        Exit code (0 for success, 1 for error).
    """
    # Configure logging
    numeric_level = getattr(logging, log_level.upper(), logging.CRITICAL)
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,  # Override any existing config
    )

    # Suppress noisy libraries unless in DEBUG mode
    if numeric_level > logging.DEBUG:
        for lib in ["httpx", "httpcore", "chromadb", "llama_index", "urllib3"]:
            logging.getLogger(lib).setLevel(logging.WARNING)

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

    # Get collections to query — explicit names + prefix-resolved names
    collections_data = query_data.get("collections", [])
    explicit_collections = [c["name"] for c in collections_data]

    prefix_data = query_data.get("collection_prefixes", [])
    prefixes = [p["name"] for p in prefix_data]

    resolved_collections: list[str] = []
    if prefixes:
        try:
            resolved_collections = resolve_collection_prefixes(prefixes, rag_config)
        except Exception as e:
            print(f"❌ Error resolving collection prefixes {prefixes}: {e}")
            return 1

    # Merge: explicit first, then prefix-resolved (deduplicated)
    seen: set[str] = set(explicit_collections)
    for name in resolved_collections:
        if name not in seen:
            explicit_collections.append(name)
            seen.add(name)
    collections = explicit_collections

    if not collections:
        print("❌ Error: No collections defined in config (add 'collections' or 'collection_prefixes')")
        return 1

    # Apply query settings
    query_settings = query_data.get("query", {})
    rag_config.query.similarity_top_k = query_settings.get("similarity_top_k", 5)
    if "system_prompt" in query_settings:
        rag_config.query.system_prompt = query_settings["system_prompt"]

    if query_text:
        # Single query mode
        try:
            with Spinner("Thinking..."):
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
        if prefixes:
            print(f"Prefixes: {', '.join(f'{p}_*' for p in prefixes)} → {len(resolved_collections)} collections")
        print(f"Collections ({len(collections)}): {', '.join(collections)}")
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
                with Spinner("Thinking..."):
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
        "--log-level",
        type=str,
        default="CRITICAL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set logging level (default: CRITICAL)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging (equivalent to --log-level DEBUG)",
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

    # Determine log level
    log_level = "DEBUG" if args.verbose else args.log_level

    # Query mode
    return query(args.cfg, query_text=args.query, log_level=log_level)


if __name__ == "__main__":
    sys.exit(main())
