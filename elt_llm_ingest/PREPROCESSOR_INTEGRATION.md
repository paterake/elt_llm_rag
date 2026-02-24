# Preprocessor Integration - Implementation Summary

## Overview

Successfully integrated a **preprocessor framework** into the elt_llm_ingest pipeline. This allows files to be transformed before embedding, improving RAG quality for complex formats like LeanIX XML.

## What Was Changed

### 1. Fixed `doc_leanix_parser.py`

**Issues Fixed:**
- ✅ Updated docstring to match actual filename
- ✅ Replaced non-standard `getparent()` with proper parent map approach
- ✅ Added error handling for XML parsing and file not found
- ✅ Improved `save()` method to handle output paths correctly
- ✅ Added `extract_leanix_file()` convenience function for programmatic use

**Location:** `elt_llm_ingest/src/elt_llm_ingest/doc_leanix_parser.py`

---

### 2. Created `preprocessor.py` (New File)

**New Framework Components:**

#### Classes:
- `PreprocessorResult` - Dataclass for preprocessing results
- `BasePreprocessor` - Abstract base class for all preprocessors
- `LeanIXPreprocessor` - Implementation for LeanIX XML → Markdown
- `IdentityPreprocessor` - Pass-through (no transformation)
- `PreprocessorConfig` - Configuration dataclass

#### Functions:
- `get_preprocessor()` - Factory function to create preprocessor instances
- `preprocess_file()` - High-level API to preprocess a file

**Location:** `elt_llm_ingest/src/elt_llm_ingest/preprocessor.py`

---

### 3. Updated `ingest.py`

**Changes:**
- ✅ Added `PreprocessorConfig` import
- ✅ Added `preprocessor` field to `IngestConfig` dataclass
- ✅ Updated `load_documents()` to accept and run preprocessor
- ✅ Updated `run_ingestion()` to pass preprocessor config

**Flow:**
```
File Path → Preprocess (if configured) → Load Documents → Chunk → Embed → Store
```

**Location:** `elt_llm_ingest/src/elt_llm_ingest/ingest.py`

---

### 4. Updated `runner.py`

**Changes:**
- ✅ Added `PreprocessorConfig` import
- ✅ Parse `preprocessor` section from YAML config
- ✅ Pass preprocessor config to `IngestConfig`

**Location:** `elt_llm_ingest/src/elt_llm_ingest/runner.py`

---

### 5. Updated `leanix.yaml` Config

**Before:**
```yaml
collection_name: "leanix"
file_paths:
  - "~/Documents/__data/books/LeanIX_Documentation.pdf"
```

**After:**
```yaml
collection_name: "leanix"

# Preprocessor: Convert LeanIX XML to structured Markdown before embedding
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "markdown"
  output_suffix: "_leanix_processed"
  enabled: true

file_paths:
  - "~/Documents/__data/books/DAT_V00.01_FA_Enterprise_Conceptual_Data_Model.xml"
```

**Location:** `elt_llm_ingest/config/leanix.yaml`

---

### 6. Updated `README.md`

**New Sections Added:**
- ✅ Preprocessor Configuration (comprehensive documentation)
- ✅ How Preprocessing Works (flow diagram)
- ✅ Available Preprocessors table
- ✅ Creating Custom Preprocessors guide
- ✅ Updated Supported Formats section
- ✅ Updated Module Structure diagram

**Location:** `elt_llm_ingest/README.md`

---

## How to Use

### Basic Usage (LeanIX Example)

```bash
# Ingest LeanIX XML files (automatically preprocessed to Markdown)
uv run python -m elt_llm_ingest.runner --cfg leanix
```

### Config Format

```yaml
collection_name: "my_collection"

preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "markdown"  # or "json" or "both"
  output_suffix: "_processed"
  enabled: true

file_paths:
  - "~/path/to/file.xml"
```

### Programmatic Usage

```python
from elt_llm_ingest.preprocessor import LeanIXPreprocessor

preprocessor = LeanIXPreprocessor(output_format="markdown")
result = preprocessor.preprocess(
    input_file="model.xml",
    output_path="output/model_processed"
)

print(result.output_files)  # ['output/model_processed.md']
```

---

## Architecture

### Preprocessor Flow

```
┌─────────────┐
│ XML File    │
│ (LeanIX)    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│ LeanIXPreprocessor      │
│ - Extracts Assets       │
│ - Extracts Relationships│
│ - Outputs Markdown      │
└──────┬──────────────────┘
       │
       ▼
┌─────────────┐
│ Markdown    │
│ (Structured)│
└──────┬──────┘
       │
       ▼
┌─────────────────────────┐
│ Standard Ingestion      │
│ - Chunking              │
│ - Embedding             │
│ - ChromaDB Storage      │
└─────────────────────────┘
```

### Configuration Flow

```
YAML Config
    ↓
runner.py (parses preprocessor section)
    ↓
IngestConfig (holds PreprocessorConfig)
    ↓
run_ingestion()
    ↓
load_documents()
    ↓
preprocess_file() → transforms each file
    ↓
SimpleDirectoryReader → loads transformed files
    ↓
Standard pipeline continues...
```

---

## Testing Results

All imports and configurations tested successfully:

✅ Preprocessor module imports  
✅ Ingest module imports with preprocessor  
✅ Runner module imports  
✅ LeanIX parser imports  
✅ Config loading with preprocessor section  
✅ IngestConfig creation with preprocessor  
✅ Runner --list command  

---

## Extending with Custom Preprocessors

### Step 1: Create Your Preprocessor

```python
# my_package/preprocessors.py
from elt_llm_ingest.preprocessor import BasePreprocessor, PreprocessorResult

class MyCustomPreprocessor(BasePreprocessor):
    def preprocess(self, input_file: str, output_path: str, **kwargs) -> PreprocessorResult:
        # Your transformation logic here
        output_file = f"{output_path}.md"
        
        # ... transform input_file to output_file ...
        
        return PreprocessorResult(
            original_file=input_file,
            output_files=[output_file],
            success=True
        )
```

### Step 2: Configure in YAML

```yaml
preprocessor:
  module: "my_package.preprocessors"
  class: "MyCustomPreprocessor"
  output_format: "markdown"
  enabled: true
```

---

## Benefits

1. **Better Embeddings**: Structured Markdown embeds better than raw XML
2. **Generic Framework**: Works with any file transformation
3. **Config-Driven**: No code changes needed to add new preprocessors
4. **Backward Compatible**: Existing configs without preprocessors work unchanged
5. **Smart Caching**: Hash tracking works on preprocessed output files

---

## Files Modified/Created

| File | Action | Description |
|------|--------|-------------|
| `doc_leanix_parser.py` | Modified | Fixed issues, added convenience function |
| `preprocessor.py` | Created | New preprocessor framework |
| `ingest.py` | Modified | Added preprocessor support |
| `runner.py` | Modified | Parse preprocessor config |
| `leanix.yaml` | Modified | Added preprocessor configuration |
| `README.md` | Modified | Added preprocessor documentation |

---

## Next Steps (Optional Enhancements)

1. **Add more preprocessors**: CSV → Markdown, JSON → Markdown, etc.
2. **Preprocessor chaining**: Run multiple preprocessors in sequence
3. **Output directory config**: Control where preprocessed files are saved
4. **Preprocessor caching**: Skip preprocessing if output already exists
5. **Progress indicators**: Show preprocessing progress in verbose mode
