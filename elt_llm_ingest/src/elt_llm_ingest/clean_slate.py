"""Clean RAG data from ChromaDB and BM25 docstores.

Usage:
    # Delete ALL collections and docstores (full wipe)
    uv run python -m elt_llm_ingest.clean_slate

    # Delete only collections whose names start with a given prefix
    uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix

    # Multiple prefixes
    uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix_dat_enterprise_conceptual_model --prefix fa_leanix_global_inventory

    # Skip confirmation prompt
    uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix -f
"""

import argparse
import shutil
import sys
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

from elt_llm_core.config import RagConfig


def _load_config() -> tuple[RagConfig, Path]:
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    config_path = repo_root / "elt_llm_ingest" / "config" / "rag_config.yaml"
    if not config_path.exists():
        logger.error(f"❌ Config not found at {config_path}")
        sys.exit(1)
    rag_config = RagConfig.from_yaml(config_path)
    persist_dir = Path(rag_config.chroma.persist_dir)
    if not persist_dir.is_absolute():
        persist_dir = (config_path.parent / persist_dir).resolve()
    return rag_config, persist_dir


def delete_by_prefix(prefixes: list[str], persist_dir: Path, force: bool) -> int:
    """Delete all ChromaDB collections and BM25 docstores matching any of the given prefixes."""
    import chromadb

    try:
        client = chromadb.PersistentClient(path=str(persist_dir))
    except Exception as e:
        logger.error(f"❌ Failed to connect to ChromaDB: {e}")
        return 1

    all_collections = client.list_collections()
    to_delete = [
        c for c in all_collections
        if any(c.name.startswith(f"{p}_") or c.name == p for p in prefixes)
    ]

    if not to_delete:
        logger.info(f"⚠️  No collections found matching prefixes: {prefixes}")
        return 0

    logger.info(f"\n🗑️  Collections to delete ({len(to_delete)}):")
    for c in sorted(to_delete, key=lambda x: x.name):
        logger.info(f"   - {c.name}")

    if not force:
        response = input("\nAre you sure? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            logger.info("Aborted.")
            return 0

    errors = 0
    for c in to_delete:
        name = c.name
        # 1. Delete ChromaDB collection
        try:
            client.delete_collection(name)
            logger.info(f"  ✅ Deleted ChromaDB collection: {name}")
        except Exception as e:
            logger.error(f"  ❌ Failed to delete collection {name}: {e}")
            errors += 1

        # 2. Delete BM25 docstore directory
        docstore_dir = persist_dir / "docstores" / name
        if docstore_dir.exists():
            try:
                shutil.rmtree(docstore_dir)
                logger.info(f"  ✅ Deleted BM25 docstore: {docstore_dir}")
            except Exception as e:
                logger.error(f"  ❌ Failed to delete docstore {docstore_dir}: {e}")
                errors += 1
        else:
            logger.info(f"  ℹ️  No BM25 docstore found for: {name}")

    logger.info(f"\n{'✅' if errors == 0 else '⚠️'} Done. {len(to_delete) - errors}/{len(to_delete)} deleted successfully.")
    return 1 if errors else 0


def delete_all(persist_dir: Path, force: bool) -> int:
    """Wipe the entire persist directory (ChromaDB + all docstores)."""
    logger.info(f"🗑️  Targeting ChromaDB directory: {persist_dir}")

    if not persist_dir.exists():
        logger.info("✅ Directory does not exist. Nothing to clean.")
        return 0

    if not force:
        logger.info("⚠️  WARNING: This will delete ALL collections and BM25 docstores.")
        response = input("\nAre you sure? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            logger.info("Aborted.")
            return 0

    try:
        shutil.rmtree(persist_dir)
        logger.info(f"✅ Successfully deleted {persist_dir}")
        return 0
    except Exception as e:
        logger.error(f"❌ Failed to delete directory: {e}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Clean RAG data from ChromaDB and BM25 docstores.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Wipe everything
  uv run python -m elt_llm_ingest.clean_slate

  # Delete old fa_leanix collections (and their docstores)
  uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix

  # Delete specific prefixes without confirmation
  uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix_dat_enterprise_conceptual_model -f
        """,
    )
    parser.add_argument(
        "--prefix",
        action="append",
        metavar="PREFIX",
        help="Delete only collections whose names start with PREFIX_ (can be repeated). "
             "Omit to delete everything.",
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        help="Skip confirmation prompt.",
    )

    args = parser.parse_args()
    _, persist_dir = _load_config()

    if args.prefix:
        return delete_by_prefix(args.prefix, persist_dir, force=args.force)
    else:
        return delete_all(persist_dir, force=args.force)


if __name__ == "__main__":
    sys.exit(main())
