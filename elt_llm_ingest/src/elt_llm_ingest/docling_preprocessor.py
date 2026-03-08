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
    
    Output format: Markdown with preserved structure
    - Headers: ## Section N, ### Subsection
    - Tables: Pipe-delimited markdown
    - Lists: Bullet/numbered lists
    - Code blocks: Fenced code blocks
    
    Attributes:
        output_format: Output format (always 'markdown' for Docling).
        split_by_sections: Whether to split output into per-section files.
        collection_prefix: Prefix for section collections when splitting.
        table_format: How to format tables ('markdown' or 'html').
    """
    
    def __init__(
        self,
        output_format: str = "markdown",
        collection_prefix: Optional[str] = None,
        split_by_sections: bool = False,
        table_format: str = "markdown",
        **kwargs: Any,
    ):
        """Initialize Docling preprocessor.
        
        Args:
            output_format: Output format (markdown only for Docling).
            collection_prefix: Prefix for section collections.
            split_by_sections: Whether to split by section boundaries.
            table_format: Table output format ('markdown' or 'html').
            **kwargs: Additional Docling-specific options.
        """
        self.output_format = output_format
        self.collection_prefix = collection_prefix
        self.split_by_sections = split_by_sections
        self.table_format = table_format
        self.docling_options = kwargs
    
    def preprocess(self, input_file: str, output_path: str, **kwargs: Any) -> PreprocessorResult:
        """Preprocess PDF using Docling.
        
        Args:
            input_file: Path to input PDF file.
            output_path: Base path for output file(s).
            **kwargs: Additional arguments (unused).
            
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
            # Configure Docling pipeline
            pipeline_options = PdfPipelineOptions(
                do_table_structure=True,
                do_ocr=False,  # FA Handbook is text-based, no OCR needed
                generate_page_images=False,
                generate_picture_images=False,
            )
            
            # Create converter with options — must wrap in PdfFormatOption
            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
                }
            )
            
            # Convert PDF to Docling document
            result = converter.convert(str(input_path))
            
            # Export to markdown
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
        
        Detects section boundaries using multiple patterns to handle
        various Docling output formats:
        - ## Section N
        - ## N - Section Title
        - # Section N
        - ### Section N
        
        Args:
            content: Markdown content to split.
            output_path: Base path for section files.
            
        Returns:
            PreprocessorResult with section files and collection mapping.
        """
        # Detect section boundaries (multiple patterns for flexibility)
        # Try to match various section header formats Docling might produce
        section_patterns = [
            (r'^#\s+(\d+)\s*[-–]\s*(.+?)$', 'H1_NUM'),      # # 1 - Section Title
            (r'^##\s+(\d+)\s*[-–]\s*(.+?)$', 'H2_NUM'),     # ## 1 - Section Title
            (r'^##\s+Section\s+(\d+)', 'H2_SECTION'),       # ## Section 1
            (r'^#\s+Section\s+(\d+)', 'H1_SECTION'),        # # Section 1
            (r'^###\s+(\d+)\s*[-–]', 'H3_NUM'),             # ### 1 - Title
            (r'^####\s+(\d+)\s*[-–]', 'H4_NUM'),            # #### 1 - Title
        ]
        
        # Find all section starts
        section_starts: List[Tuple[int, int, str, str]] = []
        
        for pattern, pattern_name in section_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE | re.IGNORECASE):
                section_num = int(match.group(1))
                section_title = match.group(2) if len(match.groups()) > 1 else match.group(0)
                section_starts.append((match.start(), section_num, pattern_name, section_title))
        
        # Sort by position and deduplicate (keep earliest pattern match per position)
        section_starts.sort(key=lambda x: x[0])
        
        # Deduplicate: if multiple patterns match same position, keep first
        deduped: List[Tuple[int, int, str, str]] = []
        seen_positions = set()
        for pos, num, ptype, title in section_starts:
            # Check if we already have a section within 100 chars
            if not any(abs(pos - p) < 100 for p, _, _, _ in deduped):
                deduped.append((pos, num, ptype, title))
        
        section_starts = deduped
        
        if not section_starts:
            logger.warning(
                "Docling: no section boundaries detected in %s — returning as single file. "
                "Check if Docling output uses different heading format.",
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
