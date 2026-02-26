"""Generic RAG ingestion runner.

Usage:
    uv run python -m elt_llm_ingest.runner --cfg <config_name> [-v] [--no-rebuild]
    uv run python -m elt_llm_ingest.runner --cfg <config_name> --delete [-f]
    uv run python -m elt_llm_ingest.runner --list
    uv run python -m elt_llm_ingest.runner --status [-v]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import chromadb
import yaml

from elt_llm_core.config import ChunkingConfig, RagConfig
from elt_llm_ingest.ingest import IngestConfig, run_ingestion
from elt_llm_ingest.preprocessor import PreprocessorConfig


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


def _docstore_node_count(persist_dir: Path, collection_name: str) -> int | None:
    """Return the number of nodes in a collection's BM25 docstore, or None if absent."""
    import json
    ds = persist_dir / "docstores" / collection_name / "docstore.json"
    if not ds.exists():
        return None
    try:
        data = json.loads(ds.read_text())
        return len(data.get("docstore/data", {}))
    except Exception:
        return None


def status(verbose: bool = False) -> int:
    """Show status of all ChromaDB collections and their BM25 docstores.

    Args:
        verbose: Show detailed information including metadata.

    Returns:
        Exit code (0 for success).
    """
    config_dir = get_config_dir()

    # Load RAG config to get persist directory
    try:
        rag_config = RagConfig.from_yaml(config_dir / "rag_config.yaml")
        persist_dir = Path(rag_config.chroma.persist_dir).expanduser()
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Configuration error: {e}")
        return 1

    # Connect to ChromaDB
    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
    except Exception as e:
        print(f"❌ Failed to connect to ChromaDB: {e}")
        return 1

    # Get all collections
    collections = client.list_collections()

    if not collections:
        print("\n=== ChromaDB Status ===\n")
        print(f"Persist directory: {persist_dir}")
        print("No collections found.\n")
        return 0

    print("\n=== ChromaDB Status ===\n")
    print(f"Persist directory: {persist_dir}\n")

    if verbose:
        print(f"{'Collection Name':<35} {'Chunks':>7}  {'BM25 nodes':>10}  {'BM25':>5}  Metadata")
        print("-" * 90)
    else:
        print(f"{'Collection Name':<35} {'Chunks':>7}  {'BM25 nodes':>10}  {'BM25':>5}")
        print("-" * 62)

    total_docs = 0
    missing_docstores = []

    for collection in sorted(collections, key=lambda c: c.name):
        try:
            count = collection.count()
            total_docs += count

            # Internal tracking collection — skip docstore check
            is_internal = collection.name == "file_hashes"

            if is_internal:
                bm25_str = "n/a"
                bm25_nodes_str = "-"
            else:
                nodes = _docstore_node_count(persist_dir, collection.name)
                if nodes is None:
                    bm25_str = "❌"
                    bm25_nodes_str = "-"
                    missing_docstores.append(collection.name)
                elif nodes == 0:
                    bm25_str = "⚠️"
                    bm25_nodes_str = "0"
                else:
                    bm25_str = "✅"
                    bm25_nodes_str = str(nodes)

            if verbose:
                metadata = collection.metadata or {}
                metadata_str = str(metadata) if metadata else "-"
                print(f"{collection.name:<35} {count:>7}  {bm25_nodes_str:>10}  {bm25_str:>5}  {metadata_str}")
            else:
                print(f"{collection.name:<35} {count:>7}  {bm25_nodes_str:>10}  {bm25_str:>5}")
        except Exception as e:
            print(f"{collection.name:<35} {'ERROR':>7}  {'-':>10}  {'?':>5}  {e}")

    print()
    print(f"Total: {len(collections)} collection(s), {total_docs} chunk(s)")

    if missing_docstores:
        print(f"\n⚠️  Missing BM25 docstores (hybrid search will fall back to vector-only):")
        for name in missing_docstores:
            print(f"   - {name}")

    print()
    return 0


