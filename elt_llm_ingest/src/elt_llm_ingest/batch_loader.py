"""Helper for loading batch ingestion configurations."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List

import yaml

logger = logging.getLogger(__name__)


def load_batch_config(config_path: str | Path) -> List[str]:
    """Load a list of ingestion configuration files from a meta-config file.

    Args:
        config_path: Path to the meta-config file (e.g., load_rag.yaml).

    Returns:
        List of configuration file names (e.g., ["ingest_dama_dmbok.yaml", ...]).
    """
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        data = yaml.safe_load(f)

    if not data:
        logger.warning("Empty config file: %s", path)
        return []

    # Check if this is a meta-config (list of other configs)
    # The structure in load_rag.yaml is:
    # file_paths:
    #   - "ingest_dama_dmbok.yaml"
    #   - ...
    if "file_paths" in data and isinstance(data["file_paths"], list):
        # Verify if these look like config files (end with .yaml or .yml)
        first_item = data["file_paths"][0] if data["file_paths"] else ""
        if first_item.endswith(".yaml") or first_item.endswith(".yml"):
            logger.info("Detected batch configuration with %d configs", len(data["file_paths"]))
            return data["file_paths"]
            
    return []
