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

**Tool**: IBM Docling (`DoclingPreprocessor`) — deep-learning layout analysis, **not LLM-based**

**Process**:
1. PDF → per-section Markdown via Docling StandardPipeline (DocLayNet + TableFormer models)
2. Section boundaries detected from headings; each section → separate ChromaDB collection
3. Running-header artefacts (repeated section title on each page) collapsed automatically
4. Tables preserved as markdown pipe-delimited rows

**Performance**:
- FA Handbook 2025-26: 2.5M chars in ~250 seconds
- First run downloads DocLayNet + TableFormer models (~200MB to `~/.cache/docling/`) — fully offline thereafter
- Section files cached at `_section_splits/` — subsequent runs skip Docling conversion

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.docling_preprocessor"
  class: "DoclingPreprocessor"
  split_by_sections: true
```

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

**Outputs**: `<stem>_model.json` (175 entities for direct JSON lookup), `<stem>_entities.md` and `<stem>_relationships.md` (ingested into ChromaDB for semantic search). See [elt_llm_ingest/ARCHITECTURE.md](elt_llm_ingest/ARCHITECTURE.md) for full preprocessor output details.

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

**Join Pattern** (Conceptual Model ↔ Inventory): entities from `_model.json` are joined to `_inventory.json` via `fact_sheet_id` in O(1) dictionary lookup. See §3.4 for the JSON sidecar rationale.

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
| LLM | Ollama | `qwen3.5:9b` |
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
| `*_model.json` | LeanIX XML | 175 entities: domain, subtype, fact_sheet_id |
| `*_inventory.json` | LeanIX Excel | 1424 fact sheets keyed by fact_sheet_id |

---

## 6. Consumer Layer

### 6.1 Primary Consumer: fa_consolidated_catalog.py

Generates a consolidated catalog: entities loaded directly from `_model.json`, inventory descriptions looked up from `_inventory.json` by `fact_sheet_id`, and FA Handbook governance context retrieved via RAG+LLM. Output: `.tmp/fa_consolidated_catalog.json`.

See [elt_llm_consumer/ARCHITECTURE.md](elt_llm_consumer/ARCHITECTURE.md) for the full 7-step pipeline detail.

### 6.2 Supporting Consumers

Three additional consumers — `fa_handbook_model_builder`, `fa_coverage_validator`, and `fa_leanix_model_validate` — support gap analysis, coverage scoring, and JSON diagnostics respectively.

See [elt_llm_consumer/README.md](elt_llm_consumer/README.md) for the full consumer scripts reference including entry points and runtimes.

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

**A:** First run downloads Docling's DocLayNet + TableFormer models (~200MB from HuggingFace, cached at `~/.cache/docling/`). All subsequent runs are fully offline. See [elt_llm_ingest/ARCHITECTURE.md](elt_llm_ingest/ARCHITECTURE.md) for full ingestion performance details.

**If you see HuggingFace errors after first run**, they're from:
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

### Q: Should I use Marker instead of Docling?

**A:** Probably not — Docling is working well and already handles the FA Handbook tables correctly.

| Aspect | Docling (current) | Marker |
|--------|-------------------|--------|
| **Your FA Handbook** | ✅ 2.5M chars, ~250s | Similar quality |
| **Internet required** | ⚠️ First run only (~200MB models) | ⚠️ First run only |
| **GPU required** | ❌ No (MPS/CPU) | ✅ Recommended |
| **Disk space** | ~200MB (`~/.cache/docling/`) | ~2-5GB |
| **Tables/layout** | ✅ Excellent (TableFormer) | ✅ Excellent |
| **LLM enhancement** | ❌ No | ✅ Optional |

**Use Marker if:**
- You have **scanned PDFs** (OCR needed)
- You have a **GPU** and want LLM-enhanced extraction

**Try Marker** (optional):
```bash
uv add marker-pdf --package elt-llm-ingest
# Then test on one chapter and compare output quality
```

### Q: Why does the consumer use direct JSON lookup for LeanIX data, and how do the XML and Excel datasets join?

**A:** LeanIX data uses **direct JSON sidecars** (not RAG) for deterministic, O(1) access. See §3.4 for the full rationale and when-to-use guide.

The two sidecars join on **`fact_sheet_id`**: `_model.json` (entities from XML) and `_inventory.json` (fact sheets from Excel, keyed by `fact_sheet_id`). Only the FA Handbook (unstructured PDF) requires RAG+LLM.

---

## 9. References

- [README.md](README.md) — Quick start
- [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) — Stakeholder presentation
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy
- [ORCHESTRATION.md](ORCHESTRATION.md) — Workflow
- [elt_llm_consumer/README.md](elt_llm_consumer/README.md) — Consumer documentation
