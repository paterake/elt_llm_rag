"""Generic RAG ingestion runner.

Usage:
    uv run python -m elt_llm_ingest.runner --cfg <config_name> [-v] [--no-rebuild]
    uv run python -m elt_llm_ingest.runner --cfg <config_name> --delete [-f]
    uv run python -m elt_llm_ingest.runner --list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chromadb
import yaml

from elt_llm_core.config import RagConfig
from elt_llm_ingest.ingest import IngestConfig, run_ingestion


def get_config_dir() -> Path:
    """Get the config directory path."""
    # Try multiple locations: package install and development
    candidates = [
        Path(__file__).parent.parent / "config",  # Installed package
        Path(__file__).parent.parent.parent.parent / "elt_llm_ingest" / "config",  # Development
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Default to development location
    return candidates[1]


def list_configs() -> int:
    """List available configurations."""
    config_dir = get_config_dir()

    print("\n=== Available RAG Ingestion Configs ===\n")
    print(f"Config directory: {config_dir}\n")

    configs = []
    for cfg in sorted(config_dir.glob("*.yaml")):
        if cfg.name != "rag_config.yaml":
            config_name = cfg.stem
            configs.append(config_name)
            print(f"  {config_name}")

    if not configs:
        print("  No configs found.")
        return 1

    print("\n=== Usage ===")
    print("\nIngest:")
    for config_name in configs:
        print(f"  uv run python -m elt_llm_ingest.runner --cfg {config_name}")

    print("\nDelete:")
    for config_name in configs:
        print(f"  uv run python -m elt_llm_ingest.runner --cfg {config_name} --delete")

    print("\nVerbose mode:")
    print(f"  uv run python -m elt_llm_ingest.runner --cfg {configs[0]} -v\n")

    print("Append mode (don't rebuild):")
    print(f"  uv run python -m elt_llm_ingest.runner --cfg {configs[0]} --no-rebuild\n")

    print("Force delete (skip confirmation):")
    print(f"  uv run python -m elt_llm_ingest.runner --cfg {configs[0]} --delete -f\n")

    return 0


def ingest(config_name: str, verbose: bool = False, no_rebuild: bool = False) -> int:
    """Ingest documents using the specified config.

    Args:
        config_name: Name of the config file (without .yaml extension).
        verbose: Enable verbose logging.
        no_rebuild: Don't rebuild the collection.

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
    for name in (
        "httpx",
        "httpcore",
        "chromadb",
        "llama_index",
        "llama_index.core.node_parser.node_utils",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)

    config_dir = get_config_dir()

    # Load RAG configuration
    try:
        rag_config = RagConfig.from_yaml(config_dir / "rag_config.yaml")
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ RAG configuration error: {e}")
        return 1

    # Load ingestion config
    ingest_path = config_dir / f"{config_name}.yaml"
    if not ingest_path.exists():
        print(f"❌ Error: Ingestion config not found: {ingest_path}")
        return 1

    with open(ingest_path) as f:
        ingest_data = yaml.safe_load(f)

    # Create ingestion config
    ingest_config = IngestConfig(
        collection_name=ingest_data["collection_name"],
        file_paths=ingest_data.get("file_paths", []),
        metadata=ingest_data.get("metadata"),
        rebuild=not no_rebuild,
    )

    try:
        index = run_ingestion(ingest_config, rag_config)
        doc_count = len(index.docstore.docs) if index.docstore else 0
        print(f"\n✅ Ingestion complete: {doc_count} chunks indexed")
        return 0
    except ValueError as e:
        print(f"❌ Error: {e}")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return 1


def delete(config_name: str, force: bool = False) -> int:
    """Delete a collection.

    Args:
        config_name: Name of the config file (without .yaml extension).
        force: Skip confirmation prompt.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    config_dir = get_config_dir()

    # Load ingestion config to get collection name
    ingest_path = config_dir / f"{config_name}.yaml"
    if not ingest_path.exists():
        print(f"❌ Error: Ingestion config not found: {ingest_path}")
        return 1

    with open(ingest_path) as f:
        ingest_data = yaml.safe_load(f)

    collection_name = ingest_data["collection_name"]

    # Load RAG config to get persist directory
    try:
        rag_config = RagConfig.from_yaml(config_dir / "rag_config.yaml")
        persist_dir = Path(rag_config.chroma.persist_dir).expanduser()
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Configuration error: {e}")
        return 1

    # Confirm deletion
    if not force:
        print(f"\n⚠️  WARNING: This will delete the '{collection_name}' collection from ChromaDB.")
        print(f"   Persist directory: {persist_dir}")
        response = input("\nAre you sure? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return 0

    # Delete collection
    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
        client.delete_collection(collection_name)
        print(f"\n✅ Successfully deleted collection: {collection_name}")
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generic RAG ingestion runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available configs
  uv run python -m elt_llm_ingest.runner --list

  # Ingest DAMA-DMBOK
  uv run python -m elt_llm_ingest.runner --cfg dama_dmbok

  # Ingest with verbose output
  uv run python -m elt_llm_ingest.runner --cfg dama_dmbok -v

  # Ingest without rebuilding (append mode)
  uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --no-rebuild

  # Delete DAMA-DMBOK collection
  uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete

  # Delete without confirmation
  uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --delete -f
        """,
    )
    parser.add_argument(
        "--cfg",
        type=str,
        help="Config name (without .yaml extension), e.g., 'dama_dmbok'",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available configurations",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the collection instead of ingesting",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Don't rebuild the collection (append mode, only for ingest)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Skip confirmation prompt (only for delete)",
    )

    args = parser.parse_args()

    # List mode
    if args.list:
        return list_configs()

    # Require --cfg for ingest/delete operations
    if not args.cfg:
        print("❌ Error: --cfg is required (or use --list to see available configs)")
        parser.print_help()
        return 1

    # Delete mode
    if args.delete:
        return delete(args.cfg, force=args.force)

    # Ingest mode
    return ingest(args.cfg, verbose=args.verbose, no_rebuild=args.no_rebuild)


if __name__ == "__main__":
    sys.exit(main())
