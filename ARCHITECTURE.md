# ELT LLM RAG Architecture

**Workspace**: `elt_llm_rag`  
**Purpose**: Technical architecture documentation

**See also**:
- [README.md](README.md) — Quick start and module overview
- [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) — Stakeholder presentation
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy details
- [ORCHESTRATION.md](ORCHESTRATION.md) — Workflow documentation

---

## Table of Contents

- [1. System Architecture](#1-system-architecture)
- [2. Module Structure](#2-module-structure)
- [3. Ingestion Techniques](#3-ingestion-techniques)
- [4. Technology Stack](#4-technology-stack)
- [5. RAG Pipeline](#5-rag-pipeline)
- [6. Consumer Layer](#6-consumer-layer)
- [7. Delivery Roadmap](#7-delivery-roadmap)
- [8. FAQ](#8-faq)
- [9. References](#9-references)

---

## 1. System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Knowledge Sources                        │
├─────────────────┬─────────────────┬─────────────────┬───────────┤
│   FA Handbook   │    LeanIX XML   │   DAMA-DMBOK    │   FDM     │
│   (PDF/HTML)    │  (draw.io)      │   (PDF)         │ (Excel)   │
└────────┬────────┴────────┬────────┴────────┬────────┴────┬─────┘
         │                 │                 │             │
         ↓                 ↓                 ↓             ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Ingestion Layer                               │
│  elt_llm_ingest: Chunk → Embed → ChromaDB + DocStore            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    RAG Collections                               │
│  ChromaDB: fa_handbook, fa_leanix_*, dama_dmbok, ...            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     Query Layer                                  │
│  elt_llm_query: BM25 + Vector → Rerank → LLM Synthesis          │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    Consumer Layer                                │
│  elt_llm_consumer: fa_consolidated_catalog.py + others          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Module Structure

```
elt_llm_rag/
├── elt_llm_core/           # Shared RAG infrastructure
│   ├── config.py           # YAML configuration
│   ├── vector_store.py     # ChromaDB client
│   ├── models.py           # Ollama models
│   └── query_engine.py     # Base query engine
│
├── elt_llm_ingest/         # Document ingestion
│   ├── runner.py           # Ingestion runner
│   ├── preprocessor.py     # Preprocessor framework
│   ├── doc_leanix_parser.py # LeanIX XML parser
│   └── config/             # Ingestion configs
│
├── elt_llm_query/          # Query interface
│   ├── runner.py           # Query runner
│   ├── query.py            # Single/multi-collection queries
│   └── llm_rag_profile/    # Query profiles
│
├── elt_llm_api/            # Gradio GUI + API
│   └── app.py              # Gradio web application
│
└── elt_llm_consumer/       # Output generators
    ├── fa_consolidated_catalog.py  # Target output (primary)
    ├── fa_handbook_model_builder.py
    └── fa_coverage_validator.py
```

---

## 3. Ingestion Techniques

### 3.1 PDF Processing (FA Handbook)

**Tool**: `pymupdf4llm` (PyMuPDF) — **not LLM-based**

**Process**:
1. PDF → Markdown conversion using layout-aware extraction
2. Preserves section hierarchy as headings
3. Handles multi-column layouts with correct reading order
4. Extracts tables as structured Markdown

**Performance**:
- ~1 second per page
- FA Handbook 2025-26: 2.2M chars in 64 seconds
- No internet access required, no model downloads

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "PyMuPDFPreprocessor"
```

**Why not LLM-based extraction?**
- PDFs are text-based (not scanned) — no OCR needed
- pymupdf4llm is faster, simpler, and fully local
- LLM enhancement (e.g., Marker) only beneficial for scanned PDFs or complex tables

---

### 3.2 LeanIX draw.io Conceptual Model (XML)

**Tool**: Custom XML parser (`LeanIXExtractor` in `doc_leanix_parser.py`)

**Process**:
1. Parse draw.io XML to extract `object` elements with `type="factSheet"`
2. Detect domain groups (both Type 1 bare `mxCell` and Type 2 object-wrapped groups)
3. Extract entities with hierarchy:
   - **Domain**: Top-level group (e.g., "AGREEMENTS", "PARTY")
   - **Subtype**: Visual subgroup within domain (e.g., "Static Data / Time Bounded Groupings")
   - **Entity**: Leaf fact sheet node
4. Extract relationships with cardinality from ER notation arrows
5. Handle nested groups (e.g., subgroups within subgroups)

**Hierarchy Detection Algorithm**:
- Group containers detected via `style="group"` in `mxCell` elements
- Two types supported:
  - Type 1: Bare `<mxCell style="group" vertex="1" parent="1"/>`
  - Type 2: Object-wrapped `<object><mxCell style="group".../></object>` (e.g., PARTY)
- Subgroup assignment via geometry analysis (parent chain traversal)
- Domain/subtype entity labels excluded from leaf entity list (container labels only)

**Outputs**:
| File | Purpose | Consumers |
|------|---------|-----------|
| `<stem>_model.json` | Structured JSON: 177 entities with domain, subtype, fact_sheet_id | Direct JSON lookup (no RAG) |
| `<stem>_entities.md` | Per-entity Markdown (one `##` heading per entity) | ChromaDB: `{prefix}_entities` |
| `<stem>_relationships.md` | Per-relationship Markdown | ChromaDB: `{prefix}_relationships` |

**JSON Schema** (`_model.json`):
```json
{
  "metadata": {
    "model_name": "FA Enterprise Conceptual Data Model",
    "source_file": "...xml",
    "entity_count": 177,
    "relationship_count": 89
  },
  "entities": [
    {
      "domain": "AGREEMENTS",
      "domain_fact_sheet_id": "uuid-...",
      "subtype": "Time Bounded Groupings",
      "subtype_fact_sheet_id": "uuid-...",
      "entity_name": "Contract",
      "fact_sheet_id": "uuid-...",
      "fact_sheet_type": "DataObject"
    }
  ],
  "relationships": [...]
}
```

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "json_md"  # Recommended: JSON sidecar + Markdown for RAG
  collection_prefix: "fa_leanix_dat_enterprise_conceptual_model"
```

---

### 3.3 LeanIX Excel Asset Inventory

**Tool**: `openpyxl` for Excel parsing

**Process**:
1. Read all fact sheets from first non-ReadMe sheet (timestamp-named export)
2. Group by `type` field (DataObject, Interface, Application, etc.)
3. Generate per-type Markdown files (split mode)
4. Write `_inventory.json` sidecar keyed by `fact_sheet_id`

**Fact Sheet Types Supported**:
| Type | Collection Suffix | Count (example) |
|------|-------------------|-----------------|
| DataObject | `dataobject` | 229 |
| Interface | `interface` | 271 |
| Application | `application` | 215 |
| BusinessCapability | `capability` | 272 |
| Organization | `organization` | 115 |
| ITComponent | `itcomponent` | 180 |
| Provider | `provider` | 74 |
| Objective | `objective` | 59 |

**Outputs**:
| File | Purpose | Consumers |
|------|---------|-----------|
| `_inventory.json` | Fact sheets keyed by `fact_sheet_id` | Direct O(1) lookup (no RAG) |
| `{type}.md` (8 files) | Per-type Markdown | ChromaDB: `fa_leanix_global_inventory_{type}` |

**Join Pattern** (Conceptual Model ↔ Inventory):
```python
# Consumer code pattern (fa_consolidated_catalog.py)
inventory = load_json("_inventory.json")["fact_sheets"]
for entity in entities:  # from _model.json
    fsid = entity["fact_sheet_id"]
    entity["leanix_description"] = inventory.get(fsid, {}).get("description")
```

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXInventoryPreprocessor"
  output_format: "split"
  collection_prefix: "fa_leanix_global_inventory"
```

---

### 3.4 JSON Sidecar Pattern

**Motivation**: Structured data (LeanIX model, inventory) should not use RAG for lookups.

**Pattern**:
1. Ingestion writes structured JSON next to source file
2. Consumers read JSON directly (deterministic, O(1) lookup)
3. Markdown variants ingested into ChromaDB for semantic search only

**Benefits**:
- ✅ Deterministic: Exact `fact_sheet_id` matching
- ✅ Fast: O(1) dictionary lookup vs. ~15s per RAG query
- ✅ Accurate: Canonical join key preserved

**When to use RAG vs. JSON sidecar**:
| Data Type | Approach | Reason |
|-----------|----------|--------|
| LeanIX Model (entities, relationships) | JSON sidecar | Structured, canonical IDs |
| LeanIX Inventory (fact sheets) | JSON sidecar | Structured, join by `fact_sheet_id` |
| FA Handbook (PDF) | RAG + LLM | Unstructured text, definitions, governance rules |
| DAMA-DMBOK (PDF) | RAG + LLM | Unstructured reference material |

---

## 4. Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| Vector Store | ChromaDB | Persistent, tenant/database isolation |
| Embeddings | Ollama | `nomic-embed-text` (768 dims) |
| LLM | Ollama | `qwen2.5:14b` (8K context) |
| Retrieval | LlamaIndex | BM25 + Vector hybrid |
| Reranking | Embedding or Cross-encoder | Cosine similarity or CrossEncoder (top-20 → top-8) |
| Dependency Mgmt | uv | Python 3.11-3.13 |

---

## 5. RAG Pipeline

### 5.1 Retrieval Flow

```
Query → Multi-query expansion → Hybrid Retrieval (BM25 + Vector)
      → Embedding or Cross-encoder Reranker + MMR diversity
      → Lost-in-middle reorder → LLM Synthesis → Structured output
```

See [RAG_STRATEGY.md](RAG_STRATEGY.md) for full pipeline detail, config knobs, and performance characteristics.

### 5.2 Collection Structure

| Collection | Source | Used for |
|------------|--------|---------|
| `fa_handbook` | FA Handbook PDF | RAG+LLM — definitions, governance rules |
| `fa_leanix_dat_enterprise_conceptual_model_*` | LeanIX XML | Query UI / semantic search only |
| `fa_leanix_global_inventory_*` | LeanIX Excel | Query UI / semantic search only |
| `dama_dmbok` | DAMA-DMBOK PDF | RAG+LLM — data management reference |

**JSON sidecars** (written next to source files during ingestion, used by consumers directly):

| File | Source | Content |
|------|--------|---------|
| `*_model.json` | LeanIX XML | 177 entities: domain, subtype, fact_sheet_id |
| `*_inventory.json` | LeanIX Excel | 1424 fact sheets keyed by fact_sheet_id |

---

## 6. Consumer Layer

### 6.1 Primary Consumer: fa_consolidated_catalog.py

**Purpose**: Generate consolidated catalog — entities enriched with inventory descriptions and Handbook context.

**Process**:
1. Load entities from `_model.json` (direct, no RAG)
2. Inventory descriptions via `fact_sheet_id` lookup in `_inventory.json` (direct, no RAG)
3. Scan Handbook docstore → defined terms
4. Name-match terms → model entities (deterministic, no LLM)
5. RAG+LLM → Handbook context per entity (formal definition, governance)
6. Load relationships from `_model.json`
7. Consolidate → JSON output

**Command**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
```

**Output**: `.tmp/fa_consolidated_catalog.json`

**Docs**: [elt_llm_consumer/ARCHITECTURE.md](elt_llm_consumer/ARCHITECTURE.md)

### 6.2 Supporting Consumers

| Consumer | Purpose | When to Use |
|----------|---------|-------------|
| `fa_handbook_model_builder` | Handbook-only entity/relationship discovery | Gap analysis — what does the handbook describe that isn't in the model? |
| `fa_coverage_validator` | Coverage scoring (model entities vs handbook) | Model refinement — which entities have strong/thin/absent handbook coverage? |
| `fa_leanix_model_validate` | Fast JSON diagnostic | Regression check after re-ingesting LeanIX XML |

---

## 7. Delivery Roadmap

Phase 1 (Data Asset Catalog) is complete. Phases 2–5 (Purview, Erwin LDM, Intranet, MS Fabric/Copilot) are planned.

See [ORCHESTRATION.md](ORCHESTRATION.md) for full phase detail, runbooks, and current status.

---

## 8. FAQ

### Q: Why not use Ollama Modelfiles instead of YAML profiles?

**A:** Ollama Modelfiles and YAML profiles serve different purposes:

| YAML Profile (`llm_rag_profile/*.yaml`) | Ollama Modelfile |
|------------------------------------------|------------------|
| Configures **LlamaIndex** (Python app) | Configures **Ollama server** (model container) |
| Sets retrieval params (`similarity_top_k`, `use_reranker`) | Sets model params (`temperature`, `top_p`) |
| Defines system prompts at **query time** | Bakes system prompts **into the model** |
| Runtime configuration | Build-time configuration |

**When Modelfiles would help:**
- Multiple teams need the same model with different baked-in behaviors
- You want to distribute pre-configured models (e.g., "dama-expert" model)
- Different prompt templates per model (not per query)

**Why YAML profiles are better for this project:**
- ✅ System prompts can change **per query** without rebuilding models
- ✅ Retrieval settings are LlamaIndex-specific, not Ollama-specific
- ✅ One model serves multiple profiles (FA, DAMA, etc.)

### Q: Does PDF processing require HuggingFace or internet access?

**A:** No — the system uses **`pymupdf4llm`** (PyMuPDF) for PDF-to-Markdown conversion, which is 100% local:

```yaml
# ingest_fa_handbook.yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "PyMuPDFPreprocessor"
```

**Real-world performance** (FA Handbook 2025-26 PDF):
```
PDF → Markdown: 2.2M chars in 64 seconds (~1s/page)
Chunks: 3,375 nodes
Embeddings: 94 seconds via Ollama (nomic-embed-text)
Total: ~3 minutes
Internet: ❌ No
HuggingFace: ❌ No
```

**If you see HuggingFace errors**, they're from:
- **Cross-encoder reranker** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) — optional, uses `sentence-transformers`
- **Not PDF processing**

**Fix:** Pre-download once or disable cross-encoder:
```bash
# Option 1: Pre-download (one-time)
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Option 2: Use embedding reranker (Ollama, fully local)
# In rag_config.yaml:
query:
  reranker_strategy: "embedding"  # Instead of "cross-encoder"
```

### Q: Should I use Marker instead of pymupdf4llm?

**A:** Probably not — `pymupdf4llm` is working well for your FA Handbook PDF.

| Aspect | pymupdf4llm (current) | Marker |
|--------|----------------------|--------|
| **Your FA Handbook** | ✅ 2.2M chars, 3 min total | Similar quality |
| **Internet required** | ❌ No | ⚠️ First run only (model download) |
| **GPU required** | ❌ No | ✅ Recommended (3.5-5GB VRAM) |
| **Disk space** | ~50MB | ~2-5GB (Surya + Texify models) |
| **Speed** | Fast (~1s/page) | Similar with GPU, slower on CPU |
| **Tables/layout** | Good | Better (but FA Handbook is simple) |
| **LLM enhancement** | ❌ No | ✅ Optional (works with Ollama) |

**Use Marker if:**
- You have **scanned PDFs** (OCR needed)
- **Complex multi-column layouts** or heavy tables
- You have a **GPU** and want better table extraction

**Stick with pymupdf4llm if:**
- PDFs are **text-based** (like FA Handbook)
- You want **simple, fast** conversion
- You don't want GPU dependencies

**Try Marker** (optional):
```bash
uv add marker-pdf --package elt-llm-ingest
# Then test on one chapter and compare output quality
```

### Q: Why does the consumer use direct JSON lookup for LeanIX data instead of RAG?

**A:** The consolidated catalog uses **direct JSON sidecars** for LeanIX data (not RAG) because:

- **Deterministic**: JSON lookup is exact — no retrieval ambiguity
- **Fast**: O(1) dictionary lookup vs. ~15s per RAG query
- **Accurate**: `fact_sheet_id` is the canonical join key

**Data flow:**
```
Ingestion: LeanIX XML → _model.json (sidecar)
           LeanIX Excel → _inventory.json (sidecar)

Consumer:  Read _model.json → entities list
           Read _inventory.json → dict lookup by fact_sheet_id
```

Only the FA Handbook (unstructured PDF) requires RAG+LLM.

### Q: How do the LeanIX XML and Excel datasets join?

**A:** They join on **`fact_sheet_id`**:

1. **Ingestion** writes JSON sidecars:
   - `LeanIXPreprocessor` → `_model.json` with entities containing `fact_sheet_id`
   - `LeanIXInventoryPreprocessor` → `_inventory.json` keyed by `fact_sheet_id`

2. **Consumer** performs O(1) lookup:
   ```python
   inventory = load_inventory_from_json("_inventory.json")
   for entity in entities:
       fsid = entity["fact_sheet_id"]
       entity["leanix_description"] = inventory.get(fsid, {}).get("description")
   ```

No RAG, no LLM — pure dictionary lookup.

---

## 9. References

- [README.md](README.md) — Quick start
- [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) — Stakeholder presentation
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy
- [ORCHESTRATION.md](ORCHESTRATION.md) — Workflow
- [elt_llm_consumer/README.md](elt_llm_consumer/README.md) — Consumer documentation
