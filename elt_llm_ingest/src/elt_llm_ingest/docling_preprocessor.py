"""Docling-based PDF preprocessor for regulatory documents.

Uses IBM's Docling library for intelligent document parsing with:
- Layout-aware text extraction
- Table structure preservation
- Header/section detection
- Figure and image handling

Optimized for FA Handbook-style regulatory documents with:
- Numbered sections (Section 1, Section 2, etc.)
- Definition tables (|Term|means Definition|)
- Hierarchical structure (sections → subsections → content)

Configuration via YAML (elt_llm_ingest/config/ingest_fa_handbook_docling.yaml):
  preprocessor:
    docling_options: Dict with pipeline and export options
    section_splitting: Section splitting configuration
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from elt_llm_ingest.preprocessor import BasePreprocessor, PreprocessorResult

logger = logging.getLogger(__name__)


class DoclingPreprocessor(BasePreprocessor):
    """PDF preprocessor using IBM Docling for layout-aware extraction.
    
    Docling uses deep learning models to understand document structure,
    making it superior to font-based heuristics for:
    - Complex table layouts (multi-row definitions)
    - Hierarchical headers (section → subsection → content)
    - Mixed content (text + tables + figures)
    - Regulatory document formatting
    
    Configuration (via YAML config):
      docling_options: Dict with pipeline and export options
      split_by_sections: Whether to split by section boundaries
      collection_prefix: Prefix for section collections
      table_format: Table output format ('markdown' or 'html')
      section_splitting: Section splitting configuration
    """
    
    def __init__(
        self,
        output_format: str = "markdown",
        collection_prefix: Optional[str] = None,
        split_by_sections: bool = False,
        table_format: str = "markdown",
        docling_options: Optional[Dict[str, Any]] = None,
        section_splitting: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        """Initialize Docling preprocessor.
        
        Args:
            output_format: Output format (markdown only for Docling).
            collection_prefix: Prefix for section collections.
            split_by_sections: Whether to split by section boundaries.
            table_format: Table output format ('markdown' or 'html').
            docling_options: Docling pipeline and export options from YAML config.
            section_splitting: Section splitting configuration from YAML config.
            **kwargs: Additional arguments (unused).
        """
        self.output_format = output_format
        self.collection_prefix = collection_prefix
        self.split_by_sections = split_by_sections
        self.table_format = table_format
        self.docling_options = docling_options or {}
        self.section_splitting = section_splitting or {}
        self.extra_kwargs = kwargs
    
    def preprocess(self, input_file: str, output_path: str, **kwargs: Any) -> PreprocessorResult:
        """Preprocess PDF using Docling.
        
        Args:
            input_file: Path to input PDF file.
            output_path: Base path for output file(s).
            **kwargs: Additional arguments (merged with docling_options).
            
        Returns:
            PreprocessorResult with output file paths and section mapping.
            
        Raises:
            ImportError: If docling package is not installed.
        """
        try:
            from docling.document_converter import (
                DocumentConverter,
                InputFormat,
                PdfFormatOption,
            )
            from docling.datamodel.pipeline_options import PdfPipelineOptions
        except ImportError as e:
            raise ImportError(
                "Docling is not installed. Install it with:\n"
                "  uv add docling --package elt-llm-ingest\n"
                "\n"
                "Docling requires additional dependencies (torch, transformers).\n"
                "First-time download may take 5-10 minutes for model weights."
            ) from e
        
        input_path = Path(input_file).expanduser().resolve()
        
        if not input_path.exists():
            return PreprocessorResult(
                original_file=str(input_path),
                output_files=[],
                success=False,
                message=f"Input file not found: {input_path}",
            )
        
        logger.info("Docling: processing %s", input_path.name)
        
        try:
            # Merge kwargs with config options (kwargs take precedence)
            options = {**self.docling_options, **kwargs}
            
            # Configure Docling pipeline from config
            pipeline_options = PdfPipelineOptions(
                do_table_structure=options.get('do_table_structure', True),
                do_ocr=options.get('do_ocr', False),
                generate_page_images=options.get('generate_page_images', False),
                generate_picture_images=options.get('generate_picture_images', False),
            )

            # Create converter with options — must wrap in PdfFormatOption
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )

            # Convert PDF to Docling document
            result = converter.convert(str(input_path))

            if self.table_format == "html":
                md_content = result.document.export_to_html()
            else:
                md_content = result.document.export_to_markdown()
            
            # Write output
            output_path_obj = Path(output_path).expanduser().resolve()
            output_path_obj.parent.mkdir(parents=True, exist_ok=True)
            output_path_obj.write_text(md_content, encoding="utf-8")
            
            logger.info(
                "Docling: converted %s → %s (%d chars)",
                input_path.name,
                output_path_obj.name,
                len(md_content),
            )
            
            # If splitting by sections, do it now
            if self.split_by_sections and self.collection_prefix:
                return self._split_by_sections(md_content, output_path_obj)
            
            return PreprocessorResult(
                original_file=str(input_path),
                output_files=[str(output_path_obj)],
                success=True,
                message=f"Docling: converted {input_path.name} ({len(md_content):,} chars)",
            )
            
        except Exception as e:
            logger.error("Docling conversion failed: %s", e)
            return PreprocessorResult(
                original_file=str(input_path),
                output_files=[],
                success=False,
                message=f"Docling conversion failed: {e}",
            )
    
    def _split_by_sections(
        self,
        content: str,
        output_path: Path,
    ) -> PreprocessorResult:
        """Split markdown content by section headers.
        
        Detects section boundaries using configured patterns to handle
        various Docling output formats:
        - # 1 - Section Title
        - ## 1 - Section Title
        - ## Section 1
        - ### 1 - Title
        
        Args:
            content: Markdown content to split.
            output_path: Base path for section files.
            
        Returns:
            PreprocessorResult with section files and collection mapping.
        """
        # Get patterns from config or use defaults
        patterns_config = self.section_splitting.get('patterns', [])
        min_section_chars = self.section_splitting.get('min_section_chars', 100)
        
        if patterns_config:
            # Use configured patterns
            section_patterns = [
                (p['pattern'], p['name'], p.get('priority', 99))
                for p in patterns_config
            ]
        else:
            # Default patterns
            section_patterns = [
                (r'^#\s+(\d+)\s*[-–]\s*(.+?)$', 'H1_NUM', 1),
                (r'^##\s+(\d+)\s*[-–]\s*(.+?)$', 'H2_NUM', 2),
                (r'^##\s+Section\s+(\d+)', 'H2_SECTION', 2),
                (r'^#\s+Section\s+(\d+)', 'H1_SECTION', 1),
                (r'^###\s+(\d+)\s*[-–]', 'H3_NUM', 3),
                (r'^####\s+(\d+)\s*[-–]', 'H4_NUM', 4),
            ]
        
        # Sort patterns by priority (lower = higher priority)
        section_patterns.sort(key=lambda x: x[2])
        
        # Find all section starts
        section_starts: List[Tuple[int, int, str, str, int]] = []
        
        for pattern, pattern_name, priority in section_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                section_num = int(match.group(1))
                section_title = match.group(2) if len(match.groups()) > 1 else match.group(0)
                section_starts.append((match.start(), section_num, pattern_name, section_title, priority))
        
        # Sort by position, then by priority
        section_starts.sort(key=lambda x: (x[0], x[4]))

        # Step 1: deduplicate matches at the same position (multiple patterns firing)
        deduped: List[Tuple[int, int, str, str]] = []
        for pos, num, ptype, title, priority in section_starts:
            if not any(abs(pos - p) < 100 for p, _, _, _ in deduped):
                deduped.append((pos, num, ptype, title))

        # Step 2: collapse repeated section numbers (Docling running-header artefact).
        # PDFs often repeat the section title as a page header on every page of that
        # section. Each repeat looks like a fresh section boundary but is not — it
        # should be absorbed into the ongoing section.  Keep only the FIRST occurrence
        # of each section number; a new boundary is only recognised when the number
        # changes.
        collapsed: List[Tuple[int, int, str, str]] = []
        prev_num: Optional[int] = None
        for pos, num, ptype, title in deduped:
            if num != prev_num:
                collapsed.append((pos, num, ptype, title))
                prev_num = num

        section_starts = collapsed
        
        if not section_starts:
            logger.warning(
                "Docling: no section boundaries detected in %s — returning as single file. "
                "Check if Docling output uses different heading format. "
                "Consider adjusting section_patterns in config.",
                output_path.name,
            )
            logger.debug("First 2000 chars of content: %s", content[:2000])
            return PreprocessorResult(
                original_file=str(output_path),
                output_files=[str(output_path)],
                success=True,
                message="No section boundaries detected — check Docling output format",
            )
        
        # Split content into sections
        section_dir = output_path.parent / f"{output_path.stem}_sections"
        section_dir.mkdir(parents=True, exist_ok=True)
        
        output_files: List[str] = []
        section_collection_map: Dict[str, str] = {}
        
        for i, (start, section_num, pattern_type, title) in enumerate(section_starts):
            # Determine end position (next section or end of document)
            end = section_starts[i + 1][0] if i + 1 < len(section_starts) else len(content)
            
            # Extract section content
            section_content = content[start:end].strip()
            
            # Skip sections that are too small
            if len(section_content) < min_section_chars:
                logger.debug(
                    "  Skipping section %02d: only %d chars (min: %d)",
                    section_num, len(section_content), min_section_chars,
                )
                continue
            
            # Write section file
            collection_name = f"{self.collection_prefix}_s{section_num:02d}"
            out_file = section_dir / f"s{section_num:02d}.md"
            out_file.write_text(section_content, encoding="utf-8")
            
            output_files.append(str(out_file))
            section_collection_map[str(out_file)] = collection_name
            
            logger.info(
                "  Section %02d → collection '%s' (%d chars, pattern: %s)",
                section_num,
                collection_name,
                len(section_content),
                pattern_type,
            )
        
        return PreprocessorResult(
            original_file=str(output_path),
            output_files=output_files,
            success=True,
            message=f"Docling: split into {len(output_files)} sections",
            section_collection_map=section_collection_map,
        )
