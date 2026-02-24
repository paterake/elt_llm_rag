"""Document ingestion pipeline using LlamaIndex."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

from llama_index.core import (
    Document,
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.storage.docstore import SimpleDocumentStore

from elt_llm_core.config import ChunkingConfig, RagConfig
from elt_llm_core.models import create_embedding_model
from elt_llm_core.vector_store import (
    ChromaConfig,
    create_chroma_client,
    create_storage_context,
    delete_collection,
    get_docstore_path,
)
from elt_llm_ingest.file_hash import (
    FILE_HASH_COLLECTION,
    get_collection_file_count,
    is_file_changed,
    store_file_hash,
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
        force: Whether to force re-ingestion regardless of file changes.
    """

    collection_name: str
    file_paths: list[str]
    metadata: dict[str, Any] | None = None
    rebuild: bool = True
    force: bool = False


def load_documents(
    file_paths: list[str],
    metadata: dict[str, Any] | None = None,
    chroma_client: chromadb.ClientAPI | None = None,
    collection_name: str | None = None,
    force: bool = False,
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
        chroma_client: Optional ChromaDB client for hash checking.
        collection_name: Optional collection name for hash tracking.
        force: If True, skip hash checking and load all files.

    Returns:
        List of LlamaIndex Document objects.
    """
    logger.info("Loading %d documents", len(file_paths))

    documents: list[Document] = []
    files_to_process: list[str] = []

    # Filter files by change detection if not in force mode
    if chroma_client and collection_name and not force:
        for file_path in file_paths:
            path = Path(file_path).expanduser()
            if not path.exists():
                env_dir = os.environ.get("RAG_DOCS_DIR")
                if env_dir:
                    alt_path = Path(env_dir).expanduser() / Path(file_path).name
                    if alt_path.exists():
                        path = alt_path
                    else:
                        logger.warning("File not found at %s and override %s", path, alt_path)
                        continue
                else:
                    logger.warning("File not found: %s", path)
                    continue

            if is_file_changed(chroma_client, str(path), collection_name):
                files_to_process.append(str(path))
            else:
                logger.info("Skipping unchanged file: %s", path)
    else:
        files_to_process = [str(Path(fp).expanduser()) for fp in file_paths]

    if not files_to_process:
        logger.info("No files to process (all unchanged)")
        return documents

    logger.info("Processing %d/%d files (changed or new)", len(files_to_process), len(file_paths))

    for file_path in files_to_process:
        path = Path(file_path)
        logger.debug("Loading document: %s", path)

        try:
            reader = SimpleDirectoryReader(input_files=[str(path)])
            docs = reader.load_data()
            for doc in docs:
                if metadata:
                    doc.metadata.update(metadata)
                doc.metadata["source_file"] = str(path)
            documents.extend(docs)
            logger.info("Loaded document: %s (%d chars)", path, len(doc.text or ""))

            # Store hash after successful load
            if chroma_client and collection_name:
                store_file_hash(chroma_client, str(path), collection_name)
        except Exception as e:
            logger.error("Failed to load %s: %s", path, e)

    logger.info("Loaded %d documents total", len(documents))
    return documents


def build_index(
    documents: list[Document],
    rag_config: RagConfig,
    collection_name: str,
    rebuild: bool = True,
) -> tuple[VectorStoreIndex, int]:
    """Build a vector index from documents.

    Args:
        documents: List of Document objects to index.
        rag_config: RAG configuration.
        collection_name: Name of the Chroma collection.
        rebuild: Whether to rebuild the collection.

    Returns:
        Tuple of (VectorStoreIndex, node_count) where node_count is the number
        of chunks stored.
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

    # Set embedding model
    embed_model = create_embedding_model(rag_config.ollama)
    Settings.embed_model = embed_model

    # Step 1: Chunk documents into nodes.
    # NOTE: VectorStoreIndex.from_documents() with ChromaDB skips the docstore
    # (ChromaDB is the authoritative node store). We run the pipeline explicitly
    # so we have the nodes to save separately for BM25.
    chunking = rag_config.chunking
    splitter = SentenceSplitter(
        chunk_size=chunking.chunk_size,
        chunk_overlap=chunking.chunk_overlap,
    )
    nodes = IngestionPipeline(transformations=[splitter]).run(
        documents=documents,
        show_progress=True,
    )
    logger.info("Created %d nodes from %d documents", len(nodes), len(documents))

    # Step 2: Persist nodes to a SimpleDocumentStore for BM25 hybrid search.
    docstore = SimpleDocumentStore()
    docstore.add_documents(nodes)
    docstore_path = get_docstore_path(rag_config.chroma, collection_name)
    docstore_path.mkdir(parents=True, exist_ok=True)
    StorageContext.from_defaults(docstore=docstore).persist(persist_dir=str(docstore_path))
    logger.info("Docstore persisted: %s (%d nodes)", docstore_path, len(nodes))

    # Step 3: Embed nodes and store vectors in ChromaDB.
    storage_context = create_storage_context(
        chroma_client,
        collection_name,
        metadata={"description": f"Collection: {collection_name}"},
    )
    index = VectorStoreIndex(
        nodes=nodes,
        storage_context=storage_context,
        show_progress=True,
    )

    logger.info("Index built successfully with %d nodes", len(nodes))
    return index, len(nodes)


def run_ingestion(
    ingest_config: IngestConfig,
    rag_config: RagConfig,
) -> tuple[VectorStoreIndex, int]:
    """Run the complete ingestion pipeline.

    Args:
        ingest_config: Ingestion configuration.
        rag_config: RAG configuration.

    Returns:
        Tuple of (VectorStoreIndex, nodes_indexed) where nodes_indexed is 0
        when all files were unchanged and no rebuild was needed.

    Raises:
        ValueError: If no documents were loaded.
    """
    logger.info("Starting ingestion pipeline for collection: %s", ingest_config.collection_name)

    # Create Chroma client for hash tracking
    chroma_client = create_chroma_client(rag_config.chroma)

    # If rebuilding, clear file hashes for this collection
    if ingest_config.rebuild:
        from elt_llm_ingest.file_hash import remove_file_hashes
        remove_file_hashes(
            chroma_client,
            ingest_config.file_paths,
            ingest_config.collection_name,
        )
        logger.info("Cleared file hashes for rebuild")

    # Load documents (with hash checking if not force mode)
    documents = load_documents(
        file_paths=ingest_config.file_paths,
        metadata=ingest_config.metadata,
        chroma_client=chroma_client,
        collection_name=ingest_config.collection_name,
        force=ingest_config.force,
    )

    # If no documents and not rebuilding, all files were unchanged - this is OK
    if not documents and not ingest_config.rebuild:
        logger.info("All files unchanged, no ingestion needed")
        # Return existing index by loading from storage context
        embed_model = create_embedding_model(rag_config.ollama)
        Settings.embed_model = embed_model
        
        storage_context = create_storage_context(
            chroma_client,
            ingest_config.collection_name,
            metadata={"description": f"Collection: {ingest_config.collection_name}"},
        )
        from llama_index.core import VectorStoreIndex
        index = VectorStoreIndex.from_vector_store(
            storage_context.vector_store,
        )
        logger.info("Loaded existing index with unchanged documents")
        return index, 0

    if not documents:
        raise ValueError("No documents were loaded. Check file paths.")

    # Build index
    index, node_count = build_index(
        documents=documents,
        rag_config=rag_config,
        collection_name=ingest_config.collection_name,
        rebuild=ingest_config.rebuild,
    )

    logger.info("Ingestion pipeline complete")
    return index, node_count


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

    index, _ = run_ingestion(ingest_config, rag_config)
    return index
