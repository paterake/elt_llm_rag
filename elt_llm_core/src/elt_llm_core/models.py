"""Ollama embedding and LLM model configuration."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

logger = logging.getLogger(__name__)


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


def create_embedding_model(config: OllamaConfig) -> OllamaEmbedding:
    """Create an Ollama embedding model.

    Args:
        config: Ollama configuration.

    Returns:
        Configured OllamaEmbedding instance.
    """
    logger.info(
        "Creating Ollama embedding model: %s (batch_size=%d)",
        config.embedding_model,
        config.embed_batch_size,
    )

    return OllamaEmbedding(
        model_name=config.embedding_model,
        base_url=config.base_url,
        embed_batch_size=config.embed_batch_size,
    )


def create_llm_model(config: OllamaConfig) -> Ollama:
    """Create an Ollama LLM model.

    Args:
        config: Ollama configuration.

    Returns:
        Configured Ollama LLM instance.
    """
    logger.info(
        "Creating Ollama LLM model: %s (context_window=%d)",
        config.llm_model,
        config.context_window,
    )

    return Ollama(
        model=config.llm_model,
        base_url=config.base_url,
        request_timeout=config.request_timeout,
        context_window=config.context_window,
    )


def check_ollama_connection(base_url: str = "http://localhost:11434") -> bool:
    """Check if Ollama server is reachable.

    Args:
        base_url: Ollama server base URL.

    Returns:
        True if connection successful, False otherwise.
    """
    import ollama

    try:
        ollama.list()
        logger.info("Ollama server reachable at %s", base_url)
        return True
    except Exception as e:
        logger.error("Failed to connect to Ollama at %s: %s", base_url, e)
        return False


def check_model_available(model_name: str) -> bool:
    """Check if a model is available in Ollama.

    Args:
        model_name: Name of the model to check.

    Returns:
        True if model is available, False otherwise.
    """
    import ollama

    try:
        models = ollama.list()
        for model in models.get("models", []):
            if model_name in model.get("name", ""):
                return True
        logger.warning("Model '%s' not found in Ollama", model_name)
        return False
    except Exception as e:
        logger.error("Failed to check model availability: %s", e)
        return False
