#!/usr/bin/env python3
"""Test script to demonstrate table-aware chunking.

This script shows how the TableAwareSentenceSplitter preserves table rows
as single chunks while using standard sentence splitting for prose content.

Usage:
    uv run python elt_llm_ingest/src/elt_llm_ingest/test_chunking.py
"""

from elt_llm_ingest.chunking import TableAwareSentenceSplitter, create_splitter
from llama_index.core.schema import TextNode


def test_table_detection():
    """Test that table content is correctly detected."""
    splitter = TableAwareSentenceSplitter()
    
    # Prose content - should NOT be detected as table
    prose = """The FA Handbook contains rules and regulations.
    Section 8 defines key terms used throughout the document.
    All participants must comply with these rules."""
    
    assert not splitter._is_table_content(prose), "Prose should not be detected as table"
    print("✓ Prose detection: PASS")
    
    # Table content - should be detected as table
    table = """|Term|means|
|---|---|
|Club|a club playing football in England|
|Player|any Contract Player or Non-Contract Player|
|Official|any match official appointed to a competition|"""
    
    assert splitter._is_table_content(table), "Table should be detected as table"
    print("✓ Table detection: PASS")


def test_table_row_splitting():
    """Test that table rows are kept intact."""
    splitter = TableAwareSentenceSplitter(chunk_size=256, table_chunk_size=1024)
    
    # Create a multi-line table row (like FA Handbook definitions)
    table_row = TextNode(
        text="""| Participant | means any Affiliated Association, Competition, Club, 
              | Club Official, FA Registered Football Agent, Intermediary, 
              | Player, Official, Manager, Match Official, 
              | Match Official observer/coach/mentor, Management Committee Member, 
              | and all persons participating in any activity under the 
              | jurisdiction of The Association. |"""
    )
    
    nodes = splitter._split_table_rows(table_row)
    
    # Should return 1 node (the entire row kept intact)
    assert len(nodes) == 1, f"Expected 1 node, got {len(nodes)}"
    assert "Participant" in nodes[0].text, "Node should contain the definition"
    assert nodes[0].metadata.get("content_type") == "table_row", "Should be marked as table_row"
    
    print("✓ Table row preservation: PASS")
    print(f"  Kept {len(nodes[0].text)} characters in single chunk")


def test_prose_splitting():
    """Test that prose content uses standard sentence splitting."""
    splitter = TableAwareSentenceSplitter(chunk_size=100, chunk_overlap=20)
    
    # Longer prose that should be split
    prose = TextNode(
        text="""The Football Association is the governing body of football in England.
        It was founded in 1863 and is the oldest football association in the world.
        The FA organizes various competitions including the FA Cup and the EFL Cup.
        It also oversees the England national football team and women's national team.
        The FA is responsible for licensing clubs and ensuring they meet financial requirements.
        It also manages the rules of football and disciplinary procedures for all participants.
        The headquarters are located at Wembley Stadium in London, England.
        The FA employs hundreds of staff and works with thousands of volunteers across the country."""
    )
    
    nodes = splitter._parse_nodes([prose])
    
    # Should split into multiple chunks due to sentence splitting
    assert len(nodes) > 1, f"Prose should be split into multiple chunks, got {len(nodes)}"
    print("✓ Prose splitting: PASS")
    print(f"  Split into {len(nodes)} chunks")


def test_factory_function():
    """Test the create_splitter factory function."""
    # Test sentence strategy
    sentence_splitter = create_splitter("sentence", chunk_size=256)
    assert sentence_splitter.chunk_size == 256
    print("✓ Factory 'sentence' strategy: PASS")
    
    # Test table_aware strategy
    table_splitter = create_splitter("table_aware", chunk_size=256, table_chunk_size=1024)
    assert table_splitter.chunk_size == 256
    assert table_splitter.table_chunk_size == 1024
    print("✓ Factory 'table_aware' strategy: PASS")
    
    # Test section_aware strategy
    section_splitter = create_splitter("section_aware", chunk_size=256)
    assert section_splitter.chunk_size == 256
    print("✓ Factory 'section_aware' strategy: PASS")


def test_fa_handbook_definition():
    """Test with a real FA Handbook-style definition."""
    splitter = TableAwareSentenceSplitter(chunk_size=256, table_chunk_size=1536)
    
    # Simulated FA Handbook definitions table row
    definition = TextNode(
        text="""| "Club" means any club playing the game of football in England and recognised as such by The Association pursuant to the Rules. For the purposes of these Regulations, references to a Club shall include a reference to any subsidiary company or holding company of the Club. |"""
    )
    
    nodes = splitter._split_table_rows(definition)
    
    assert len(nodes) == 1, "Definition should be kept as single chunk"
    assert len(nodes[0].text) > 200, "Definition should be substantial"
    assert nodes[0].metadata.get("content_type") == "table_row", "Should be marked as table_row"
    print("✓ FA Handbook definition preservation: PASS")
    print(f"  Definition kept intact: {len(nodes[0].text)} characters")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Table-Aware Chunking Test Suite")
    print("=" * 60)
    print()
    
    test_table_detection()
    test_table_row_splitting()
    test_prose_splitting()
    test_factory_function()
    test_fa_handbook_definition()
    
    print()
    print("=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)
    print()
    print("Summary:")
    print("  - Table content is correctly detected")
    print("  - Table rows are preserved as single chunks (up to table_chunk_size)")
    print("  - Prose content uses standard sentence splitting")
    print("  - FA Handbook definitions will remain intact during ingestion")


if __name__ == "__main__":
    main()
