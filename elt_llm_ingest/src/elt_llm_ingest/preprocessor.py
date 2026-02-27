"""Document preprocessor framework for transforming files before ingestion.

This module provides a framework for running preprocessors on files before
they are ingested into the RAG system. Preprocessors can transform files
(e.g., XML to Markdown) to improve embedding quality.
"""

from __future__ import annotations

import csv
import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PreprocessorResult:
    """Result of preprocessing.

    Attributes:
        original_file: Path to the original input file.
        output_files: List of paths to generated output files.
        success: Whether preprocessing succeeded.
        message: Optional message describing the result.
        section_collection_map: For split-mode preprocessors only — maps each
            output file path to the ChromaDB collection it should be ingested
            into. None for standard single-output preprocessors.
    """
    original_file: str
    output_files: List[str]
    success: bool = True
    message: Optional[str] = None
    section_collection_map: Optional[Dict[str, str]] = None  # file_path → collection_name


class BasePreprocessor(ABC):
    """Abstract base class for document preprocessors.
    
    Subclasses must implement the preprocess() method.
    """
    
    @abstractmethod
    def preprocess(self, input_file: str, output_path: str, **kwargs: Any) -> PreprocessorResult:
        """Preprocess a file and save the output.
        
        Args:
            input_file: Path to the input file.
            output_path: Base path for output file(s).
            **kwargs: Additional format-specific arguments.
            
        Returns:
            PreprocessorResult with output file paths.
        """
        pass


class LeanIXPreprocessor(BasePreprocessor):
    """Preprocessor for LeanIX draw.io XML exports.

    Extracts assets and relationships from LeanIX diagrams and outputs
    structured Markdown suitable for RAG embedding.

    Supports three output modes:
    - ``'markdown'`` / ``'md'`` / ``'both'``: single-file output (original behaviour).
    - ``'split'``: generates one Markdown file per logical section (overview,
      one per domain group, additional entities, relationships) and populates
      :attr:`PreprocessorResult.section_collection_map` so the ingestion
      pipeline can load each file into its own ChromaDB collection.
    """

    def __init__(self, output_format: str = "markdown", collection_prefix: Optional[str] = None):
        """Initialise the LeanIX preprocessor.

        Args:
            output_format: ``'markdown'``, ``'json'``, ``'both'``, or ``'split'``.
            collection_prefix: Required when ``output_format='split'``. Each
                section file is loaded into ``{collection_prefix}_{section_key}``.
        """
        self.output_format = output_format
        self.collection_prefix = collection_prefix

    def preprocess(self, input_file: str, output_path: str, **kwargs: Any) -> PreprocessorResult:
        """Preprocess a LeanIX XML file.

        Args:
            input_file: Path to the LeanIX XML file.
            output_path: Base path for output file(s). For split mode this is
                used as the stem of the sections sub-directory.
            **kwargs: Additional arguments (currently unused).

        Returns:
            PreprocessorResult with paths to generated files, and
            ``section_collection_map`` populated when in split mode.
        """
        from .doc_leanix_parser import LeanIXExtractor

        input_path = Path(input_file).expanduser().resolve()
        output_path_obj = Path(output_path).expanduser().resolve()
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Preprocessing LeanIX file: %s", input_path)

        try:
            extractor = LeanIXExtractor(str(input_path))
            extractor.parse_xml()
            extractor.extract_all()

            # ── Split mode: one file per domain section + relationships ────────
            if self.output_format == "split":
                section_dir = output_path_obj.parent / f"{output_path_obj.stem}_sections"
                section_file_map = extractor.save_sections(str(section_dir))

                section_collection_map: Optional[Dict[str, str]] = None
                if self.collection_prefix:
                    section_collection_map = {
                        file_path: f"{self.collection_prefix}_{section_key}"
                        for section_key, file_path in section_file_map.items()
                    }
                    logger.info(
                        "Split into %d sections → collections: %s",
                        len(section_file_map),
                        list(section_collection_map.values()),
                    )

                return PreprocessorResult(
                    original_file=str(input_path),
                    output_files=list(section_file_map.values()),
                    success=True,
                    message=(
                        f"Split into {len(section_file_map)} sections from "
                        f"{len(extractor.assets)} assets and "
                        f"{len(extractor.relationships)} relationships"
                    ),
                    section_collection_map=section_collection_map,
                )

            # ── Standard single-file modes (markdown / json / both) ───────────
            output_files: List[str] = []

            if self.output_format in ("markdown", "md", "both"):
                md_path = output_path_obj.with_suffix(".md")
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(extractor.to_markdown())
                output_files.append(str(md_path))
                logger.info("Generated Markdown: %s", md_path)

            if self.output_format in ("json", "both"):
                json_path = output_path_obj.with_suffix(".json")
                with open(json_path, "w", encoding="utf-8") as f:
                    f.write(extractor.to_json())
                output_files.append(str(json_path))
                logger.info("Generated JSON: %s", json_path)

            return PreprocessorResult(
                original_file=str(input_path),
                output_files=output_files,
                success=True,
                message=(
                    f"Extracted {len(extractor.assets)} assets and "
                    f"{len(extractor.relationships)} relationships"
                ),
            )

        except Exception as e:
            logger.error("Failed to preprocess LeanIX file: %s", e)
            return PreprocessorResult(
                original_file=str(input_path),
                output_files=[],
                success=False,
                message=str(e),
            )


