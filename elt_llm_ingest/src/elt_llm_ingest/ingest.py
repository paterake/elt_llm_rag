"""Document ingestion pipeline using LlamaIndex."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from llama_index.core import (
    Document,
    Settings,
    VectorStoreIndex,
)
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import FlatReader

from elt_llm_core.config import ChunkingConfig, RagConfig
from elt_llm_core.models import create_embedding_model
from elt_llm_core.vector_store import (
    ChromaConfig,
    create_chroma_client,
    create_storage_context,
    delete_collection,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestConfig:
    """Ingestion configuration.

    Attributes:
        collection_name: Name of the Chroma collection.
        file_paths: List of file paths to ingest.
        metadata: Metadata to attach to all documents.
        rebuild: Whether to rebuild (delete and recreate) the collection.
    """

    collection_name: str
    file_paths: list[str]
    metadata: dict[str, Any] | None = None
    rebuild: bool = True


def load_documents(
    file_paths: list[str],
    metadata: dict[str, Any] | None = None,
) -> list[Document]:
    """Load documents from file paths.

    Supports multiple file formats via LlamaIndex readers:
    - PDF (.pdf)
    - Word (.docx)
    - Text (.txt)
    - HTML (.html)
    - And more...

    Args:
        file_paths: List of file paths to load.
        metadata: Optional metadata to attach to all documents.

    Returns:
        List of LlamaIndex Document objects.
    """
    logger.info("Loading %d documents", len(file_paths))

    documents: list[Document] = []
    reader = FlatReader()

    for file_path in file_paths:
        path = Path(file_path).expanduser()
        logger.debug("Loading document: %s", path)

        if not path.exists():
            logger.warning("File not found, skipping: %s", path)
            continue

        try:
            docs = reader.load_data(path)
            for doc in docs:
                if metadata:
                    doc.metadata.update(metadata)
                doc.metadata["source_file"] = str(path)
            documents.extend(docs)
            logger.info("Loaded document: %s (%d chars)", path, len(doc.text or ""))
        except Exception as e:
            logger.error("Failed to load %s: %s", path, e)

    logger.info("Loaded %d documents total", len(documents))
    return documents


def build_index(
    documents: list[Document],
    rag_config: RagConfig,
    collection_name: str,
    rebuild: bool = True,
) -> VectorStoreIndex:
    """Build a vector index from documents.

    Args:
        documents: List of Document objects to index.
        rag_config: RAG configuration.
        collection_name: Name of the Chroma collection.
        rebuild: Whether to rebuild the collection.

    Returns:
        VectorStoreIndex containing the embedded documents.
    """
    logger.info(
        "Building index from %d documents (collection=%s, rebuild=%s)",
        len(documents),
        collection_name,
        rebuild,
    )

    # Create Chroma client
    chroma_client = create_chroma_client(rag_config.chroma)

    # Delete existing collection if rebuild
    if rebuild:
        delete_collection(chroma_client, collection_name)

    # Create storage context
    storage_context = create_storage_context(
        chroma_client,
        collection_name,
        metadata={"description": f"Collection: {collection_name}"},
    )

    # Set embedding model
    embed_model = create_embedding_model(rag_config.ollama)
    Settings.embed_model = embed_model

    # Create transformations based on strategy
    chunking = rag_config.chunking
    if chunking.strategy == "sentence":
        transformations = [
            SentenceSplitter(
                chunk_size=chunking.chunk_size,
                chunk_overlap=chunking.chunk_overlap,
            )
        ]
    else:
        # For semantic chunking, we'd use a different splitter
        transformations = [
            SentenceSplitter(
                chunk_size=chunking.chunk_size,
                chunk_overlap=chunking.chunk_overlap,
            )
        ]

    # Create index
    index = VectorStoreIndex.from_documents(
        documents=documents,
        storage_context=storage_context,
        transformations=transformations,
        show_progress=True,
    )

    logger.info("Index built successfully with %d documents", len(documents))
    return index


def run_ingestion(
    ingest_config: IngestConfig,
    rag_config: RagConfig,
) -> VectorStoreIndex:
    """Run the complete ingestion pipeline.

    Args:
        ingest_config: Ingestion configuration.
        rag_config: RAG configuration.

    Returns:
        VectorStoreIndex containing the ingested documents.

    Raises:
        ValueError: If no documents were loaded.
    """
    logger.info("Starting ingestion pipeline for collection: %s", ingest_config.collection_name)

    # Load documents
    documents = load_documents(
        file_paths=ingest_config.file_paths,
        metadata=ingest_config.metadata,
    )

    if not documents:
        raise ValueError("No documents were loaded. Check file paths.")

    # Build index
    index = build_index(
        documents=documents,
        rag_config=rag_config,
        collection_name=ingest_config.collection_name,
        rebuild=ingest_config.rebuild,
    )

    logger.info("Ingestion pipeline complete")
    return index


def ingest_from_config(
    config_path: str | Path,
    rag_config: RagConfig | None = None,
) -> VectorStoreIndex:
    """Run ingestion from a configuration file.

    Args:
        config_path: Path to the ingestion config YAML file.
        rag_config: Optional RAG config (loads from same path if not provided).

    Returns:
        VectorStoreIndex containing the ingested documents.
    """
    config_path = Path(config_path).expanduser()

    # Load ingestion config
    with open(config_path) as f:
        data = __import__("yaml").safe_load(f)

    ingest_config = IngestConfig(
        collection_name=data["collection_name"],
        file_paths=data.get("file_paths", []),
        metadata=data.get("metadata"),
        rebuild=data.get("rebuild", True),
    )

    # Load RAG config if not provided
    if rag_config is None:
        rag_config_path = data.get("rag_config", config_path)
        rag_config = RagConfig.from_yaml(rag_config_path)

    return run_ingestion(ingest_config, rag_config)
