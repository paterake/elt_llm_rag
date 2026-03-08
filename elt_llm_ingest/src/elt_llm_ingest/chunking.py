"""Custom chunking strategies for RAG ingestion.

This module provides specialized text splitters that handle different content types
appropriately, such as preserving table rows as single chunks while using standard
sentence splitting for prose content.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import BaseNode, TextNode


class TableAwareSentenceSplitter(SentenceSplitter):
    """SentenceSplitter that preserves table rows as single chunks.
    
    For FA Handbook Rules §8 definitions table and similar structured content:
    - Prose sections: Standard sentence splitting (chunk_size tokens)
    - Table rows: Single chunk per row (up to table_chunk_size tokens)
    
    This prevents multi-line table definitions from being split across chunks,
    which would lose semantic coherence and reduce retrieval quality.
    
    Example:
        A definitions table row like:
        ```
        | Participant | means any Affiliated Association, Competition, Club, 
                      | Club Official, FA Registered Football Agent, ... |
        ```
        Would be kept as one chunk instead of split across 2-3 chunks.
    
    Attributes:
        chunk_size: Token size for prose chunks (default: 256).
        chunk_overlap: Overlap between prose chunks (default: 32).
        table_chunk_size: Maximum token size for table row chunks (default: 1024).
        paragraph_separator: Separator used to detect paragraph boundaries.
    """
    
    table_chunk_size: int = 1024
    table_detection_threshold: float = 0.3

    def __init__(
        self,
        chunk_size: int = 256,
        chunk_overlap: int = 32,
        table_chunk_size: int = 1024,
        table_detection_threshold: float = 0.3,
        paragraph_separator: str = "\n\n",
        **kwargs: Any,
    ):
        """Initialize the table-aware splitter.

        Args:
            chunk_size: Token size for prose chunks.
            chunk_overlap: Overlap between prose chunks.
            table_chunk_size: Maximum token size for table row chunks.
            table_detection_threshold: Min proportion of pipe-delimited lines to
                classify a node as table content (0.0–1.0).
            paragraph_separator: Separator for paragraph boundaries.
            **kwargs: Additional arguments passed to SentenceSplitter.
        """
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separator=paragraph_separator,
            **kwargs,
        )
        # Use object.__setattr__ to bypass Pydantic's field validation
        object.__setattr__(self, "table_chunk_size", table_chunk_size)
        object.__setattr__(self, "table_detection_threshold", table_detection_threshold)
        object.__setattr__(self, "paragraph_separator", paragraph_separator)
    
    def _parse_nodes(self, nodes: List[BaseNode], **kwargs: Any) -> List[BaseNode]:
        """Override to handle table content specially.

        Always routes through _split_table_rows which handles mixed content:
        - Pipe-delimited lines → table_chunk_size-bounded chunks (kept intact)
        - Prose blocks → sentence-split with standard chunk_size

        This ensures correct chunking regardless of the table/prose ratio in a
        node (e.g. §8 is ~9% pipe lines but still contains definition tables).

        Args:
            nodes: Input nodes to split.
            **kwargs: Additional arguments.

        Returns:
            List of split nodes with appropriate chunking.
        """
        all_nodes: List[BaseNode] = []

        for node in nodes:
            mixed_nodes = self._split_table_rows(node)
            for n in mixed_nodes:
                ct = n.metadata.get("content_type", "") if hasattr(n, "metadata") else ""
                if ct == "prose":
                    # Further sentence-split prose blocks to respect chunk_size
                    all_nodes.extend(super()._parse_nodes([n], **kwargs))
                else:
                    all_nodes.append(n)

        return all_nodes
    
    def _is_table_content(self, text: str) -> bool:
        """Detect if text contains markdown table patterns.
        
        Looks for pipe-delimited table rows. A text is considered table content
        if >30% of its lines are table rows (contain pipe delimiters).
        
        Args:
            text: The text to analyze.
            
        Returns:
            True if the text is primarily table content.
        """
        lines = text.strip().split("\n")
        if len(lines) == 0:
            return False
        
        table_line_count = 0
        for line in lines:
            stripped = line.strip()
            # Count lines that contain pipe delimiters (table content)
            # More lenient detection: lines with | anywhere are considered table-related
            if "|" in stripped:
                table_line_count += 1
        
        return len(lines) > 0 and (table_line_count / len(lines)) > self.table_detection_threshold
    
    def _split_table_rows(self, node: BaseNode) -> List[BaseNode]:
        """Split table content into chunks respecting table_chunk_size.

        Accumulates consecutive pipe-delimited lines into chunks bounded by
        table_chunk_size (rough token estimate: 4 chars ≈ 1 token).  Prose
        lines interspersed with table content are flushed as separate nodes.

        Args:
            node: Input node containing table content.

        Returns:
            List of nodes, each within table_chunk_size tokens.
        """
        text = node.text if hasattr(node, "text") else str(node)
        metadata = dict(node.metadata) if hasattr(node, "metadata") else {}

        # Rough token estimate — avoids a tokeniser round-trip
        max_chars = self.table_chunk_size * 4

        lines = text.split("\n")
        nodes: List[BaseNode] = []

        table_lines: List[str] = []
        table_chars: int = 0
        prose_lines: List[str] = []

        def _flush_table() -> None:
            nonlocal table_lines, table_chars
            if table_lines:
                nodes.append(TextNode(
                    text="\n".join(table_lines),
                    metadata={**metadata, "content_type": "table_row"},
                ))
                table_lines = []
                table_chars = 0

        def _flush_prose() -> None:
            nonlocal prose_lines
            if prose_lines:
                prose_text = "\n".join(prose_lines).strip()
                if prose_text:
                    nodes.append(TextNode(
                        text=prose_text,
                        metadata={**metadata, "content_type": "prose"},
                    ))
                prose_lines = []

        for line in lines:
            if "|" in line:
                # Skip markdown table separator lines (|---|---|) — no semantic value
                # and they can be very long, causing tokenizer overflow
                stripped = line.strip()
                if stripped and all(c in '|-+: ' for c in stripped):
                    continue
                _flush_prose()
                line_chars = len(line)
                # Start a new chunk when the current one would overflow
                if table_chars + line_chars > max_chars and table_lines:
                    _flush_table()
                # Single line exceeds max_chars — split at word boundaries
                if line_chars > max_chars:
                    words = line.split(" ")
                    sub_chunk: List[str] = []
                    sub_chars = 0
                    for word in words:
                        word_chars = len(word) + 1  # +1 for space
                        if sub_chars + word_chars > max_chars and sub_chunk:
                            nodes.append(TextNode(
                                text=" ".join(sub_chunk),
                                metadata={**metadata, "content_type": "table_row"},
                            ))
                            sub_chunk = [word]
                            sub_chars = word_chars
                        else:
                            sub_chunk.append(word)
                            sub_chars += word_chars
                    if sub_chunk:
                        nodes.append(TextNode(
                            text=" ".join(sub_chunk),
                            metadata={**metadata, "content_type": "table_row"},
                        ))
                else:
                    table_lines.append(line)
                    table_chars += line_chars
            else:
                _flush_table()
                prose_lines.append(line)

        _flush_table()
        _flush_prose()

        return nodes if nodes else [node]


class SectionAwareSentenceSplitter(SentenceSplitter):
    """SentenceSplitter that respects document section boundaries.
    
    Detects section headers (e.g., markdown ## Header) and tries to keep
    sections intact within chunks. Useful for documents like the FA Handbook
    where sections represent logical units (Rules §8, Section 23, etc.).
    
    Attributes:
        chunk_size: Target token size for chunks.
        chunk_overlap: Overlap between chunks.
        section_header_pattern: Regex pattern for detecting section headers.
    """
    
    section_header_pattern: str = r"^#{1,6}\s+.+$"
    
    def __init__(
        self,
        chunk_size: int = 256,
        chunk_overlap: int = 32,
        section_header_pattern: str = r"^#{1,6}\s+.+$",
        **kwargs: Any,
    ):
        """Initialize the section-aware splitter.
        
        Args:
            chunk_size: Target token size for chunks.
            chunk_overlap: Overlap between chunks.
            section_header_pattern: Regex for section headers.
            **kwargs: Additional arguments passed to SentenceSplitter.
        """
        super().__init__(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **kwargs,
        )
        # Use object.__setattr__ to bypass Pydantic's field validation
        object.__setattr__(self, "section_header_pattern", section_header_pattern)
    
    def _parse_nodes(self, nodes: List[BaseNode], **kwargs: Any) -> List[BaseNode]:
        """Override to respect section boundaries.
        
        Args:
            nodes: Input nodes to split.
            **kwargs: Additional arguments.
            
        Returns:
            List of split nodes respecting section boundaries.
        """
        all_nodes: List[BaseNode] = []
        
        for node in nodes:
            text = node.text if hasattr(node, "text") else str(node)
            
            # Find section boundaries
            section_splits = self._find_section_splits(text)
            
            if len(section_splits) > 1:
                # Split by sections, then apply normal chunking within each
                for section_text in section_splits:
                    section_node = TextNode(
                        text=section_text,
                        metadata=dict(node.metadata) if hasattr(node, "metadata") else {},
                    )
                    chunked = super()._parse_nodes([section_node], **kwargs)
                    all_nodes.extend(chunked)
            else:
                # No clear sections - use standard splitting
                chunked = super()._parse_nodes([node], **kwargs)
                all_nodes.extend(chunked)
        
        return all_nodes
    
    def _find_section_splits(self, text: str) -> List[str]:
        """Find section boundaries in text and split accordingly.
        
        Args:
            text: The text to split.
            
        Returns:
            List of section texts.
        """
        pattern = re.compile(self.section_header_pattern, re.MULTILINE)
        matches = list(pattern.finditer(text))
        
        if not matches:
            return [text]
        
        sections: List[str] = []
        for i, match in enumerate(matches):
            start = match.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections.append(text[start:end].strip())
        
        return sections


def create_splitter(
    strategy: str,
    chunk_size: int = 256,
    chunk_overlap: int = 32,
    **kwargs: Any,
) -> SentenceSplitter:
    """Factory function to create appropriate splitter based on strategy.

    Args:
        strategy: Splitter strategy name. One of:
            - "sentence": Standard sentence-based splitting
            - "table_aware": Preserves table rows as single chunks
            - "section_aware": Respects section boundaries
        chunk_size: Target chunk size in tokens.
        chunk_overlap: Overlap between chunks.
        **kwargs: Additional strategy-specific arguments.

    Returns:
        Appropriate SentenceSplitter instance.

    Raises:
        ValueError: If strategy is not recognized.
    """
    if strategy == "sentence":
        return SentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **kwargs,
        )
    elif strategy == "table_aware":
        table_chunk_size = kwargs.pop("table_chunk_size", 1024)
        table_detection_threshold = kwargs.pop("table_detection_threshold", 0.3)
        return TableAwareSentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            table_chunk_size=table_chunk_size,
            table_detection_threshold=table_detection_threshold,
            **kwargs,
        )
    elif strategy == "section_aware":
        return SectionAwareSentenceSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            **kwargs,
        )
    else:
        raise ValueError(
            f"Unknown chunking strategy: {strategy}. "
            f"Valid options: sentence, table_aware, section_aware"
        )
