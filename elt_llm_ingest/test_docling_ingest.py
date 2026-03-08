"""
Test: Docling PDF ingestion.

Uses Docling's StandardPipeline — the only valid pipeline for PDFs. Docling's
SimplePipeline only works for declarative formats (Word, PPTX, HTML). For PDFs,
the StandardPipeline downloads two ML models from HuggingFace on first run
(DocLayNet for layout, TableFormer for tables, ~200MB total), then caches them.

Run (ad-hoc, without adding to project deps permanently):
    uv run --with docling python elt_llm_ingest/test_docling_ingest.py

Or install docling first:
    uv add docling --dev
    uv run python elt_llm_ingest/test_docling_ingest.py

What this tests:
    1. Conversion quality — headings, sections, subsections extracted
    2. Table detection — how many tables found, are definition tables preserved
    3. Section hierarchy — can we split into subsections (not just top-level sections)?
    4. Chunk suitability — are chunks a natural size for RAG without aggressive splitting?
    5. Comparison metrics vs current pymupdf4llm output
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

FA_HANDBOOK_PDF = Path("~/Documents/__data/resources/thefa/FA_Handbook_2025-26.pdf").expanduser()

# Current pymupdf4llm output for comparison (if it exists)
FA_HANDBOOK_MD = Path(
    "~/Documents/__data/resources/thefa/FA_Handbook_2025-26_processed_clean.md"
).expanduser()

OUTPUT_DIR = Path(__file__).parent / "_docling_test_output"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_prerequisites() -> bool:
    """Verify PDF exists and docling is importable."""
    ok = True
    if not FA_HANDBOOK_PDF.exists():
        print(f"[ERROR] PDF not found: {FA_HANDBOOK_PDF}")
        ok = False
    try:
        import docling  # noqa: F401
        try:
            from importlib.metadata import version
            print(f"[OK]    docling importable (version: {version('docling')})")
        except Exception:
            print("[OK]    docling importable")
    except ImportError:
        print("[ERROR] docling not installed.")
        print("        Run:  uv run --with docling python elt_llm_ingest/test_docling_ingest.py")
        ok = False
    return ok


def _build_converter():
    """
    Build a DocumentConverter using Docling's StandardPipeline for PDFs.

    NOTE: SimplePipeline in Docling is only for declarative formats (Word, PPTX, HTML)
    where structure is embedded in the file format. PDFs ALWAYS require StandardPipeline.

    StandardPipeline downloads two ML models from HuggingFace on first run (~200MB total),
    then caches them at ~/.cache/docling/ for all subsequent runs:
      - DocLayNet: layout analysis (detects headings, paragraphs, tables, figures)
      - TableFormer: table structure recognition (row/column structure)

    We disable OCR (do_ocr=False) since the FA Handbook is a digital PDF — not scanned.
    Table structure is enabled (do_table_structure=True) — this is a key advantage over
    pymupdf4llm, which only detects pipe-delimited table patterns in text.

    Models are cached after the first download — subsequent runs are fully offline.
    """
    from docling.document_converter import DocumentConverter, PdfFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = False              # FA Handbook is digital — no OCR needed
    pipeline_options.do_table_structure = True   # Enable TableFormer — key benefit vs pymupdf4llm

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    print("[OK]    Using StandardPipeline (do_ocr=False, do_table_structure=True)")
    print("[INFO]  First run will download DocLayNet + TableFormer models from HuggingFace (~200MB)")
    print("[INFO]  Subsequent runs use cached models at ~/.cache/docling/")
    return converter, "StandardPipeline"


def _convert_pdf(converter, pdf_path: Path):
    """Run docling conversion and return the ConversionResult."""
    print(f"\n[...] Converting {pdf_path.name} — this may take 30-120 seconds...")
    result = converter.convert(str(pdf_path))
    print("[OK]    Conversion complete")
    return result


def _analyse_structure(doc) -> dict:
    """
    Inspect the docling Document object and extract structural metrics.

    Returns a dict of counts and samples for reporting.
    """
    metrics = {
        "heading_counts": {},       # {level: count}
        "heading_samples": {},      # {level: [first 3 texts]}
        "table_count": 0,
        "table_samples": [],        # first 3 table cell counts
        "text_block_count": 0,
        "page_count": 0,
    }

    # Iterate over document body items
    for item, _level in doc.iterate_items():
        item_type = type(item).__name__

        if "Heading" in item_type or "SectionHeader" in item_type:
            level = getattr(item, "level", getattr(item, "heading_level", 1))
            metrics["heading_counts"][level] = metrics["heading_counts"].get(level, 0) + 1
            samples = metrics["heading_samples"].setdefault(level, [])
            if len(samples) < 3:
                text = item.text if hasattr(item, "text") else str(item)
                samples.append(text[:80])

        elif "Table" in item_type:
            metrics["table_count"] += 1
            if len(metrics["table_samples"]) < 3:
                try:
                    cell_count = len(list(item.data.grid)) if hasattr(item, "data") else "?"
                    metrics["table_samples"].append(cell_count)
                except Exception:
                    metrics["table_samples"].append("?")

        elif "Text" in item_type or "Paragraph" in item_type:
            metrics["text_block_count"] += 1

    # Page count via document pages attribute
    try:
        metrics["page_count"] = len(doc.pages)
    except AttributeError:
        pass

    return metrics


def _export_outputs(doc, result) -> dict:
    """Export to markdown and JSON, save to OUTPUT_DIR, return file sizes."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    sizes = {}

    # Markdown export
    try:
        md_text = doc.export_to_markdown()
        md_path = OUTPUT_DIR / "fa_handbook_docling.md"
        md_path.write_text(md_text, encoding="utf-8")
        sizes["markdown_chars"] = len(md_text)
        sizes["markdown_path"] = str(md_path)
        print(f"[OK]    Markdown saved → {md_path} ({len(md_text):,} chars)")
    except Exception as e:
        print(f"[WARN]  Markdown export failed: {e}")

    # JSON export (preserves structural metadata)
    try:
        doc_dict = doc.export_to_dict()
        json_path = OUTPUT_DIR / "fa_handbook_docling.json"
        json_path.write_text(json.dumps(doc_dict, indent=2, ensure_ascii=False), encoding="utf-8")
        sizes["json_path"] = str(json_path)
        print(f"[OK]    JSON saved → {json_path}")
    except Exception as e:
        print(f"[WARN]  JSON export failed: {e}")

    return sizes