def ingest(config_name: str, verbose: bool = False, no_rebuild: bool = False, force: bool = False) -> int:
    """Ingest documents using the specified config.

    Args:
        config_name: Name of the config file (without .yaml extension).
        verbose: Enable verbose logging.
        no_rebuild: Don't rebuild the collection.
        force: Force re-ingestion regardless of file changes.

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

    # Check for batch config
    from elt_llm_ingest.batch_loader import load_batch_config
    try:
        batch_configs = load_batch_config(ingest_path)
        if batch_configs:
            print(f"📦 Detected batch configuration: {len(batch_configs)} configs")
            failed = 0
            for cfg in batch_configs:
                # Remove extension if present
                cfg_name = Path(cfg).stem
                print(f"\n🚀 Running ingestion for: {cfg_name}")
                # Recursively call ingest for each config
                if ingest(cfg_name, verbose, no_rebuild, force) != 0:
                    failed += 1
            
            if failed > 0:
                print(f"\n❌ Batch ingestion completed with {failed} failures")
                return 1
            print("\n✅ Batch ingestion completed successfully")
            return 0
    except Exception as e:
        # Not a batch config or error reading it, proceed as single config
        pass

    with open(ingest_path) as f:
        ingest_data = yaml.safe_load(f)

    # Detect split mode (collection_prefix) vs single-collection mode
    collection_prefix = ingest_data.get("collection_prefix")
    collection_name = ingest_data.get("collection_name")

    if collection_prefix and collection_name:
        print("❌ Error: ingest config must not set both 'collection_prefix' and 'collection_name'")
        return 1
    if not collection_prefix and not collection_name:
        print("❌ Error: ingest config must set either 'collection_prefix' (split mode) or 'collection_name'")
        return 1

    # Preprocessor config
    preprocessor_config = None
    if "preprocessor" in ingest_data:
        preprocessor_config = PreprocessorConfig.from_dict(ingest_data["preprocessor"])
        # Propagate collection_prefix into the preprocessor so split mode works
        if collection_prefix and preprocessor_config.collection_prefix is None:
            preprocessor_config.collection_prefix = collection_prefix

    # Per-config chunking override (optional)
    chunking_override = None
    if "chunking" in ingest_data:
        cd = ingest_data["chunking"]
        chunking_override = ChunkingConfig(
            strategy=cd.get("strategy", "sentence"),
            chunk_size=cd.get("chunk_size", 1024),
            chunk_overlap=cd.get("chunk_overlap", 200),
        )

    ingest_config = IngestConfig(
        collection_name=collection_name,
        collection_prefix=collection_prefix,
        file_paths=ingest_data.get("file_paths", []),
        metadata=ingest_data.get("metadata"),
        rebuild=not no_rebuild,
        force=force,
        preprocessor=preprocessor_config,
        chunking_override=chunking_override,
    )

    try:
        _, node_count = run_ingestion(ingest_config, rag_config)

        if node_count > 0:
            if collection_prefix:
                print(f"\n✅ Split ingestion complete: {node_count} total chunks indexed across collections prefixed '{collection_prefix}_*'")
            else:
                print(f"\n✅ Ingestion complete: {node_count} chunks indexed")
        else:
            print(f"\n✅ No changes detected - collection(s) unchanged")
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

    collection_prefix = ingest_data.get("collection_prefix")
    collection_name = ingest_data.get("collection_name")

    # Load RAG config to get persist directory
    try:
        rag_config = RagConfig.from_yaml(config_dir / "rag_config.yaml")
        persist_dir = Path(rag_config.chroma.persist_dir).expanduser()
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Configuration error: {e}")
        return 1

    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
    except Exception as e:
        print(f"❌ Failed to connect to ChromaDB: {e}")
        return 1

    # ── Split mode: delete all collections matching the prefix ─────────────
    if collection_prefix:
        all_collections = client.list_collections()
        matching = [c for c in all_collections if c.name.startswith(f"{collection_prefix}_")]
        if not matching:
            print(f"\n⚠️  No collections found with prefix '{collection_prefix}_'")
            return 0

        collection_names_to_delete = [c.name for c in matching]
        if not force:
            print(f"\n⚠️  WARNING: This will delete {len(collection_names_to_delete)} collection(s):")
            for name in sorted(collection_names_to_delete):
                print(f"   - {name}")
            print(f"\n   Persist directory: {persist_dir}")
            response = input("\nAre you sure? (y/N): ").strip().lower()
            if response not in ("y", "yes"):
                print("Aborted.")
                return 0

        for name in collection_names_to_delete:
            try:
                client.delete_collection(name)
                print(f"  ✅ Deleted: {name}")
            except Exception as e:
                print(f"  ❌ Failed to delete {name}: {e}")
        return 0

    # ── Single-collection mode ─────────────────────────────────────────────
    if not force:
        print(f"\n⚠️  WARNING: This will delete the '{collection_name}' collection from ChromaDB.")
        print(f"   Persist directory: {persist_dir}")
        response = input("\nAre you sure? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            print("Aborted.")
            return 0

    try:
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

  # Show collection status
  uv run python -m elt_llm_ingest.runner --status

  # Show collection status with verbose metadata
  uv run python -m elt_llm_ingest.runner --status -v

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
        help="For delete: skip confirmation; for ingest: bypass hash checking and re-ingest all files",
    )
    parser.add_argument(
        "--status",
        "-s",
        action="store_true",
        help="Show status of all ChromaDB collections",
    )

    args = parser.parse_args()

    # Status mode
    if args.status:
        return status(verbose=args.verbose)

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
    return ingest(args.cfg, verbose=args.verbose, no_rebuild=args.no_rebuild, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
