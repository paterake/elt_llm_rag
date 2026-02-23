"""CLI entry point for document ingestion."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import yaml

from elt_llm_core.config import RagConfig
from elt_llm_ingest.ingest import IngestConfig, run_ingestion


def get_config_dir() -> Path:
    """Get the config directory path."""
    return Path(__file__).parent.parent / "config"


def main() -> None:
    """CLI entry point for ingestion."""
    parser = argparse.ArgumentParser(description="Ingest documents into RAG index")
    parser.add_argument(
        "--config",
        "-c",
        type=str,
        help="Path to ingestion configuration YAML file (e.g., config/dama_dmbok.yaml)",
    )
    parser.add_argument(
        "--rag-config",
        "-r",
        type=str,
        default=None,
        help="Path to RAG configuration YAML file (default: config/rag_config.yaml)",
    )
    parser.add_argument(
        "--collection",
        type=str,
        help="Override collection name from config",
    )
    parser.add_argument(
        "--no-rebuild",
        action="store_true",
        help="Don't rebuild the collection (append mode)",
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
        help="List available ingestion configs",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    config_dir = get_config_dir()

    # List configs mode
    if args.list:
        print("\nAvailable ingestion configs:\n")
        for cfg in sorted(config_dir.glob("*.yaml")):
            if cfg.name != "rag_config.yaml":
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
        # Try config directory
        alt_path = config_dir / config_path.name
        if alt_path.exists():
            config_path = alt_path

    # Load RAG configuration
    rag_config_path = args.rag_config
    if rag_config_path is None:
        rag_config_path = config_dir / "rag_config.yaml"
    else:
        rag_config_path = Path(rag_config_path).expanduser()

    try:
        rag_config = RagConfig.from_yaml(rag_config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"RAG configuration error: {e}")
        raise SystemExit(1)

    # Load ingestion configuration
    with open(config_path) as f:
        ingest_data = yaml.safe_load(f)

    # Create ingestion config
    ingest_config = IngestConfig(
        collection_name=args.collection or ingest_data["collection_name"],
        file_paths=ingest_data.get("file_paths", []),
        metadata=ingest_data.get("metadata"),
        rebuild=not args.no_rebuild,
    )

    try:
        index = run_ingestion(ingest_config, rag_config)
        doc_count = len(index.docstore.docs) if index.docstore else 0
        print(f"\nIngestion complete: {doc_count} chunks indexed")
    except ValueError as e:
        print(f"Error: {e}")
        raise SystemExit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
