#!/usr/bin/env python3
"""Compare Docling vs. PyMuPDF4LLM output quality.

Compares:
- Text extraction accuracy
- Table preservation
- Header/section detection
- Processing time
- Output size

Usage:
    uv run python elt_llm_ingest/src/elt_llm_ingest/compare_parsers.py
"""

import time
from pathlib import Path

from elt_llm_ingest.preprocessor import PyMuPDFPreprocessor


def compare_parsers(pdf_path: str, output_dir: str):
    """Compare Docling and PyMuPDF4LLM on the same PDF.
    
    Args:
        pdf_path: Path to input PDF file.
        output_dir: Directory for output files.
    """
    output_path = Path(output_dir).expanduser().resolve()
    output_path.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("PDF Parser Comparison: Docling vs. PyMuPDF4LLM")
    print("=" * 70)
    print(f"\nInput: {pdf_path}")
    print(f"Output: {output_path}\n")
    
    results = {}
    
    # Test PyMuPDF4LLM
    print("\n[1/2] Testing PyMuPDF4LLM...")
    start = time.time()
    pymupdf = PyMuPDFPreprocessor()
    result_pymupdf = pymupdf.preprocess(
        pdf_path,
        str(output_path / "FA_Handbook_pymupdf.md"),
    )
    elapsed_pymupdf = time.time() - start
    
    if result_pymupdf.success:
        output_file = Path(result_pymupdf.output_files[0])
        content = output_file.read_text()
        results['pymupdf'] = {
            'success': True,
            'time': elapsed_pymupdf,
            'chars': len(content),
            'output_file': output_file,
        }
        print(f"  ✅ Success: {len(content):,} chars in {elapsed_pymupdf:.2f}s")
    else:
        results['pymupdf'] = {'success': False, 'error': result_pymupdf.message}
        print(f"  ❌ Failed: {result_pymupdf.message}")
    
    # Test Docling
    print("\n[2/2] Testing Docling...")
    start = time.time()
    try:
        from elt_llm_ingest.docling_preprocessor import DoclingPreprocessor
        
        docling = DoclingPreprocessor()
        result_docling = docling.preprocess(
            pdf_path,
            str(output_path / "FA_Handbook_docling.md"),
        )
        elapsed_docling = time.time() - start
        
        if result_docling.success:
            output_file = Path(result_docling.output_files[0])
            content = output_file.read_text()
            results['docling'] = {
                'success': True,
                'time': elapsed_docling,
                'chars': len(content),
                'output_file': output_file,
            }
            print(f"  ✅ Success: {len(content):,} chars in {elapsed_docling:.2f}s")
        else:
            results['docling'] = {'success': False, 'error': result_docling.message}
            print(f"  ❌ Failed: {result_docling.message}")
    except ImportError as e:
        results['docling'] = {'success': False, 'error': str(e)}
        print(f"  ❌ Not installed: {e}")
        print(f"     Install with: uv add docling --package elt-llm-ingest")
    
    # Comparison
    print("\n" + "=" * 70)
    print("Comparison Results")
    print("=" * 70)
    
    if results['pymupdf']['success'] and results.get('docling', {}).get('success'):
        pm = results['pymupdf']
        dl = results['docling']
        
        print(f"\n{'Metric':<25} {'PyMuPDF4LLM':>15} {'Docling':>15} {'Difference':>15}")
        print("-" * 70)
        print(f"{'Processing time (s)':<25} {pm['time']:>15.2f} {dl['time']:>15.2f} {dl['time']/pm['time']-1:>14.1%}")
        print(f"{'Output size (chars)':<25} {pm['chars']:>15,} {dl['chars']:>15,} {dl['chars']-pm['chars']:>+14,}")
        print(f"{'Chars/second':<25} {pm['chars']/pm['time']:>15,.0f} {dl['chars']/dl['time']:>15,.0f}")
        
        # Content comparison
        pm_content = pm['output_file'].read_text()
        dl_content = dl['output_file'].read_text()
        
        print(f"\n{'Content Analysis':<25}")
        print("-" * 70)
        
        # Count tables
        pm_tables = pm_content.count('|means|')
        dl_tables = dl_content.count('|means|')
        print(f"{'Definition tables':<25} {pm_tables:>15} {dl_tables:>15} {dl_tables-pm_tables:>+14}")
        
        # Count section headers
        pm_sections = pm_content.count('## Section')
        dl_sections = dl_content.count('## Section')
        print(f"{'Section headers':<25} {pm_sections:>15} {dl_sections:>15} {dl_sections-pm_sections:>+14}")
        
        # Count bold definitions
        pm_bold = pm_content.count('**')
        dl_bold = dl_content.count('**')
        print(f"{'Bold markers (**)**':<25} {pm_bold:>15} {dl_bold:>15} {dl_bold-pm_bold:>+14}")
        
        print("\n" + "=" * 70)
        print("Recommendation")
        print("=" * 70)
        
        if dl['time'] > pm['time'] * 5:
            print("\n⚠️  Docling is >5x slower than PyMuPDF4LLM")
        
        if dl['chars'] > pm['chars'] * 1.2:
            print("✅ Docling extracts more content (+20% or more)")
        elif dl['chars'] < pm['chars'] * 0.8:
            print("⚠️  Docling extracts less content (-20% or more)")
        
        if dl_tables > pm_tables:
            print(f"✅ Docling found {dl_tables-pm_tables} more definition tables")
        
        if dl_sections > pm_sections:
            print(f"✅ Docling found {dl_sections-pm_sections} more section headers")
        
        print("\nVerdict:")
        if dl['chars'] > pm['chars'] * 1.1 and dl_tables > pm_tables:
            print("  🎯 Docling is recommended — better structure extraction")
        elif abs(dl['chars'] - pm['chars']) < pm['chars'] * 0.1:
            print("  🎯 Similar quality — use PyMuPDF4LLM (faster)")
        else:
            print("  🎯 Test with your specific use case before deciding")
    
    elif results['pymupdf']['success']:
        print("\n✅ PyMuPDF4LLM works — use this for now")
        print("   Install Docling later for comparison:")
        print("   uv add docling --package elt-llm-ingest")
    
    else:
        print("\n❌ Both parsers failed — check PDF file path and format")
    
    print()


def main():
    """Run comparison on FA Handbook."""
    pdf_path = Path("~/Documents/__data/resources/thefa/FA_Handbook_2025-26.pdf").expanduser()
    output_dir = Path("~/Documents/__data/resources/thefa/compare_output").expanduser()
    
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        return
    
    compare_parsers(str(pdf_path), str(output_dir))


if __name__ == "__main__":
    main()
