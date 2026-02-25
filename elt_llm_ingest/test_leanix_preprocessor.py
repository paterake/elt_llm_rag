#!/usr/bin/env python3
"""
Test script to run LeanIX preprocessor and show results.

Usage:
    uv run python test_leanix_preprocessor.py <path_to_xml_file>
    
Example:
    uv run python test_leanix_preprocessor.py ~/Documents/__data/books/DAT_V00.01_FA_Enterprise_Conceptual_Data_Model.xml
"""

import sys
from pathlib import Path
from elt_llm_ingest.preprocessor import LeanIXPreprocessor, PreprocessorConfig, preprocess_file
from elt_llm_ingest.doc_leanix_parser import LeanIXExtractor


def test_extractor_api(input_file: str):
    """Test using the LeanIXExtractor API directly."""
    print("=" * 80)
    print("TEST 1: Using LeanIXExtractor API directly")
    print("=" * 80)
    
    extractor = LeanIXExtractor(input_file)
    extractor.parse_xml()
    extractor.extract_all()
    
    print(f"\n📊 Extraction Summary:")
    print(f"   Total Assets: {len(extractor.assets)}")
    print(f"   Total Relationships: {len(extractor.relationships)}")
    
    # Show asset types
    from collections import defaultdict
    asset_types = defaultdict(int)
    for asset in extractor.assets.values():
        asset_types[asset.fact_sheet_type] += 1
    
    print(f"\n📁 Asset Types:")
    for atype, count in sorted(asset_types.items()):
        print(f"   {atype}: {count}")
    
    # Show sample assets
    print(f"\n📋 Sample Assets (first 5):")
    for i, asset in enumerate(list(extractor.assets.values())[:5]):
        print(f"\n   {i+1}. {asset.label}")
        print(f"      Type: {asset.fact_sheet_type}")
        print(f"      ID: {asset.fact_sheet_id}")
        if asset.parent_group:
            print(f"      Parent: {asset.parent_group}")
    
    # Show sample relationships
    print(f"\n🔗 Sample Relationships (first 10):")
    for i, rel in enumerate(extractor.relationships[:10]):
        source_label = rel.source_label or rel.source_id
        target_label = rel.target_label or rel.target_id
        print(f"\n   {i+1}. {source_label} → {target_label}")
        if rel.cardinality:
            print(f"      Cardinality: {rel.cardinality}")
        if rel.relationship_type:
            print(f"      Type: {rel.relationship_type}")
    
    return extractor


def test_preprocessor_api(input_file: str, output_dir: str):
    """Test using the Preprocessor API."""
    print("\n" + "=" * 80)
    print("TEST 2: Using Preprocessor API")
    print("=" * 80)
    
    output_path = Path(output_dir) / "leanix_test_output"
    
    # Test Markdown output
    print("\n📝 Generating Markdown output...")
    preprocessor_md = LeanIXPreprocessor(output_format="markdown")
    result_md = preprocessor_md.preprocess(input_file, str(output_path))
    
    if result_md.success:
        print(f"   ✅ Success: {result_md.message}")
        print(f"   Output files: {result_md.output_files}")
    else:
        print(f"   ❌ Failed: {result_md.message}")
        return None
    
    # Test JSON output
    print("\n📊 Generating JSON output...")
    output_path_json = Path(output_dir) / "leanix_test_output_json"
    preprocessor_json = LeanIXPreprocessor(output_format="json")
    result_json = preprocessor_json.preprocess(input_file, str(output_path_json))
    
    if result_json.success:
        print(f"   ✅ Success: {result_json.message}")
        print(f"   Output files: {result_json.output_files}")
    else:
        print(f"   ❌ Failed: {result_json.message}")
    
    # Test both outputs
    print("\n📚 Generating both Markdown and JSON...")
    output_path_both = Path(output_dir) / "leanix_test_output_both"
    preprocessor_both = LeanIXPreprocessor(output_format="both")
    result_both = preprocessor_both.preprocess(input_file, str(output_path_both))
    
    if result_both.success:
        print(f"   ✅ Success: {result_both.message}")
        print(f"   Output files: {result_both.output_files}")
    
    return result_md.output_files


