"""Configuration management for RAG settings."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ChromaConfig:
    """ChromaDB configuration.

    Attributes:
        persist_dir: Directory for persistent storage.
        tenant: Chroma tenant name.
        database: Chroma database name.
    """

    persist_dir: str = "./chroma_db"
    tenant: str = "default_tenant"
    database: str = "default_database"


@dataclass
class OllamaConfig:
    """Ollama configuration.

    Attributes:
        base_url: Ollama server base URL.
        embedding_model: Name of the embedding model.
        llm_model: Name of the LLM model.
        embed_batch_size: Batch size for embeddings.
        context_window: Context window size for LLM.
        request_timeout: Request timeout in seconds.
    """

    base_url: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    llm_model: str = "llama3.2"
    embed_batch_size: int = 10
    context_window: int = 4096
    request_timeout: float = 60.0


@dataclass
class ChunkingConfig:
    """Document chunking configuration.

    Attributes:
        strategy: Chunking strategy ("sentence" or "semantic").
        chunk_size: Maximum characters per chunk.
        chunk_overlap: Overlap between consecutive chunks.
        sentence_split_threshold: Threshold for semantic splitting.
    """

    strategy: str = "sentence"
    chunk_size: int = 1024
    chunk_overlap: int = 200
    sentence_split_threshold: float = 0.5


@dataclass
class QueryConfig:
    """Query configuration.

    Attributes:
        similarity_top_k: Number of similar chunks to retrieve.
        system_prompt: Optional system prompt for the LLM.
    """

    similarity_top_k: int = 5
    system_prompt: str | None = None


@dataclass
class RagConfig:
    """Root RAG configuration.

    Attributes:
        chroma: ChromaDB configuration.
        ollama: Ollama configuration.
        chunking: Chunking configuration.
        query: Query configuration.
    """

    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    query: QueryConfig = field(default_factory=QueryConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RagConfig":
        """Create RagConfig from a dictionary.

        Args:
            data: Dictionary with configuration.

        Returns:
            RagConfig instance.
        """
        chroma_data = data.get("chroma", {})
        ollama_data = data.get("ollama", {})
        chunking_data = data.get("chunking", {})
        query_data = data.get("query", {})

        return cls(
            chroma=ChromaConfig(
                persist_dir=chroma_data.get("persist_dir", "./chroma_db"),
                tenant=chroma_data.get("tenant", "default_tenant"),
                database=chroma_data.get("database", "default_database"),
            ),
            ollama=OllamaConfig(
                base_url=ollama_data.get("base_url", "http://localhost:11434"),
                embedding_model=ollama_data.get("embedding_model", "nomic-embed-text"),
                llm_model=ollama_data.get("llm_model", "llama3.2"),
                embed_batch_size=ollama_data.get("embed_batch_size", 10),
                context_window=ollama_data.get("context_window", 4096),
                request_timeout=ollama_data.get("request_timeout", 60.0),
            ),
            chunking=ChunkingConfig(
                strategy=chunking_data.get("strategy", "sentence"),
                chunk_size=chunking_data.get("chunk_size", 1024),
                chunk_overlap=chunking_data.get("chunk_overlap", 200),
                sentence_split_threshold=chunking_data.get("sentence_split_threshold", 0.5),
            ),
            query=QueryConfig(
                similarity_top_k=query_data.get("similarity_top_k", 5),
                system_prompt=query_data.get("system_prompt"),
            ),
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RagConfig":
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file.

        Returns:
            RagConfig instance.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If config is invalid.
        """
        config_path = Path(path).expanduser()

        if not config_path.exists():
            logger.error("Configuration file not found: %s", config_path)
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        logger.info("Loading configuration from: %s", config_path)

        with open(config_path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            logger.error("Configuration must be a YAML dictionary")
            raise ValueError("Configuration must be a YAML dictionary")

        return cls.from_dict(data)

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary.

        Returns:
            Dictionary representation of the configuration.
        """
        return {
            "chroma": {
                "persist_dir": str(self.chroma.persist_dir),
                "tenant": self.chroma.tenant,
                "database": self.chroma.database,
            },
            "ollama": {
                "base_url": self.ollama.base_url,
                "embedding_model": self.ollama.embedding_model,
                "llm_model": self.ollama.llm_model,
                "embed_batch_size": self.ollama.embed_batch_size,
                "context_window": self.ollama.context_window,
                "request_timeout": self.ollama.request_timeout,
            },
            "chunking": {
                "strategy": self.chunking.strategy,
                "chunk_size": self.chunking.chunk_size,
                "chunk_overlap": self.chunking.chunk_overlap,
                "sentence_split_threshold": self.chunking.sentence_split_threshold,
            },
            "query": {
                "similarity_top_k": self.query.similarity_top_k,
                "system_prompt": self.query.system_prompt,
            },
        }


def load_config(path: str | Path) -> RagConfig:
    """Load configuration from a YAML file.

    Convenience function for loading configuration.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        RagConfig instance.
    """
    return RagConfig.from_yaml(path)
