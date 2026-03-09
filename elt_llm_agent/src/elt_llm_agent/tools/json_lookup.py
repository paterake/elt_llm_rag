"""JSON lookup tool — direct access to LeanIX sidecar JSON files."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from llama_index.core.tools import FunctionTool

logger = logging.getLogger(__name__)

# Default output directory from elt_llm_consumer
DEFAULT_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent / ".tmp"


def _load_json_sidecars() -> dict[str, dict[str, Any]]:
    """Load all JSON sidecars from .tmp directory and consumer outputs.

    Returns:
        Dict mapping entity type to dict of entities keyed by fact_sheet_id
    """
    sidecars = {}

    # Default output directory from elt_llm_consumer
    search_dirs = [
        Path(__file__).parent.parent.parent.parent.parent / ".tmp",  # Project root .tmp
        Path.cwd() / ".tmp",
    ]

    for search_dir in search_dirs:
        if not search_dir.exists():
            continue

        # Look for LeanIX _model.json files (from ingestion)
        for json_file in search_dir.glob("*_model.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                # Extract domain from filename
                domain = json_file.stem.replace("_model", "")

                # Index by fact_sheet_id for O(1) lookup
                sidecars[domain] = {}
                if isinstance(data, list):
                    for entity in data:
                        fs_id = entity.get("fact_sheet_id") or entity.get("id")
                        if fs_id:
                            sidecars[domain][str(fs_id)] = entity
                elif isinstance(data, dict):
                    sidecars[domain] = data

                logger.debug("Loaded %s: %d entities", json_file.name, len(sidecars[domain]))

            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load %s: %s", json_file.name, e)

        # Look for LeanIX _inventory.json files (from ingestion)
        for json_file in search_dir.glob("*_inventory.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                domain = json_file.stem.replace("_inventory", "")
                sidecars[domain] = data if isinstance(data, dict) else {"items": data}

                logger.debug("Loaded %s: %d entries", json_file.name, len(data) if isinstance(data, (list, dict)) else 0)

            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load %s: %s", json_file.name, e)

        # Fallback: Load consumer consolidated catalog (contains entity data)
        catalog_file = search_dir / "fa_consolidated_catalog_party.json"
        if catalog_file.exists():
            try:
                with open(catalog_file, "r") as f:
                    catalog = json.load(f)

                # Extract entities from nested domain structure
                # Structure: {DOMAIN: {subtypes: {SUBTYPE: {entities: [...]}}}}
                for domain_name, domain_data in catalog.items():
                    if not isinstance(domain_data, dict):
                        continue  # Skip non-domain keys
                    
                    # Get entities from subtypes
                    subtypes = domain_data.get("subtypes", {})
                    for subtype_name, subtype_data in subtypes.items():
                        entities = subtype_data.get("entities", [])
                        for entity in entities:
                            entity_name = entity.get("entity_name", "")
                            if entity_name:
                                # Store under consumer_{domain}_{subtype} for organized access
                                key = f"consumer_{domain_name.lower()}_{subtype_name.lower().replace(' ', '_')}"
                                if key not in sidecars:
                                    sidecars[key] = {}
                                sidecars[key][entity_name] = entity
                                
                                # Also store under just entity name for easy lookup
                                sidecars.setdefault("consumer_all", {})[entity_name] = entity

                logger.debug("Loaded consumer catalog into sidecars: %d keys", len(sidecars))

            except (json.JSONDecodeError, IOError) as e:
                logger.warning("Failed to load consumer catalog: %s", e)

    return sidecars


def json_lookup_tool(
    entity_type: str,
    entity_id: str | None = None,
    entity_name: str | None = None,
    filter_field: str | None = None,
    filter_value: str | None = None,
) -> str:
    """Lookup entities in LeanIX JSON sidecars by ID, name, or field filter.

    This tool provides fast, deterministic access to structured LeanIX data
    (conceptual model entities, asset inventory) without RAG retrieval.

    Args:
        entity_type: Type of entity to lookup. Options:
            - "model": Conceptual model entities (from draw.io)
            - "inventory": Asset inventory (from Excel export)
            - Specific domain: "party", "agreements", "dataobject", "interface", etc.
        entity_id: Optional fact_sheet_id to lookup directly
        entity_name: Optional entity name to search for
        filter_field: Optional field name to filter on (e.g., "name", "type")
        filter_value: Optional value to filter for

    Returns:
        JSON-formatted string of matching entities

    Example:
        >>> # Lookup by ID
        >>> result = json_lookup_tool(entity_type="dataobject", entity_id="DO-123")

        >>> # Lookup by name
        >>> result = json_lookup_tool(entity_type="interface", entity_name="Player Registration")

        >>> # Filter by field
        >>> result = json_lookup_tool(
        ...     entity_type="inventory",
        ...     filter_field="type",
        ...     filter_value="DataObject"
        ... )
    """
    try:
        sidecars = _load_json_sidecars()

        if not sidecars:
            return "No JSON sidecars found. Run ingestion first: uv run python -m elt_llm_ingest.runner --cfg load_rag"

        # Determine which sidecar to use
        if entity_type == "model":
            # Search all _model.json files
            candidates = {}
            for key, data in sidecars.items():
                if "_model" in key or key in ["party", "agreements", "initiative"]:
                    candidates.update(data)
            search_data = candidates
        elif entity_type == "inventory":
            # Search all _inventory.json files
            search_data = {}
            for key, data in sidecars.items():
                if "_inventory" in key or key in ["dataobject", "interface", "application"]:
                    if isinstance(data, dict):
                        search_data.update(data)
                    elif isinstance(data, list):
                        search_data.update({item.get("fact_sheet_id", str(i)): item for i, item in enumerate(data)})
        elif entity_type.startswith("consumer"):
            # Consumer catalog lookup
            search_data = sidecars.get(entity_type, {})
        else:
            # Specific domain
            search_data = sidecars.get(entity_type.lower(), {})

        if not search_data:
            return f"No data found for entity_type='{entity_type}'. Available: {list(sidecars.keys())[:15]}"

        # Lookup by ID
        if entity_id:
            result = search_data.get(entity_id)
            if result:
                return json.dumps(result, indent=2)
            return f"Entity with id='{entity_id}' not found"

        # Lookup by name
        if entity_name:
            matches = []
            for item in search_data.values():
                # Check both "name" (LeanIX) and "entity_name" (consumer catalog)
                name = item.get("name", "") or item.get("entity_name", "")
                if entity_name.lower() in name.lower():
                    matches.append(item)
            if matches:
                return json.dumps(matches[:10], indent=2)  # Limit to 10
            return f"No entities found with name containing '{entity_name}'"

        # Filter by field
        if filter_field and filter_value:
            matches = []
            for item in search_data.values():
                value = item.get(filter_field, "")
                if filter_value.lower() in str(value).lower():
                    matches.append(item)
            if matches:
                return json.dumps(matches[:20], indent=2)  # Limit to 20
            return f"No entities found with {filter_field}='{filter_value}'"

        # Return all (limited)
        items = list(search_data.values())[:50]
        return json.dumps(items, indent=2)

    except Exception as e:
        logger.exception("JSON lookup failed")
        return f"Error: {e}"


def create_json_lookup_tool() -> FunctionTool:
    """Create LlamaIndex FunctionTool for JSON lookups."""
    return FunctionTool.from_defaults(
        fn=json_lookup_tool,
        name="json_lookup",
        description="Lookup LeanIX entities (conceptual model, inventory) by ID, name, or field filter. Fast, deterministic access to structured data.",
    )


JSONLookupTool = create_json_lookup_tool