def test_config_based_preprocessing(input_file: str, output_dir: str):
    """Test using config-based preprocessing."""
    print("\n" + "=" * 80)
    print("TEST 3: Using Config-based Preprocessing")
    print("=" * 80)
    
    config = PreprocessorConfig(
        module="elt_llm_ingest.preprocessor",
        class_name="LeanIXPreprocessor",
        output_format="markdown",
        output_suffix="_test_processed",
        enabled=True
    )
    
    output_files = preprocess_file(input_file, config, output_dir)
    
    print(f"\n   Output files: {output_files}")
    return output_files


def show_markdown_preview(markdown_file: str, lines: int = 50):
    """Show a preview of the generated Markdown."""
    print("\n" + "=" * 80)
    print(f"MARKDOWN PREVIEW (first {lines} lines): {markdown_file}")
    print("=" * 80)
    
    md_path = Path(markdown_file)
    if not md_path.exists():
        print(f"   ❌ File not found: {md_path}")
        return
    
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Show file size
    print(f"\n📊 File Statistics:")
    print(f"   Size: {len(content):,} characters")
    print(f"   Lines: {len(content.splitlines()):,}")
    
    # Show preview
    print(f"\n📄 Content Preview:")
    print("-" * 80)
    preview_lines = content.splitlines()[:lines]
    for line in preview_lines:
        print(line)
    
    if len(content.splitlines()) > lines:
        print(f"\n... ({len(content.splitlines()) - lines} more lines)")
    
    print("-" * 80)


def show_json_preview(json_file: str, max_chars: int = 2000):
    """Show a preview of the generated JSON."""
    print("\n" + "=" * 80)
    print(f"JSON PREVIEW (first {max_chars} chars): {json_file}")
    print("=" * 80)
    
    json_path = Path(json_file)
    if not json_path.exists():
        print(f"   ❌ File not found: {json_path}")
        return
    
    with open(json_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Show file size
    print(f"\n📊 File Statistics:")
    print(f"   Size: {len(content):,} characters")
    
    # Show preview
    print(f"\n📄 Content Preview:")
    print("-" * 80)
    print(content[:max_chars])
    if len(content) > max_chars:
        print(f"\n... ({len(content) - max_chars} more characters)")
    print("-" * 80)


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python test_leanix_preprocessor.py <xml_file>")
        print("\nExample:")
        print("  uv run python test_leanix_preprocessor.py ~/Documents/__data/books/model.xml")
        sys.exit(1)
    
    input_file = Path(sys.argv[1]).expanduser()
    
    if not input_file.exists():
        print(f"❌ File not found: {input_file}")
        sys.exit(1)
    
    print(f"\n🚀 Testing LeanIX Preprocessor")
    print(f"   Input file: {input_file}")
    print(f"   File size: {input_file.stat().st_size:,} bytes\n")
    
    # Create output directory
    output_dir = input_file.parent / "leanix_test_output"
    output_dir.mkdir(exist_ok=True)
    
    # Run tests
    extractor = test_extractor_api(str(input_file))
    
    output_files = test_preprocessor_api(str(input_file), str(output_dir))
    
    test_config_based_preprocessing(str(input_file), str(output_dir))
    
    # Show previews
    if output_files:
        md_file = [f for f in output_files if f.endswith('.md')]
        json_file = [f for f in output_files if f.endswith('.json')]
        
        if md_file:
            show_markdown_preview(md_file[0], lines=60)
        
        if json_file:
            show_json_preview(json_file[0], max_chars=3000)
    
    print("\n✅ All tests complete!")
    print(f"\n📁 Output directory: {output_dir}")
    print("\nGenerated files:")
    for f in output_dir.glob("*"):
        print(f"   - {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