class LeanIXInventoryPreprocessor(BasePreprocessor):
    """Preprocessor for the LeanIX full-inventory Excel export.

    Reads the LeanIX inventory Excel file (exported from LeanIX → Inventory →
    Export) and generates one Markdown file per fact-sheet type, then maps each
    file to its own ChromaDB collection via ``section_collection_map``.

    This mirrors the split-mode behaviour of ``LeanIXPreprocessor`` so that:
    - ``ingest_fa_ea_leanix.yaml`` → ``fa_leanix_cm_*`` (conceptual model, from XML)
    - ``ingest_fa_leanix_inventory.yaml`` → ``fa_leanix_inv_*`` (inventory, from Excel)

    Collections produced (prefix = collection_prefix, default 'fa_leanix_inv'):
        fa_leanix_inv_dataobject    — 229 DataObject fact sheets with definitions
        fa_leanix_inv_interface     — 271 Interface fact sheets (data flows)
        fa_leanix_inv_application   — 215 Application fact sheets
        fa_leanix_inv_capability    — 272 BusinessCapability fact sheets
        fa_leanix_inv_organization  — 115 Organization fact sheets
        fa_leanix_inv_itcomponent   — 180 ITComponent fact sheets
        fa_leanix_inv_provider      — 74  Provider fact sheets
        fa_leanix_inv_objective     — 59  Objective fact sheets

    Excel format expected (LeanIX standard inventory export):
        Columns: id, type, name, displayName, description, level, status, lxState
        Sheet:   first non-'ReadMe' sheet (name includes export timestamp)
    """

    # Maps LeanIX type → (collection_suffix, human_label)
    _TYPE_MAP: Dict[str, Tuple[str, str]] = {
        "DataObject":        ("dataobject",   "DataObject Inventory"),
        "Interface":         ("interface",    "Interface Inventory (Data Flows)"),
        "Application":       ("application",  "Application Inventory"),
        "BusinessCapability":("capability",   "Business Capability Inventory"),
        "Organization":      ("organization", "Organization Inventory"),
        "ITComponent":       ("itcomponent",  "IT Component Inventory"),
        "Provider":          ("provider",     "Provider Inventory"),
        "Objective":         ("objective",    "Objective Inventory"),
    }

    def __init__(self, output_format: str = "split", collection_prefix: Optional[str] = None):
        self.output_format = output_format  # kept for interface compatibility; always split
        self.collection_prefix = collection_prefix or "fa_leanix_inv"

    def preprocess(self, input_file: str, output_path: str, **kwargs: Any) -> PreprocessorResult:
        input_path = Path(input_file).expanduser().resolve()
        output_path_obj = Path(output_path).expanduser().resolve()
        section_dir = output_path_obj.parent / f"{output_path_obj.stem}_sections"
        section_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Preprocessing LeanIX inventory Excel: %s", input_path)

        try:
            rows = self._read_excel(input_path)
            logger.info("Read %d rows from Excel", len(rows))

            # Group by type
            by_type: Dict[str, List[dict]] = defaultdict(list)
            for row in rows:
                fs_type = row.get("type", "Unknown")
                if fs_type in self._TYPE_MAP:
                    by_type[fs_type].append(row)

            section_collection_map: Dict[str, str] = {}
            output_files: List[str] = []
            total = 0

            for fs_type, type_rows in sorted(by_type.items()):
                suffix, label = self._TYPE_MAP[fs_type]
                collection_name = f"{self.collection_prefix}_{suffix}"

                md_content = self._type_to_markdown(fs_type, label, type_rows)
                out_file = section_dir / f"{suffix}.md"
                out_file.write_text(md_content, encoding="utf-8")

                section_collection_map[str(out_file)] = collection_name
                output_files.append(str(out_file))
                total += len(type_rows)
                logger.info("  %s → %s (%d rows)", out_file.name, collection_name, len(type_rows))

            return PreprocessorResult(
                original_file=str(input_path),
                output_files=output_files,
                success=True,
                message=(
                    f"Split {total} fact sheets across {len(output_files)} collections "
                    f"(prefix: {self.collection_prefix})"
                ),
                section_collection_map=section_collection_map,
            )

        except Exception as e:
            logger.error("Failed to preprocess LeanIX inventory Excel: %s", e)
            return PreprocessorResult(
                original_file=str(input_path),
                output_files=[],
                success=False,
                message=str(e),
            )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_excel(xlsx_path: Path) -> List[dict]:
        """Read the LeanIX inventory Excel export → list of row dicts.

        Finds the first non-'ReadMe' sheet (the export sheet has a
        timestamp-based name that changes with every export).
        """
        try:
            import openpyxl
        except ImportError as exc:
            raise ImportError(
                "openpyxl is required to read LeanIX Excel exports. "
                "Add it to elt_llm_ingest dependencies: uv add openpyxl"
            ) from exc

        wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
        sheet_name = next(
            (name for name in wb.sheetnames if name.lower() != "readme"),
            wb.sheetnames[0],
        )
        ws = wb[sheet_name]

        headers: List[str] = []
        rows: List[dict] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i == 0:
                headers = [str(h) if h is not None else f"col_{j}" for j, h in enumerate(row)]
            else:
                if any(cell is not None for cell in row):
                    rows.append(dict(zip(headers, row)))
        return rows

    def _type_to_markdown(self, fs_type: str, label: str, rows: List[dict]) -> str:
        """Generate Markdown for a single fact-sheet type."""
        md: List[str] = []
        md.append(f"# LeanIX {label}\n\n")
        md.append(
            f"The FA LeanIX inventory contains {len(rows)} {fs_type} fact sheets. "
            "Each entry below includes the name, LeanIX identifier, hierarchy level, "
            "and a description where recorded.\n\n"
        )
        md.append("---\n\n")

        for row in rows:
            name = (row.get("name") or row.get("displayName") or "Unknown")
            fsid = row.get("id", "")
            level = row.get("level", "")
            lx_state = row.get("lxState", "")
            description = (row.get("description") or "").strip()

            md.append(f"## {name}\n\n")
            md.append(f"**LeanIX ID**: `{fsid}`  \n")
            if level:
                md.append(f"**Level**: {level}  \n")
            if lx_state:
                md.append(f"**Quality State**: {lx_state}  \n")

            if fs_type == "Interface":
                source, target = self._parse_interface_endpoints(str(name))
                if source and target:
                    md.append(f"**Data flow**: {source} → {target}  \n")

            md.append("\n")

            if description:
                if len(description) > 800:
                    description = description[:800] + "…"
                md.append(f"{description}\n\n")
            else:
                md.append("_No description recorded in LeanIX._\n\n")

            md.append("---\n\n")

        return "".join(md)

    @staticmethod
    def _parse_interface_endpoints(name: str) -> Tuple[Optional[str], Optional[str]]:
        """Try to extract source and target from an interface name like 'A to B'."""
        match = re.match(r"^(.+?)\s+to\s+(.+?)(?:\s+LI)?$", name, re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return None, None


class IdentityPreprocessor(BasePreprocessor):
    """Pass-through preprocessor that returns the original file.
    
    Used when no preprocessing is needed.
    """
    
    def preprocess(self, input_file: str, output_path: str, **kwargs: Any) -> PreprocessorResult:
        """Return the original file unchanged.
        
        Args:
            input_file: Path to the input file.
            output_path: Unused (kept for interface compatibility).
            **kwargs: Unused.
            
        Returns:
            PreprocessorResult with the original file path.
        """
        return PreprocessorResult(
            original_file=input_file,
            output_files=[input_file],
            success=True,
            message="No preprocessing applied"
        )


@dataclass
class PreprocessorConfig:
    """Preprocessor configuration.

    Attributes:
        module: Python module containing the preprocessor class.
        class_name: Name of the preprocessor class.
        output_format: Output format (e.g. 'markdown', 'json', 'both', 'split').
        output_suffix: Suffix for output files (default: '_processed').
        enabled: Whether preprocessing is enabled.
        collection_prefix: For split-mode preprocessors — prefix used to name
            each section's target collection (e.g. 'fa_leanix' → 'fa_leanix_agreements').
    """
    module: str
    class_name: str
    output_format: str = "markdown"
    output_suffix: str = "_processed"
    enabled: bool = True
    collection_prefix: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PreprocessorConfig":
        """Create PreprocessorConfig from a dictionary."""
        return cls(
            module=data.get("module", ""),
            class_name=data.get("class", ""),
            output_format=data.get("output_format", "markdown"),
            output_suffix=data.get("output_suffix", "_processed"),
            enabled=data.get("enabled", True),
            collection_prefix=data.get("collection_prefix"),
        )


def get_preprocessor(config: PreprocessorConfig) -> BasePreprocessor:
    """Factory function to create a preprocessor instance.
    
    Args:
        config: Preprocessor configuration.
        
    Returns:
        Preprocessor instance.
        
    Raises:
        ImportError: If the preprocessor module cannot be imported.
        AttributeError: If the preprocessor class doesn't exist.
    """
    if not config.enabled:
        return IdentityPreprocessor()
    
    module = __import__(config.module, fromlist=[config.class_name])
    preprocessor_class = getattr(module, config.class_name)
    return preprocessor_class(
        output_format=config.output_format,
        collection_prefix=config.collection_prefix,
    )


def preprocess_file(
    input_file: str,
    config: Optional[PreprocessorConfig],
    output_dir: Optional[str] = None
) -> List[str]:
    """Preprocess a file using the specified configuration.
    
    Args:
        input_file: Path to the input file.
        config: Preprocessor configuration. If None, returns original file.
        output_dir: Directory for output files. If None, uses input file's directory.
        
    Returns:
        List of output file paths (may be the original file if no preprocessing).
    """
    if config is None or not config.enabled:
        logger.debug("No preprocessing configured for: %s", input_file)
        return [input_file]
    
    try:
        preprocessor = get_preprocessor(config)
    except (ImportError, AttributeError) as e:
        logger.error("Failed to load preprocessor: %s", e)
        return [input_file]
    
    # Generate output path
    input_path = Path(input_file)
    if output_dir:
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / f"{input_path.stem}{config.output_suffix}"
    else:
        output_path = input_path.parent / f"{input_path.stem}{config.output_suffix}"
    
    # Run preprocessor
    result = preprocessor.preprocess(str(input_file), str(output_path))
    
    if result.success:
        logger.info("Preprocessing successful: %s", result.message)
        return result.output_files
    else:
        logger.warning("Preprocessing failed (%s), using original file", result.message)
        return [input_file]
