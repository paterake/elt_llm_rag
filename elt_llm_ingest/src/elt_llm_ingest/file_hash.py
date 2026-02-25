"""File hash utilities for smart ingest with change detection."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

import chromadb
import numpy as np

logger = logging.getLogger(__name__)

# Collection name for storing file hashes
FILE_HASH_COLLECTION = "file_hashes"

# Dummy embedding dimension (we query by ID, not similarity)
EMBEDDING_DIM = 1


def compute_file_hash(file_path: str | Path) -> str:
    """Compute SHA256 hash of a file.

    Args:
        file_path: Path to the file.

    Returns:
        Hexadecimal SHA256 hash string.
    """
    file_path = Path(file_path).expanduser()
    sha256_hash = hashlib.sha256()

    with open(file_path, "rb") as f:
        # Read in chunks for large files
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)

    return sha256_hash.hexdigest()


def _get_hash_collection(
    client: chromadb.ClientAPI,
) -> chromadb.Collection:
    """Get or create the file_hashes collection.

    Args:
        client: ChromaDB client.

    Returns:
        The file_hashes collection.
    """
    try:
        collection = client.get_collection(name=FILE_HASH_COLLECTION)
        logger.debug("Using existing file_hashes collection")
    except Exception:
        collection = client.create_collection(
            name=FILE_HASH_COLLECTION,
            metadata={"description": "File hash tracking for smart ingest"},
        )
        logger.debug("Created file_hashes collection")

    return collection


def _file_path_to_id(file_path: str, collection_name: str) -> str:
    """Convert file path and collection to a unique ID for ChromaDB.

    Args:
        file_path: Path to the file.
        collection_name: Name of the target collection.

    Returns:
        Unique ID string for ChromaDB.
    """
    # Use combination of collection and path to allow same file in multiple collections
    return f"{collection_name}::{file_path}"


def get_stored_hash(
    client: chromadb.ClientAPI,
    file_path: str,
    collection_name: str,
) -> str | None:
    """Retrieve stored hash for a file.

    Args:
        client: ChromaDB client.
        file_path: Path to the file.
        collection_name: Name of the target collection.

    Returns:
        Stored hash if found, None otherwise.
    """
    doc_id = _file_path_to_id(file_path, collection_name)
    collection = _get_hash_collection(client)

    try:
        result = collection.get(ids=[doc_id])
        if result["ids"]:
            stored_hash = result["metadatas"][0].get("hash")
            logger.debug("Found stored hash for %s: %s", file_path, stored_hash[:8] if stored_hash else None)
            return stored_hash
    except Exception as e:
        logger.warning("Error retrieving hash for %s: %s", file_path, e)

    logger.debug("No stored hash found for %s", file_path)
    return None


def store_file_hash(
    client: chromadb.ClientAPI,
    file_path: str,
    collection_name: str,
    file_hash: str | None = None,
) -> None:
    """Store or update file hash in ChromaDB.

    Args:
        client: ChromaDB client.
        file_path: Path to the file.
        collection_name: Name of the target collection.
        file_hash: Optional pre-computed hash (computed if not provided).
    """
    if file_hash is None:
        file_hash = compute_file_hash(file_path)

    doc_id = _file_path_to_id(file_path, collection_name)
    collection = _get_hash_collection(client)

    # Use zero embedding (we query by ID only)
    embedding = [0.0] * EMBEDDING_DIM

    metadata = {
        "file_path": file_path,
        "hash": file_hash,
        "collection_name": collection_name,
    }

    # Check if exists - update or add
    try:
        existing = collection.get(ids=[doc_id])
        if existing["ids"]:
            collection.update(
                ids=[doc_id],
                embeddings=[embedding],
                metadatas=[metadata],
            )
            logger.debug("Updated hash for %s", file_path)
        else:
            collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                metadatas=[metadata],
            )
            logger.debug("Stored new hash for %s", file_path)
    except Exception as e:
        logger.error("Failed to store hash for %s: %s", file_path, e)


def is_file_changed(
    client: chromadb.ClientAPI,
    file_path: str,
    collection_name: str,
) -> bool:
    """Check if a file has changed since last ingestion.

    Args:
        client: ChromaDB client.
        file_path: Path to the file.
        collection_name: Name of the target collection.

    Returns:
        True if file is new or has changed, False if unchanged.
    """
    file_path = str(Path(file_path).expanduser())

    # Compute current hash
    try:
        current_hash = compute_file_hash(file_path)
    except Exception as e:
        logger.warning("Failed to compute hash for %s: %s", file_path, e)
        return True  # Assume changed if we can't hash

    # Get stored hash
    stored_hash = get_stored_hash(client, file_path, collection_name)

    if stored_hash is None:
        logger.info("New file (no stored hash): %s", file_path)
        return True

    if current_hash != stored_hash:
        logger.info("File changed: %s", file_path)
        return True

    logger.info("File unchanged: %s", file_path)
    return False


def remove_file_hashes(
    client: chromadb.ClientAPI,
    file_paths: list[str],
    collection_name: str,
) -> None:
    """Remove file hashes for a list of files.

    Args:
        client: ChromaDB client.
        file_paths: List of file paths.
        collection_name: Name of the target collection.
    """
    collection = _get_hash_collection(client)
    doc_ids = []
    for fp in file_paths:
        expanded_path = str(Path(fp).expanduser())
        doc_ids.append(_file_path_to_id(expanded_path, collection_name))

    try:
        collection.delete(ids=doc_ids)
        logger.debug("Removed %d file hashes", len(doc_ids))
    except Exception as e:
        logger.warning("Failed to remove file hashes: %s", e)


def get_collection_file_count(
    client: chromadb.ClientAPI,
    collection_name: str,
) -> int:
    """Get number of files tracked for a collection.

    Args:
        client: ChromaDB client.
        collection_name: Name of the target collection.

    Returns:
        Number of files tracked.
    """
    collection = _get_hash_collection(client)

    # Get all and filter by collection_name metadata
    try:
        results = collection.get(
            where={"collection_name": collection_name},
        )
        return len(results["ids"])
    except Exception:
        return 0