def _compare_with_pymupdf(md_text: str | None) -> None:
    """
    Compare docling markdown with current pymupdf4llm output.
    Reports heading detection and section boundary differences.
    """
    import re

    if not FA_HANDBOOK_MD.exists():
        print("\n[INFO] No pymupdf4llm markdown found for comparison (run ingest_fa_handbook_pdf first)")
        return

    pymupdf_text = FA_HANDBOOK_MD.read_text(encoding="utf-8")

    # Count section boundaries in each output
    # Current approach: #### **N - SECTION TITLE**
    pymupdf_sections = re.findall(r'^####\s+\*\*\d+\s+[-–]', pymupdf_text, re.MULTILINE)

    print(f"\n--- Comparison vs pymupdf4llm ---")
    print(f"  pymupdf4llm top-level sections found : {len(pymupdf_sections)}")
    print(f"  (expected: 44 for FA Handbook 2025-26)")

    if md_text:
        # Count headings in docling output at each # level
        for level in range(1, 5):
            prefix = "#" * level + " "
            count = len([l for l in md_text.splitlines() if l.startswith(prefix)])
            print(f"  docling H{level} headings               : {count}")

        # Check if docling captures subsection markers
        subsec = re.findall(r'^##+ .+', md_text, re.MULTILINE)
        print(f"  docling total markdown headings      : {len(subsec)}")
        if subsec:
            print(f"  docling heading samples:")
            for h in subsec[:5]:
                print(f"    {h[:80]}")


def _print_report(pipeline_name: str, metrics: dict, sizes: dict) -> None:
    print("\n" + "=" * 60)
    print(f"  DOCLING TEST REPORT — {pipeline_name}")
    print("=" * 60)
    print(f"  Pages detected        : {metrics['page_count']}")
    print(f"  Text blocks           : {metrics['text_block_count']}")
    print(f"  Tables detected       : {metrics['table_count']}")
    if metrics["table_samples"]:
        print(f"  Table cell counts     : {metrics['table_samples']}")
    print()
    print("  Heading levels:")
    for level in sorted(metrics["heading_counts"]):
        count = metrics["heading_counts"][level]
        samples = metrics["heading_samples"].get(level, [])
        print(f"    H{level}: {count} headings")
        for s in samples:
            print(f"      → {s}")

    if sizes.get("markdown_chars"):
        print(f"\n  Markdown output size  : {sizes['markdown_chars']:,} chars")
    print()
    print("  KEY QUESTION — can we subsection-split?")
    total_headings = sum(metrics["heading_counts"].values())
    h1 = metrics["heading_counts"].get(1, 0)
    deeper = total_headings - h1
    if deeper > 10:
        print(f"  YES — {deeper} sub-headings detected (H2+). Subsection splitting is viable.")
    elif total_headings > 0:
        print(f"  PARTIAL — only {total_headings} headings total, mostly at top level.")
    else:
        print("  NO — no headings detected. Structure not preserved.")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Docling No-HuggingFace Ingestion Test")
    print("=" * 60)

    if not _check_prerequisites():
        sys.exit(1)

    converter, pipeline_name = _build_converter()
    result = _convert_pdf(converter, FA_HANDBOOK_PDF)
    doc = result.document

    metrics = _analyse_structure(doc)
    sizes = _export_outputs(doc, result)

    md_text = None
    if "markdown_path" in sizes:
        md_text = Path(sizes["markdown_path"]).read_text(encoding="utf-8")

    _compare_with_pymupdf(md_text)
    _print_report(pipeline_name, metrics, sizes)

    print(f"\nOutputs written to: {OUTPUT_DIR.resolve()}")
    print("Review fa_handbook_docling.md to assess heading/section quality.")


if __name__ == "__main__":
    main()
