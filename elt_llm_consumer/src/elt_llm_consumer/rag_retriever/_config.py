"""Shared config loading for the rag_retriever diagnostic tool."""
from __future__ import annotations

from pathlib import Path

import yaml

from elt_llm_core.config import RagConfig

# Resolve paths relative to this file (elt_llm_consumer/src/elt_llm_consumer/rag_retriever/)
_RAG_ROOT = Path(__file__).parent.parent.parent.parent.parent  # → elt_llm_rag/
_DEFAULT_RAG_CONFIG = _RAG_ROOT / "elt_llm_ingest" / "config" / "rag_config.yaml"
_CONSUMER_CONFIG_DIR = _RAG_ROOT / "elt_llm_consumer" / "config"

DEFAULT_SECTION_PREFIX = "fa_handbook"


def load_rag_config(config_path: Path | None = None) -> RagConfig:
    return RagConfig.from_yaml(config_path or _DEFAULT_RAG_CONFIG)


def load_entity_aliases() -> dict[str, list[str]]:
    aliases_path = _CONSUMER_CONFIG_DIR / "entity_aliases.yaml"
    if not aliases_path.exists():
        return {}
    with open(aliases_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_aliases_for(entity_name: str, entity_aliases: dict[str, list[str]]) -> list[str]:
    """Return all alias variants for entity_name from entity_aliases.yaml.

    Checks both directions — entity_name as canonical key OR as a value in
    another entity's alias list — and returns a deduplicated list excluding
    the entity name itself.
    """
    name_lower = entity_name.lower().strip()
    variants: set[str] = set()

    for canonical, aliases in entity_aliases.items():
        aliases_lower = [a.lower() for a in aliases]
        if name_lower == canonical.lower():
            variants.update(aliases_lower)
        elif name_lower in aliases_lower:
            variants.add(canonical.lower())
            variants.update(aliases_lower)

    variants.discard(name_lower)
    return sorted(variants)
