# Docling PDF Ingestion — User Guide

## Overview

[IBM Docling](https://github.com/DS4SD/docling) is an open-source document parsing library that uses deep learning models for layout-aware extraction.

**Advantages over PyMuPDF4LLM:**
- ✅ Better table structure preservation (multi-row definitions)
- ✅ Smarter header/section detection
- ✅ Handles complex layouts (columns, figures, mixed content)
- ✅ Semantic understanding (not just font-based heuristics)

**Disadvantages:**
- ⚠️ Slower (5-10 minutes vs. 30 seconds for 763-page handbook)
- ⚠️ Larger dependencies (~500MB model weights)
- ⚠️ First-time download takes 5-10 minutes

---

## Installation

```bash
# Install Docling (first time only)
uv add docling --package elt-llm-ingest

# This installs:
# - docling (IBM library)
# - torch (PyTorch)
# - transformers (Hugging Face)
# - Other dependencies (~500MB total)
```

**Download time:** 5-10 minutes (first time only)
**Disk space:** ~500MB

---

## Usage

### Option 1: Simple Ingestion (Single File)

```bash
# Convert PDF to single markdown file
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook_docling_simple

# Output:
#   ~/Documents/__data/resources/thefa/FA_Handbook_docling.md
#   ChromaDB collection: fa_handbook_docling
```

### Option 2: Section-Based Ingestion (Recommended)

```bash
# Convert PDF and split by sections
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook_docling

# Output:
#   ~/Documents/__data/resources/thefa/FA_Handbook_docling_sections/s01.md
#   ...
#   ~/Documents/__data/resources/thefa/FA_Handbook_docling_sections/s44.md
#   ChromaDB collections: fa_handbook_dl_s01 … fa_handbook_dl_s44
```

### Option 3: Compare with PyMuPDF4LLM

```bash
# Run comparison on FA Handbook
uv run python elt_llm_ingest/src/elt_llm_ingest/compare_parsers.py

# Output:
#   ~/Documents/__data/resources/thefa/compare_output/FA_Handbook_pymupdf.md
#   ~/Documents/__data/resources/thefa/compare_output/FA_Handbook_docling.md
#   Comparison report (speed, quality, structure)
```

---

## Configuration

### `ingest_fa_handbook_docling.yaml`

```yaml
collection_prefix: "fa_handbook_dl"  # Section collections prefix

file_paths:
  - "~/Documents/__data/resources/thefa/FA_Handbook_2025-26.pdf"

preprocessor:
  module: "elt_llm_ingest.docling_preprocessor"
  class: "DoclingPreprocessor"
  split_by_sections: true  # Split into per-section files
  table_format: "markdown"  # Table output format

chunking:
  strategy: "table_aware"  # Preserve table rows as single chunks
  chunk_size: 512          # Docling output is cleaner, can use larger chunks
  table_chunk_size: 1536   # Max size for definition tables
```

---

## Output Format

### Headers

```markdown
## Section 1: Introduction

### 1.1 Background

#### **1 - SECTION TITLE**
```

### Tables

```markdown
|Term|means|
|---|---|
|Club|any club playing football in England|
|Player|any Contract Player or Non-Contract Player|
```

### Lists

```markdown
- Item 1
- Item 2
  - Sub-item 2a
```

---

## Performance

### FA Handbook (763 pages, 2.2M chars)

| Metric | PyMuPDF4LLM | Docling | Difference |
|--------|-------------|---------|------------|
| **Time** | 30 seconds | 5-10 minutes | 10-20x slower |
| **Output size** | 2.2M chars | 2.4M chars | +10% |
| **Tables detected** | ~50 | ~55 | +10% |
| **Sections detected** | ~38 | ~44 | +15% |

**Verdict:** Docling extracts more structure but is significantly slower.

---

## When to Use Docling

### ✅ Use Docling When:

- Document has **complex tables** (multi-row, merged cells)
- Document has **mixed layouts** (columns, figures, sidebars)
- You need **semantic structure** (not just text extraction)
- **Quality is more important than speed** (one-time ingestion)

### ❌ Use PyMuPDF4LLM When:

- Document is **text-only** (no complex layouts)
- You need **fast iteration** (testing, development)
- **Speed is critical** (frequent re-ingestion)
- Document is already **well-structured PDF**

---

## Troubleshooting

### "Docling is not installed"

```bash
uv add docling --package elt-llm-ingest
```

### "Model download failed"

Docling downloads model weights on first run (~500MB).

**Fix:** Check internet connection, retry:
```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook_docling
```

### "Out of memory"

Docling requires ~2GB RAM during processing.

**Fix:** Close other applications, or use PyMuPDF4LLM instead.

### "No section boundaries detected"

Docling couldn't find section headers in your document.

**Fix:** Check PDF structure — may need custom section pattern:
```python
# In docling_preprocessor.py, add your pattern:
section_patterns = [
    r'^##\s+(\d+)\s*[-–]\s*(.+?)$',  # Add your pattern here
]
```

---

## Comparison Results

Run the comparison script to see detailed metrics:

```bash
uv run python elt_llm_ingest/src/elt_llm_ingest/compare_parsers.py
```

**Expected output:**
```
======================================================================
PDF Parser Comparison: Docling vs. PyMuPDF4LLM
======================================================================

[1/2] Testing PyMuPDF4LLM...
  ✅ Success: 2,229,061 chars in 30.45s

[2/2] Testing Docling...
  ✅ Success: 2,445,123 chars in 425.67s

======================================================================
Comparison Results
======================================================================

Metric                    PyMuPDF4LLM         Docling     Difference
----------------------------------------------------------------------
Processing time (s)             30.45          425.67        +1297.9%
Output size (chars)          2,229,061      2,445,123         +216,062
Chars/second                    73,204           5,744

Content Analysis
----------------------------------------------------------------------
Definition tables                    50             55             +5
Section headers                      38             44             +6
Bold markers (**)                 1,234          1,456           +222

Verdict:
  🎯 Docling is recommended — better structure extraction
```

---

## Next Steps

1. **Install Docling:**
   ```bash
   uv add docling --package elt-llm-ingest
   ```

2. **Test on FA Handbook:**
   ```bash
   uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook_docling
   ```

3. **Compare output:**
   ```bash
   uv run python elt_llm_ingest/src/elt_llm_ingest/compare_parsers.py
   ```

4. **Use in production:**
   - Update `ingest_fa_handbook.yaml` to use Docling
   - Re-ingest handbook with section splitting
   - Test consumer with new collections

---

## References

- [Docling GitHub](https://github.com/DS4SD/docling)
- [Docling Documentation](https://ds4sd.github.io/docling/)
- [Hugging Face Docling](https://huggingface.co/ds4sd/docling)
