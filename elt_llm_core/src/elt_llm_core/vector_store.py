"""ChromaDB vector store management with tenant/database/collection support."""

from __future__ import annotations

import logging
from dataclasses import dataclass
import os
from pathlib import Path

import chromadb
from llama_index.core import StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore

logger = logging.getLogger(__name__)


@dataclass
class ChromaConfig:
    """ChromaDB configuration.

    Attributes:
        persist_dir: Directory for persistent storage.
        tenant: Chroma tenant name (default: "default_tenant").
        database: Chroma database name (default: "default_database").
    """

    persist_dir: str | Path
    tenant: str = "default_tenant"
    database: str = "default_database"

    def __post_init__(self) -> None:
        """Convert persist_dir to Path."""
        if isinstance(self.persist_dir, str):
            self.persist_dir = Path(self.persist_dir).expanduser()


def create_chroma_client(config: ChromaConfig) -> chromadb.ClientAPI:
    """Create a ChromaDB client with tenant and database.

    Args:
        config: ChromaDB configuration.

    Returns:
        ChromaDB client API instance.
    """
    env_dir = os.environ.get("RAG_CHROMA_DIR")
    if env_dir:
        persist_path = Path(env_dir).expanduser()
    else:
        persist_path = Path(config.persist_dir).expanduser()
    persist_path.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Creating ChromaDB client: persist_dir=%s, tenant=%s, database=%s",
        persist_path,
        config.tenant,
        config.database,
    )

    # Create client
    client = chromadb.PersistentClient(path=str(persist_path))

    # Set tenant and database if supported
    # Note: PersistentClient doesn't support tenant/database in older versions
    # For now, we use them as logical grouping in collection names

    logger.info("ChromaDB client created successfully")
    return client


def get_or_create_collection(
    client: chromadb.ClientAPI,
    collection_name: str,
    metadata: dict | None = None,
) -> chromadb.Collection:
    """Get or create a Chroma collection.

    Args:
        client: ChromaDB client.
        collection_name: Name of the collection.
        metadata: Optional metadata for the collection.

    Returns:
        Chroma collection instance.
    """
    logger.info("Getting or creating collection: %s", collection_name)

    try:
        # Try to get existing collection
        collection = client.get_collection(name=collection_name)
        logger.debug("Collection '%s' already exists", collection_name)
    except Exception:
        # Create new collection
        collection = client.create_collection(
            name=collection_name,
            metadata=metadata,
        )
        logger.debug("Created new collection '%s'", collection_name)

    return collection


def get_docstore_path(config: "ChromaConfig", collection_name: str) -> Path:
    """Get the path where a collection's docstore is persisted.

    The docstore lives alongside the ChromaDB data and enables BM25 hybrid search.

    Args:
        config: ChromaDB configuration (used to locate the persist directory).
        collection_name: Name of the collection.

    Returns:
        Path to the docstore directory for this collection.
    """
    env_dir = os.environ.get("RAG_CHROMA_DIR")
    base = Path(env_dir).expanduser() if env_dir else Path(config.persist_dir).expanduser()
    return base / "docstores" / collection_name


def create_storage_context(
    client: chromadb.ClientAPI,
    collection_name: str,
    metadata: dict | None = None,
    include_docstore: bool = False,
) -> StorageContext:
    """Create a LlamaIndex StorageContext with Chroma vector store.

    Args:
        client: ChromaDB client.
        collection_name: Name of the collection.
        metadata: Optional metadata for the collection.
        include_docstore: If True, attach a SimpleDocumentStore so nodes are
            persisted for BM25 hybrid search during ingestion.

    Returns:
        StorageContext configured with Chroma vector store.
    """
    collection = get_or_create_collection(client, collection_name, metadata)
    vector_store = ChromaVectorStore(chroma_collection=collection)

    if include_docstore:
        from llama_index.core.storage.docstore import SimpleDocumentStore
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store,
            docstore=SimpleDocumentStore(),
        )
    else:
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

    logger.info("StorageContext created for collection '%s'", collection_name)
    return storage_context


def get_collection_count(
    client: chromadb.ClientAPI,
    collection_name: str,
) -> int:
    """Get the number of documents in a collection.

    Args:
        client: ChromaDB client.
        collection_name: Name of the collection.

    Returns:
        Number of documents in the collection.
    """
    try:
        collection = client.get_collection(name=collection_name)
        return collection.count()
    except Exception:
        return 0


def delete_collection(
    client: chromadb.ClientAPI,
    collection_name: str,
) -> None:
    """Delete a collection.

    Args:
        client: ChromaDB client.
        collection_name: Name of the collection to delete.
    """
    logger.info("Deleting collection: %s", collection_name)
    try:
        client.delete_collection(name=collection_name)
        logger.debug("Collection '%s' deleted", collection_name)
    except Exception as e:
        logger.warning("Failed to delete collection '%s': %s", collection_name, e)


def list_collections(client: chromadb.ClientAPI) -> list[str]:
    """List all collections.

    Args:
        client: ChromaDB client.

    Returns:
        List of collection names.
    """
    collections = client.list_collections()
    return [c.name for c in collections]


def list_collections_by_prefix(client: chromadb.ClientAPI, prefix: str) -> list[str]:
    """List all collection names that start with the given prefix.

    Matches '{prefix}_*' so 'fa_leanix' matches 'fa_leanix_overview',
    'fa_leanix_relationships', etc.

    Args:
        client: ChromaDB client.
        prefix: Collection name prefix (without trailing underscore).

    Returns:
        Sorted list of matching collection names.
    """
    match = prefix + "_"
    return sorted(name for name in list_collections(client) if name.startswith(match))
