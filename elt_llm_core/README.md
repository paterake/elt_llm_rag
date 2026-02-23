# elt-llm-core

Core RAG infrastructure for ChromaDB, LlamaIndex, and Ollama integration.

## Overview

This package provides the foundational components for building RAG (Retrieval-Augmented Generation) systems:

- **ChromaDB** vector store management with tenant/database/collection support
- **Ollama** embedding and LLM model configuration
- **Query engine** for retrieval and response generation
- **Configuration** management via YAML

## Installation

```bash
cd elt_llm_core
uv sync
```

## Usage

### Vector Store

```python
from elt_llm_core.config import RagConfig
from elt_llm_core.vector_store import create_chroma_client, create_storage_context

# Load config
config = RagConfig.from_yaml("rag_config.yaml")

# Create Chroma client
client = create_chroma_client(config.chroma)

# Create storage context for a collection
storage = create_storage_context(client, "my_collection")
```

### Models

```python
from elt_llm_core.config import RagConfig
from elt_llm_core.models import create_embedding_model, create_llm_model

config = RagConfig.from_yaml("rag_config.yaml")

# Create embedding model
embed_model = create_embedding_model(config.ollama)

# Create LLM model
llm_model = create_llm_model(config.ollama)
```

### Query Engine

```python
from elt_llm_core.config import RagConfig
from elt_llm_core.query_engine import QueryConfig, query_index

rag_config = RagConfig.from_yaml("rag_config.yaml")
query_config = QueryConfig(similarity_top_k=5)

result = query_index(index, "What is data governance?", rag_config, query_config)
print(result.response)
```

### Configuration

```python
from elt_llm_core.config import load_config

config = load_config("rag_config.yaml")

# Access settings
print(config.chroma.persist_dir)
print(config.ollama.embedding_model)
print(config.chunking.chunk_size)
```

## Configuration Format

```yaml
# rag_config.yaml

chroma:
  persist_dir: "./chroma_db"
  tenant: "rag_tenants"
  database: "knowledge_base"

ollama:
  base_url: "http://localhost:11434"
  embedding_model: "nomic-embed-text"
  llm_model: "llama3.2"
  embed_batch_size: 10
  context_window: 4096

chunking:
  strategy: "sentence"  # or "semantic"
  chunk_size: 1024
  chunk_overlap: 200
  sentence_split_threshold: 0.5

query:
  similarity_top_k: 5
  system_prompt: |
    You are a helpful assistant...
```

## Module Structure

```
elt_llm_core/
├── src/elt_llm_core/
│   ├── __init__.py
│   ├── config.py          # Configuration management
│   ├── vector_store.py    # ChromaDB integration
│   ├── models.py          # Ollama models
│   └── query_engine.py    # Query interface
└── tests/
```

## Prerequisites

- Python 3.11, 3.12, or 3.13 (ChromaDB is not yet compatible with Python 3.14)
- Ollama running locally: `ollama serve`
