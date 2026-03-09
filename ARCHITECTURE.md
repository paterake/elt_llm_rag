# ELT LLM RAG Architecture

**Workspace**: `elt_llm_rag`  
**Purpose**: Complete technical architecture and system overview  
**Last Updated**: March 2026

**Start here**: This document tells the complete story — what's built, why, how it works, and key design decisions. Read this first, then dive into module-specific docs for details.

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [1. The Challenge](#1-the-challenge)
- [2. The Solution](#2-the-solution)
- [3. AI Architecture Overview](#3-ai-architecture-overview)
  - [3.1 What is RAG?](#31-what-is-rag)
  - [3.2 What is the LLM?](#32-what-is-the-llm)
  - [3.3 Prompt Engineering](#33-prompt-engineering)
  - [3.4 Custom Code (Non-AI Components)](#34-custom-code-non-ai-components)
  - [3.5 AI vs. Custom Code Summary](#35-ai-vs-custom-code-summary)
- [4. System Architecture](#4-system-architecture)
- [5. Ingestion Layer](#5-ingestion-layer)
  - [5.1 PDF Processing (FA Handbook)](#51-pdf-processing-fa-handbook)
  - [5.2 LeanIX draw.io Conceptual Model](#52-leanix-drawio-conceptual-model)
  - [5.3 LeanIX Excel Asset Inventory](#53-leanix-excel-asset-inventory)
  - [5.4 JSON Sidecar Pattern](#54-json-sidecar-pattern)
- [6. RAG Pipeline](#6-rag-pipeline)
  - [6.1 Retrieval Flow](#61-retrieval-flow)
  - [6.2 Configuration](#62-configuration)
  - [6.3 Example Query Flow](#63-example-query-flow)
- [7. Consumer Layer](#7-consumer-layer)
  - [7.1 Primary Consumer: Consolidated Catalog](#71-primary-consumer-consolidated-catalog)
  - [7.2 Supporting Consumers](#72-supporting-consumers)
- [7.3 Agent Layer: Agentic RAG](#73-agent-layer-agentic-rag)
- [8. Technology Stack](#8-technology-stack)
- [9. Performance Characteristics](#9-performance-characteristics)
- [10. Module Reference](#10-module-reference)
- [11. Delivery Roadmap](#11-delivery-roadmap)
- [12. FAQ](#12-faq)
- [References](#references)

---

## Executive Summary

**Challenge**: Generate a comprehensive business glossary from the FA Handbook, reverse-engineered and mapped to the LeanIX conceptual data model as the frame.

**Solution**: A RAG+LLM platform that:
1. Extracts ~149 defined terms from the FA Handbook
2. Maps each term to LeanIX conceptual model entities (175 entities)
3. Enriches with governance rules, definitions, and relationships
4. Produces review-ready JSON output for stakeholder validation
5. Ready for downstream import (Purview, Erwin LDM, MS Fabric)

**Key Design Principle**: **Hybrid architecture** — only use RAG+LLM where semantic understanding is genuinely needed. Structured data (LeanIX XML/Excel) uses direct JSON lookups (fast, deterministic); unstructured data (FA Handbook PDF) uses RAG+LLM (semantic search).

**Command**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
```

**Output**: `.tmp/fa_consolidated_catalog.json` — your complete glossary and catalogue.

---

## 1. The Challenge

### 1.1 Business Requirements

**Primary Objective**: Generate a comprehensive business glossary from the FA Handbook, mapped to the LeanIX conceptual data model as the organising frame.

**Specific Requirements**:

| # | Requirement | Source | Priority |
|---|-------------|--------|----------|
| 1 | Conceptual model as the organising frame for all artefacts | LeanIX XML | Primary |
| 2 | FA Handbook as SME/business context provider | FA Handbook PDF | Primary |
| 3 | LeanIX Inventory for entity descriptions | LeanIX Excel | Primary |
| 4 | Glossary terms linked to LeanIX Data Objects | Handbook → Model mapping | Primary |
| 5 | Structured export format for downstream import | Purview-ready | Primary |
| 6 | Gap analysis: identify Handbook entities missing from conceptual model | Handbook vs Model comparison | Secondary |
| 7 | Capture governance rules and terms of reference per entity | Handbook extraction | Secondary |

### 1.2 Stakeholder Expectations

- **Data Modelling Team**: Review and validate entity definitions and mappings
- **Business SMEs**: Confirm glossary terms reflect operational reality
- **Data Governance Lead**: Approve governance rules and terms of reference
- **Architecture Review Board**: Endorse conceptual model alignment

### 1.3 Downstream Integration Path

- **Phase 1**: Generate review-ready glossary/catalogue (current deliverable) ✅
- **Phase 2**: Import to Microsoft Purview business glossary + embed in Erwin LDM
- **Phase 3**: Publish to intranet + integrate with MS Fabric semantic model for Copilot

---

## 2. The Solution

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. INGESTION (elt_llm_ingest)                                   │
│    - FA Handbook PDF → fa_handbook collection                   │
│    - LeanIX XML → fa_leanix_dat_enterprise_conceptual_model_*   │
│                → _model.json (JSON sidecar next to source)      │
│    - LeanIX Excel → fa_leanix_global_inventory_*                │
│                   → _inventory.json (JSON sidecar next to source)│
│    Technology: LlamaIndex + ChromaDB (vectorstore + docstore)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. RAG STRATEGY (elt_llm_query)                                 │
│    - Hybrid retrieval: BM25 + Vector                            │
│    - Embedding reranker: nomic-embed-text                       │
│    - LLM synthesis: qwen3.5:9b                                 │
│    (Used only for FA Handbook queries — see Consumer below)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. CONSUMER (elt_llm_consumer)                                  │
│    fa_consolidated_catalog.py — TARGET OUTPUT                   │
│                                                                   │
│    LeanIX Data (direct JSON lookup — no RAG, no LLM):           │
│    - Entities from _model.json                                  │
│    - Inventory descriptions via fact_sheet_id lookup            │
│    - Relationships from _model.json                             │
│                                                                   │
│    Handbook Data (RAG+LLM required — unstructured PDF):         │
│    - Defined terms from docstore scan                           │
│    - Handbook context per entity (formal definition, rules)     │
│                                                                   │
│    Output: fa_consolidated_catalog.json                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Key Design Decision: JSON Sidecars

LeanIX data uses **direct JSON sidecars** (not RAG) because:
- Data is already structured during ingestion
- Deterministic joins via `fact_sheet_id`
- Fast: O(1) lookup vs. ~15s per RAG query

RAG+LLM is used **only for the FA Handbook** (unstructured PDF text).

### 2.3 Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| **Vector Store** | ChromaDB | Persistent, tenant/database isolation |
| **DocStore** | LlamaIndex | Metadata index for structured extraction |
| **Embeddings** | Ollama | `nomic-embed-text` (768 dimensions) |
| **LLM** | Ollama | `qwen3.5:9b` (16K context) |
| **Retrieval** | Hybrid | BM25 + Vector via QueryFusionRetriever |
| **Reranking** | Embedding or Cross-encoder | Cosine similarity or CrossEncoder |
| **Orchestration** | LlamaIndex | Query engine with synthesis |

### 2.4 RAG Strategy

**Why Hybrid Retrieval?**

| Retriever | Strength | Weakness Alone |
|-----------|----------|----------------|
| **Vector (Dense)** | Semantic similarity ("Club" ≈ "Organisation") | Misses exact terms, IDs, version numbers |
| **BM25 (Sparse)** | Exact keyword matches | Misses semantic equivalence |
| **Hybrid (Both)** | Captures both semantic and exact matches | — |

**Reranking Matters**:
- Initial retrieval optimises for **speed** (approximate nearest neighbours)
- Reranking optimises for **relevance** (careful cosine similarity scoring)
- Ensures LLM receives the **most pertinent chunks** for synthesis

**Retrieval Flow**:
```
Query → Hybrid Retrieval (BM25 + Vector) → Top-20 candidates
      → Embedding Reranker (cosine similarity) → Top-8 chunks
      → LLM Synthesis (qwen3.5:9b) → Structured JSON output
```

---

## 3. AI Architecture Overview

This solution combines **AI components** (RAG, LLM, prompts) with **custom code** (ingestion, consumers) to deliver an automated glossary extraction and mapping system.

### 3.1 What is RAG? (Retrieval-Augmented Generation)

**Definition**: RAG is an AI architecture that combines:
- **Retrieval**: Fetching relevant documents/chunks from a knowledge base
- **Generation**: Using an LLM to synthesize answers based on retrieved context

**Why RAG?**
- LLMs have knowledge cutoffs and can't access your private documents
- RAG grounds the LLM in YOUR data (FA Handbook, LeanIX models)
- Reduces hallucinations — LLM only answers based on retrieved evidence
- Enables citation of sources (section numbers, rule numbers)

**Our RAG Implementation**:

```
┌──────────────────────────────────────────────────────────────┐
│ RAG PIPELINE FOR FA HANDBOOK                                 │
│                                                              │
│ 1. INGESTION                                                 │
│    FA Handbook PDF → Docling → per-section Markdown          │
│    Markdown → TableAwareSentenceSplitter → 3,562 chunks     │
│    Chunks → nomic-embed-text → 768-dim vectors              │
│    Vectors + chunks → ChromaDB (vector store + docstore)    │
│                                                              │
│ 2. RETRIEVAL (at query time)                                 │
│    User query → Hybrid search (BM25 + Vector)               │
│    → Top-24 candidates from 3,562 chunks                    │
│    → Embedding reranker (cosine similarity)                 │
│    → Top-8 most relevant chunks                            │
│                                                              │
│ 3. GENERATION                                                │
│    Query + 8 chunks → qwen3.5:9b LLM                       │
│    → Structured response (definition, context, governance)  │
│    → JSON output with citations                             │
└──────────────────────────────────────────────────────────────┘
```

**RAG Configuration** (`elt_llm_ingest/config/rag_config.yaml`):

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `chunking.strategy` | `table_aware` | Preserves table rows as single chunks |
| `chunking.chunk_size` | 256 | Prose chunk size (tokens) |
| `chunking.table_chunk_size` | 1536 | Table row max size (tokens) |
| `query.similarity_top_k` | 8 | Chunks passed to LLM |
| `query.reranker_top_k` | 10 | Chunks after reranking |
| `query.num_queries` | 3 | Query variants for diversity |
| `query.use_hybrid_search` | `true` | BM25 + Vector combined |
| `query.use_mmr` | `true` | Maximal Marginal Relevance (diversity) |

**Key Features**:
- **Hybrid search**: BM25 (keyword) + Vector (semantic) — captures both exact matches and conceptual similarity
- **Reranking**: Initial retrieval optimizes for speed, reranking optimizes for relevance
- **MMR (Maximal Marginal Relevance)**: Prevents near-duplicate chunks from dominating results
- **Table-aware chunking**: FA Handbook definitions table (Rules §8) kept intact — no split definitions

**For a detailed walkthrough of the RAG+LLM flow** (with visual diagrams), see [SOLUTION_OVERVIEW.md](SOLUTION_OVERVIEW.md) Parts 2-3.

See [RAG_STRATEGY.md](RAG_STRATEGY.md) for full pipeline detail, config knobs, and enhancement roadmap.

---

### 3.2 What is the LLM? (Large Language Model)

**Our LLM**: `qwen3.5:9b` via Ollama

| Specification | Value |
|---------------|-------|
| **Model** | Qwen 3.5 (Alibaba) |
| **Parameters** | 9 billion |
| **Context window** | 16,384 tokens |
| **Embedding model** | `nomic-embed-text` (768 dimensions) |
| **Runtime** | Ollama (local, CPU/M3) |

**Why This Model?**
- **Local execution**: No API calls, data stays on-premises
- **9B parameters**: Good balance of quality vs. resource usage (~6.6GB VRAM)
- **16K context**: Can process 8+ retrieved chunks simultaneously
- **Strong reasoning**: Good at extraction, synthesis, and classification tasks

**LLM Tasks in This Solution**:

| Task | Prompt | Output |
|------|--------|--------|
| **Handbook context extraction** | `handbook_context.yaml` | Definition + context + governance |
| **Governance extraction** | `governance_extraction.yaml` | Governance rules only |
| **Domain inference** | `domain_inference.yaml` | Domain/subgroup classification |
| **Relationship extraction** | `entity_relationship.yaml` | Entity-to-entity relationships |

**What the LLM Does NOT Do**:
- ❌ Parse LeanIX XML/Excel (done by custom code)
- ❌ Match handbook terms to entities (done by string matching)
- ❌ Consolidate results (done by Python logic)
- ❌ Store/retrieve vectors (done by ChromaDB)

---

### 3.3 Prompt Engineering

**What is Prompt Engineering?**
Designing input prompts to guide the LLM toward desired outputs. Well-engineered prompts:
- Specify the task clearly
- Provide context and constraints
- Define output format (JSON, sections, etc.)
- Include examples or decision rules

**Our Prompts** (in `elt_llm_consumer/config/prompts/`):

#### 1. `handbook_context.yaml` — Primary Entity Query

**Purpose**: Extract complete terms-of-reference for a conceptual model entity.

**Variables**: `{entity_name}`, `{domain}`

**Output Structure**:
```
FORMAL_DEFINITION: [exact quote or paraphrase]
DOMAIN_CONTEXT: [role in domain, related concepts]
GOVERNANCE: [rules with section/rule citations]
```

**Key Prompt Techniques**:
- **Subtype awareness**: "The FA Handbook may refer to this entity... as 'Contract {entity_name}', 'Registered {entity_name}'..."
- **Citation requirement**: "Cite section and rule numbers where possible"
- **Fallback handling**: "If no handbook rules apply, state 'Not documented in FA Handbook...'"

---

#### 2. `governance_extraction.yaml` — Dedicated Governance Query

**Purpose**: Fallback governance query when primary prompt returns empty/hedged results.

**Variables**: `{entity_name}`

**When Used**:
- Always for `_GOVERNANCE_INTENSIVE_ENTITIES` (Club, Player, Match Official, etc.)
- For other entities when initial governance is empty or starts with "Not documented..."

**Key Prompt Techniques**:
- **Structured coverage**: Lists specific governance types (registration, eligibility, compliance, etc.)
- **Prose output**: Returns governance rules as continuous text (not structured sections)

---

#### 3. `domain_inference.yaml` — HANDBOOK_ONLY Classification

**Purpose**: Classify handbook terms that don't match any conceptual model entity.

**Variables**: `{taxonomy_context}`, `{entity_name}`, `{handbook_definition}`

**Output**: JSON with domain, subgroup, confidence, reasoning

**Decision Logic** (Three-Tier):
```
TIER 1 — Map to existing taxonomy (preferred)
  → inference_tier: "existing"

TIER 2 — Propose new taxonomy
  → inference_tier: "new_proposed"

TIER 3 — Unknown (last resort)
  → inference_tier: "unknown"
```

**Key Prompt Techniques**:
- **Decision process**: Explicit priority order (Tier 1 > Tier 2 > Tier 3)
- **Confidence scoring**: "high | medium | low" based on semantic clarity
- **Alternative consideration**: "alternative_domain" field for ambiguous cases

---

#### 4. `entity_relationship.yaml` — Relationship Extraction

**Purpose**: Extract entity-to-entity relationships from FA Handbook for a domain pair.

**Variables**: `{source_domain}`, `{source_entities}`, `{target_domain}`, `{target_entities}`, `{domain_cardinality}`

**Output**: JSON array of relationship records (forward + inverse pairs)

**Key Prompt Techniques**:
- **Bidirectional requirement**: "return BOTH the forward and inverse directions"
- **Evidence requirement**: "brief quote or paraphrase from the Handbook (max 30 words)"
- **Inference flag**: `inferred: true/false` distinguishes explicit vs. inferred relationships

---

### 3.4 Custom Code (Non-AI Components)

**What Requires Custom Code?**

RAG+LLM handles **unstructured data** (FA Handbook PDF), but **structured data** (LeanIX XML/Excel) requires custom parsing and deterministic logic.

#### Ingestion Layer (`elt_llm_ingest`)

| Component | Purpose | AI or Custom? |
|-----------|---------|---------------|
| `preprocessor.py` | LeanIX XML → Markdown, Excel → Markdown | **Custom** (XML parsing, Excel reading) |
| `docling_preprocessor.py` | PDF → per-section Markdown (Docling) | **Library** (third-party) |
| `chunking.py` | Table-aware sentence splitter | **Custom** (table detection logic) |
| `ingest.py` | Orchestrate ingestion pipeline | **Custom** (LlamaIndex integration) |
| `file_hash.py` | Track file changes for incremental ingestion | **Custom** (hash computation) |

**Key Custom Logic**:

1. **Table-Aware Chunking** (`chunking.py`):
   ```python
   # Detects table content via pipe-delimiter patterns
   if "|" in line:  # Table row detected
       keep_as_single_chunk()  # Up to 1536 tokens
   else:
       standard_sentence_split()  # 256 tokens
   ```

2. **LeanIX Preprocessor** (`preprocessor.py`):
   ```python
   # Parses draw.io XML, extracts entities/relationships
   # Produces: _model.json, _entities.md, _relationships.md
   # Splits by domain for targeted RAG queries
   ```

---

#### Consumer Layer (`elt_llm_consumer`)

| Component | Purpose | AI or Custom? |
|-----------|---------|---------------|
| `fa_consolidated_catalog.py` | Main consolidation logic | **Custom** (orchestration) |
| Step 1: Load entities | Read `_model.json` | **Custom** (JSON parsing) |
| Step 2: Inventory lookup | O(1) dict lookup by fact_sheet_id | **Custom** (deterministic) |
| Step 3: Extract handbook terms | Docstore scan with regex | **Custom** (pattern matching) |
| Step 4: Match terms to entities | Normalized name + alias matching | **Custom** (string matching) |
| Step 5: Handbook context | RAG+LLM per entity | **AI** (uses prompts) |
| Step 6: Load relationships | Read `_model.json` | **Custom** (JSON parsing) |
| Step 7: Consolidate | Merge and classify | **Custom** (business logic) |

**Key Custom Logic**:

1. **Entity Alias Map** (`fa_consolidated_catalog.py`):
   ```python
   _ENTITY_ALIASES = {
       "fa county": ["county association", "county football association"],
       "competition league": ["competition", "league"],
       "match official": ["referee", "assistant referee"],
       # ... 25+ alias mappings
   }
   ```

2. **No-Coverage Exclusions**:
   ```python
   _NO_HANDBOOK_COVERAGE = frozenset([
       "Supplier", "Household", "Business Unit", "Prospect",
       "Customer", "Event Attendee", "Casual & Contingent Labourers",
       "Managed Service Workers",
   ])
   # Skips RAG calls for these — saves 8 LLM calls
   ```

3. **Governance-Intensive Entities**:
   ```python
   _GOVERNANCE_INTENSIVE_ENTITIES = frozenset([
       "Club", "Player", "Match Official", "Club Official",
       "County Association", "Competition", "Competition League", "FA County",
   ])
   # Always runs dedicated governance query for these
   ```

---

### 3.5 AI vs. Custom Code Summary

| Component | AI (RAG+LLM) | Custom Code | Why |
|-----------|--------------|-------------|-----|
| **FA Handbook parsing** | ❌ No | ✅ Yes | PDF → Markdown requires library |
| **FA Handbook chunking** | ❌ No | ✅ Yes | Table detection is rule-based |
| **FA Handbook embedding** | ✅ Yes | ❌ No | nomic-embed-text model |
| **FA Handbook retrieval** | ✅ Yes | ❌ No | Hybrid search (BM25 + Vector) |
| **FA Handbook synthesis** | ✅ Yes | ❌ No | qwen3.5:9b LLM |
| **LeanIX XML parsing** | ❌ No | ✅ Yes | Structured data → custom parser |
| **LeanIX Excel parsing** | ❌ No | ✅ Yes | Structured data → openpyxl |
| **Term matching** | ❌ No | ✅ Yes | String matching + alias map |
| **Domain inference** | ✅ Yes | ❌ No | LLM classification |
| **Consolidation logic** | ❌ No | ✅ Yes | Business rules + merging |
| **Output formatting** | ❌ No | ✅ Yes | JSON structure |

**Design Principle**:
- **AI for unstructured**: RAG+LLM for FA Handbook (PDF text)
- **Custom for structured**: Direct parsing for LeanIX (XML/Excel)
- **Hybrid where needed**: LLM inference for domain classification, custom logic for consolidation

---

## 4. System Architecture

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

## 5. Ingestion Layer

### 5.1 PDF Processing (FA Handbook)

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

See [elt_llm_ingest/ARCHITECTURE.md](elt_llm_ingest/ARCHITECTURE.md) for full ingestion pipeline details.

---

### 5.2 LeanIX draw.io Conceptual Model (XML)

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

**Outputs**: 
- `<stem>_model.json` (175 entities for direct JSON lookup)
- `<stem>_entities.md` and `<stem>_relationships.md` (ingested into ChromaDB for semantic search)

**Configuration**:
```yaml
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "json_md"
  collection_prefix: "fa_leanix_dat_enterprise_conceptual_model"
```

---

### 5.3 LeanIX Excel Asset Inventory

**Tool**: `openpyxl` for Excel parsing

**Process**:
1. Read all fact sheets from first non-ReadMe sheet (timestamp-named export)
2. Group by `type` field (DataObject, Interface, Application, etc.)
3. Generate per-type Markdown files (split mode)
4. Write `_inventory.json` sidecar keyed by `fact_sheet_id`

**Fact Sheet Types**:
| Type | Collection Suffix | Count |
|------|-------------------|-------|
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

**Join Pattern**: Conceptual Model ↔ Inventory via `fact_sheet_id` in O(1) dictionary lookup.

---

### 5.4 JSON Sidecar Pattern

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

## 6. RAG Pipeline

### 6.1 Retrieval Flow

```
Query → Multi-query expansion → Hybrid Retrieval (BM25 + Vector)
      → Embedding or Cross-encoder Reranker + MMR diversity
      → Lost-in-middle reorder → LLM Synthesis → Structured output
```

**Multi-Collection Query**:
When querying across multiple collections (e.g., multiple LeanIX domains):
1. Retrieve `reranker_retrieve_k / num_collections` from each collection
2. Merge all candidates
3. Apply embedding reranker globally
4. Keep top-`reranker_top_k` overall

**Benefit**: Each collection has representation while reranker selects the most relevant overall.

See [RAG_STRATEGY.md](RAG_STRATEGY.md) for full pipeline detail, config knobs, and enhancement roadmap.

---

### 6.2 Configuration

**File**: `elt_llm_ingest/config/rag_config.yaml`

**Key Parameters**:

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `chunking.strategy` | `table_aware` | Preserves table rows as single chunks |
| `chunking.chunk_size` | 256 | Prose chunk size (tokens) |
| `chunking.table_chunk_size` | 1536 | Table row max size (tokens) |
| `query.similarity_top_k` | 8 | Chunks passed to LLM |
| `query.reranker_top_k` | 10 | Chunks after reranking |
| `query.num_queries` | 3 | Query variants for diversity |
| `query.use_hybrid_search` | `true` | BM25 + Vector combined |
| `query.use_mmr` | `true` | Maximal Marginal Relevance (diversity) |
| `query.use_lost_in_middle` | `true` | Reorder chunks for better LLM attention |
| `query.reranker_strategy` | `embedding` | `embedding` or `cross-encoder` |

**Tuning Guide**: See [RAG_TUNING.md](RAG_TUNING.md) for parameter tuning rationale and trade-offs.

---

### 6.3 Example Query Flow

**Query**: "What is a Club, and what governance rules apply?"

**Step-by-Step**:

1. **Consumer script** loads `Club` entity from `_model.json`
   - domain: `PARTY`, fact_sheet_id: `12345`

2. **Inventory lookup**: `_inventory.json["12345"]`
   - → "An organisation affiliated with The Association..."

3. **RAG Query**: `"Club PARTY rules governance obligations"`
   - **BM25** finds chunks with "Club", "organisation", "affiliated"
   - **Vector** finds chunks semantically similar (even if different wording)
   - **Fusion** merges both result sets
   - **Reranker** scores all 20 candidates by cosine similarity
   - **Top-8 chunks** selected

4. **LLM Synthesis**: Prompt + 8 chunks → `qwen3.5:9b` →
   ```json
   {
     "formal_definition": "Club means any club which plays the game of football...",
     "domain_context": "Central entity in PARTY domain, relates to Player, Competition...",
     "governance_rules": "Rule A1: Club must be affiliated. Rule C2: Club must appoint..."
   }
   ```

5. **Consolidation**: All sources merged → `fa_consolidated_catalog.json`

**Total latency**: ~15s retrieval + ~60s LLM = ~75s per entity

---

## 7. Consumer Layer

### 7.1 Primary Consumer: Consolidated Catalog

**File**: `fa_consolidated_catalog.py`  
**Entry point**: `elt-llm-consumer-consolidated-catalog`  
**Runtime**: ~45–60 min for full domain run  
**Output**: `fa_consolidated_catalog.json` — PRIMARY stakeholder review artifact

**7-Step Pipeline**:

```
Step 1: Load Conceptual Model Entities
  Source: _model.json (direct JSON read — no RAG, no LLM)
  Produces: ~175 entities with entity_name, domain, subtype, fact_sheet_id

Step 2: Load Inventory Descriptions
  Source: _inventory.json (O(1) dict lookup — no RAG, no LLM)
  Produces: dict: normalised entity_name → { description, level, status, type }

Step 3: Extract Handbook Defined Terms
  Source: fa_handbook docstore (regex scan — no RAG, no LLM)
  Produces: ~149 dicts: { term, definition }

Step 4: Match Handbook Terms to Model Entities
  Source: handbook_terms + model entity names (dict lookup — no RAG, no LLM)
  Produces: dict: term.lower() → { mapped_entity, domain, mapping_confidence }
  Note: Typically 2–5% match rate (model uses short names, handbook uses qualified names)

Step 5: Extract Handbook Context per Entity  (RAG + LLM)
  Source: fa_handbook ChromaDB + docstore (hybrid search)
  How: For each entity:
       1. Build query: "{entity_name} {domain} rules governance..."
       2. Hybrid retrieval: BM25 + Vector → fusion → embedding reranker
       3. Retrieved chunks + prompt → Ollama → synthesised text
       4. If governance empty, run second dedicated RAG query
  Runtime: ~60–90s per entity
  Produces: dict: entity_name → { formal_definition, domain_context, governance_rules }

Step 6: Load Relationships
  Source: _model.json (direct JSON read — no RAG, no LLM)
  Produces: dict: entity → entity relationships

Step 6b: Extract Handbook Relationship Context  (RAG + LLM)
  Source: relationships + fa_handbook
  How: For each relationship pair, query handbook for context
  Produces: entity_relationships list

Step 7: Consolidate
  Inputs: ALL variables from Steps 1–6
  How: Merge all inputs per entity. Classify each as:
       - BOTH: entity in model AND handbook
       - LEANIX_ONLY: in model only
       - HANDBOOK_ONLY: handbook term with no matching model entity
  Output: fa_consolidated_catalog.json (hierarchical: domain → subtype → entity)
          fa_consolidated_relationships.json
```

**Output Structure** (per entity):
```json
{
  "fact_sheet_id": "12345",
  "entity_name": "Club",
  "domain": "PARTY",
  "subgroup": "Organisation",
  "source": "BOTH",
  "leanix_description": "An organisation affiliated with The Association...",
  "formal_definition": "Club means any club which plays the game of football...",
  "domain_context": "Central entity in PARTY domain, relates to Player, Competition...",
  "governance_rules": "Rule A1: Club must be affiliated. Rule C2: Club must appoint...",
  "review_status": "PENDING",
  "relationships": [...]
}
```

See [elt_llm_consumer/ARCHITECTURE.md](elt_llm_consumer/ARCHITECTURE.md) for the full pipeline detail and output interpretation.

---

### 7.2 Supporting Consumers

| Consumer | Purpose | Runtime | Output |
|----------|---------|---------|--------|
| **fa_handbook_model_builder** | Extract candidate entities from Handbook alone | ~5-7 min | `fa_handbook_candidate_entities.json`, `fa_handbook_candidate_relationships.json`, `fa_handbook_terms_of_reference.json` |
| **fa_coverage_validator** | Validate model coverage against Handbook (no LLM) | ~3-7 min | `fa_coverage_report.json`, `fa_gap_analysis.json` |
| **fa_leanix_model_validate** | JSON diagnostics for LeanIX model | <1 min | Validation report |

**Conceptual Model Enhancement Cycle**:
```
1. Run Handbook Model Builder
   → fa_handbook_candidate_entities.json (what the handbook thinks exists)

2. Run Coverage Validator (--gap-analysis)
   → fa_coverage_report.json (coverage scores)
   → fa_gap_analysis.json (MATCHED / MODEL_ONLY / HANDBOOK_ONLY)

3. Human SME Review
   HANDBOOK_ONLY → add to LeanIX conceptual model
   MODEL_ONLY    → question: technical detail? remove or keep?
   THIN/ABSENT   → rename entity to match handbook terminology?

4. Update LeanIX model, re-run ingestion, repeat from step 2.

5. When model is stable, run Consolidated Catalog for final output.
   → fa_consolidated_catalog.json ← stakeholder review + Purview import
```

**Important caveat**: LLM output is *candidate* content — not a replacement for data modelling discipline. The system automates discovery and synthesis; human SMEs make the final calls.

---

### 7.3 Agent Layer: Agentic RAG

**Module**: `elt_llm_agent`  
**Purpose**: Interactive, multi-step reasoning across data sources  
**Start here**: [elt_llm_agent/ARCHITECTURE.md](elt_llm_agent/ARCHITECTURE.md) for complete agent architecture

**What is Agentic RAG?**

Agentic RAG adds an **orchestration layer** on top of existing RAG infrastructure. Instead of single-shot retrieval (one query → one collection → one answer), the agent:
1. Receives natural language questions (no collection name needed)
2. Plans multi-step reasoning loops (which tools to call, in what order)
3. Executes tools (JSON lookup, graph traversal, RAG queries)
4. Synthesizes final answer from multiple sources with citations

**ReAct Pattern** (Reason + Act):
```
Query → Plan → [Tool: JSON Lookup] → [Tool: Graph Traversal] → [Tool: RAG Query]
   → Reason → Observe → Repeat → Synthesize → Answer
```

**Key Tools**:
| Tool | Purpose | Uses |
|------|---------|------|
| `rag_query_tool` | Query RAG collections | `elt_llm_query` |
| `json_lookup_tool` | Direct JSON sidecar access | `.tmp/*_model.json`, `*_inventory.json` |
| `graph_traversal_tool` | Relationship traversal | NetworkX (in-memory graph) |

**When to Use Agent vs Consumer**:

| Goal | Use Agent | Use Consumer |
|------|-----------|--------------|
| **Structured JSON output** | ❌ No | ✅ Yes |
| **Complete entity coverage** | ❌ No (query-driven) | ✅ Yes (all 175 entities) |
| **Interactive Q&A** | ✅ Yes (chat-style) | ❌ No (batch only) |
| **Fast response (<30s)** | ❌ No (10–30s) | ❌ No (45–60 min) |
| **Follow-up questions** | ✅ Yes (conversation memory) | ❌ No (stateless) |
| **Graph traversal** | ✅ Yes (NetworkX) | ❌ No (direct lookup) |
| **Downstream import** | ❌ No (prose output) | ✅ Yes (schema-enforced JSON) |

**Example Commands**:
```bash
# Interactive chat
uv run python -m elt_llm_agent.chat

# Single query
uv run python -m elt_llm_agent.query \
  -q "What data objects flow through the Player Registration interface?"

# Batch queries
uv run python -m elt_llm_agent.query --file queries.json --output results.json
```

**Example Query Flow**:
```
Query: "What data objects flow through the Player Registration interface?"

Step 1: json_lookup_tool(entity_type="interface", entity_name="Player Registration")
  → Returns: {fact_sheet_id: "INT-456", name: "Player Registration System", ...}

Step 2: graph_traversal_tool(entity_name="INT-456", operation="neighbors")
  → Returns: {neighbors: ["Player", "Registration", "County FA"]}

Step 3: rag_query_tool(collection="fa_handbook", query="governance for Player data")
  → Returns: "FA Handbook Section C, Rule 8: Player data must..."

Step 4: Synthesize final answer with citations
```

**Runtime**: 10–30s per query (3–5 tool calls typical)

**Open-Source Compliance**: All components are open-source:
- LlamaIndex (MIT) — Agent framework
- NetworkX (BSD) — Graph traversal (no Neo4j required)
- ChromaDB (Apache 2.0) — Vector store (via `elt_llm_query`)

See [elt_llm_agent/ARCHITECTURE.md](elt_llm_agent/ARCHITECTURE.md) for complete agent architecture, or [AGENT_VS_CONSUMER.md](AGENT_VS_CONSUMER.md) for detailed comparison with `elt_llm_consumer`.

---

## 8. Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| **Vector Store** | ChromaDB | Persistent, tenant/database isolation |
| **Embeddings** | Ollama | `nomic-embed-text` (768 dimensions) |
| **LLM** | Ollama | `qwen3.5:9b` (16K context) |
| **Retrieval** | LlamaIndex | BM25 + Vector hybrid via QueryFusionRetriever |
| **Reranking** | Embedding or Cross-encoder | Cosine similarity or `cross-encoder/ms-marco-MiniLM-L-6-v2` |
| **PDF Processing** | IBM Docling | DocLayNet + TableFormer models |
| **XML Parsing** | Custom Python | `xml.etree.ElementTree` |
| **Excel Parsing** | openpyxl | Read-only mode |
| **Dependency Mgmt** | uv | Python 3.11-3.13 |
| **GUI** | Gradio | http://localhost:7860 |

---

## 9. Performance Characteristics

### 9.1 Ingestion Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| **FA Handbook PDF → Markdown** | ~250s | 2.5M chars, Docling StandardPipeline |
| **LeanIX XML → JSON + Markdown** | ~5s | 175 entities, custom parser |
| **LeanIX Excel → JSON + Markdown** | ~10s | 1,424 fact sheets, openpyxl |
| **Chunking** | ~5s | 3,375 nodes for FA Handbook |
| **Embedding** | ~94s | Ollama, nomic-embed-text |
| **Total FA Handbook ingestion** | ~3 min | First run includes model download |

### 9.2 Query Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| **Vector retrieval** | 10–50ms | ChromaDB ANN search |
| **BM25 retrieval** | 5–20ms | In-memory index |
| **Embedding reranker** | 100–500ms | Ollama embedding (20 candidates) |
| **Cross-encoder reranker** | 200–800ms | MiniLM-L-6-v2 (optional) |
| **LLM synthesis** | 10–90s | Depends on model and context size |
| **Total typical query** | 2–6s | Single question, no batch |
| **Per-entity consolidation** | ~60–90s | RAG + LLM synthesis |

### 9.3 Consumer Runtime

| Consumer | Runtime (full run) | Bottleneck |
|----------|-------------------|------------|
| **fa_consolidated_catalog** | ~45–60 min | Handbook RAG (175 entities × ~15s each) |
| **fa_handbook_model_builder** | ~5-7 min | LLM synthesis (14 seed topics) |
| **fa_coverage_validator** | ~3-7 min | Retrieval only (no LLM) |

### 9.4 Cost Optimisation

| Optimisation | Savings | How |
|--------------|---------|-----|
| **Skip relationships** | ~30% faster | `--skip-relationships` flag |
| **Single domain** | ~80% faster | `--domain PARTY` (one domain vs. all) |
| **Reduce num_queries** | ~60% faster | Set `num_queries: 1` in `rag_config.yaml` |
| **No-coverage exclusions** | ~8 LLM calls | Hardcoded exclusion list in consumer |

---

## 10. Module Reference

### Module Structure

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
├── elt_llm_consumer/       # Output generators
│   ├── fa_consolidated_catalog.py  # Target output (primary)
│   ├── fa_handbook_model_builder.py
│   └── fa_coverage_validator.py
│
└── elt_llm_agent/          # Agentic RAG orchestration
    ├── agent.py            # ReActAgent orchestrator
    ├── chat.py             # Interactive chat CLI
    ├── runner.py           # Batch query runner
    ├── tools/              # Tool wrappers (RAG, JSON, Graph)
    ├── planners/           # ReAct + Plan-and-Execute
    └── memory/             # Conversation + Workspace memory
```

### Module Documentation

| Module | Purpose | Documentation |
|--------|---------|---------------|
| `elt_llm_core/` | Shared RAG infrastructure | [README](elt_llm_core/README.md) |
| `elt_llm_ingest/` | Document ingestion pipeline | [README](elt_llm_ingest/README.md), [ARCHITECTURE](elt_llm_ingest/ARCHITECTURE.md) |
| `elt_llm_query/` | Query interface | [README](elt_llm_query/README.md) |
| `elt_llm_api/` | Gradio GUI + API | [README](elt_llm_api/README.md) |
| `elt_llm_consumer/` | Purpose-built output generators | [README](elt_llm_consumer/README.md), [ARCHITECTURE](elt_llm_consumer/ARCHITECTURE.md) |
| `elt_llm_agent/` 🆕 | Agentic RAG orchestration | [README](elt_llm_agent/README.md), [ARCHITECTURE](elt_llm_agent/ARCHITECTURE.md) |

---

## 11. Delivery Roadmap

### Phase 1: Data Asset Catalog (COMPLETE ✅)

**Goal**: Produce a structured catalog linking FA Handbook regulatory terms to LeanIX conceptual model entities and inventory descriptions.

**Deliverables**:
- `fa_consolidated_catalog.json` — Merged LeanIX + Handbook entities with source attribution
- `fa_consolidated_relationships.json` — Relationships with source lineage
- `fa_handbook_candidate_entities.json` — Entities discovered from Handbook only
- `fa_coverage_report.json` — Coverage scoring: Model → Handbook
- `fa_gap_analysis.json` — Gap analysis: Handbook → Model

**Next**: Stakeholder review workflow, metadata enrichment, parent-child chunking

---

### Phase 2: Purview + Erwin LDM Integration

**Goal**: Import reviewed catalog into Microsoft Purview as a governed business glossary and embed entity definitions/relationships into an Erwin Logical Data Model.

**Required Enhancements**:
- **CSV Export** — Purview-compatible format with term, description, domain, steward
- **Structured Citations** — Add source attribution (Handbook section, LeanIX ID)
- **GraphRAG** — Enable relationship traversal for Erwin LDM
- **Relationship Export** — Export entity relationships (not just definitions)

**Deliverables**:
- `purview_glossary.csv` — Business glossary for import
- `erwin_ldm.json` — Logical data model with entities + relationships

---

### Phase 3: Intranet Publishing

**Goal**: Publish the catalog to the FA intranet for organisation-wide access.

**Considerations**:
- Format: HTML / searchable web interface
- Access Control: Role-based (SMEs, Data Modellers, General Users)
- Update Cadence: Sync with LeanIX refresh cycle
- Search: Full-text search across glossary terms

---

### Phase 4: MS Fabric / Copilot Integration

**Goal**: Integrate with MS Fabric's agentic semantic model for use in Microsoft Copilot.

**RAG Implications**:
- **Structured Output** — JSON with term, definition, steward, domain, related asset IDs
- **GraphRAG** — Relationship data feeds semantic model dimensions/facts
- **Caching** — Repeated Copilot queries across users require response caching

---

### Phase 5: Vendor Assessment & SAD Generation

**Goal**: Automate SAD (Solution Architecture Document) generation and vendor assessments using RAG-grounded standards.

**Deliverables**:
- Auto-generated SADs with consistent structure
- Vendor capability assessments against FA standards
- Compliance checking against reference data (ISO, ONS)

---

## 12. FAQ

### Q: Why not use Ollama Modelfiles instead of YAML profiles?

**A:** Ollama Modelfiles and YAML profiles serve different purposes:

| YAML Profile (`llm_rag_profile/*.yaml`) | Ollama Modelfile |
|------------------------------------------|------------------|
| Configures **LlamaIndex** (Python app) | Configures **Ollama server** (model container) |
| Sets retrieval params (`similarity_top_k`, `use_reranker`) | Sets model params (`temperature`, `top_p`) |
| Defines system prompts at **query time** | Bakes system prompts **into the model** |
| Runtime configuration | Build-time configuration |

**Why YAML profiles are better for this project**:
- ✅ System prompts can change **per query** without rebuilding models
- ✅ Retrieval settings are LlamaIndex-specific, not Ollama-specific
- ✅ One model serves multiple profiles (FA, DAMA, etc.)

---

### Q: Does PDF processing require HuggingFace or internet access?

**A:** First run downloads Docling's DocLayNet + TableFormer models (~200MB from HuggingFace, cached at `~/.cache/docling/`). All subsequent runs are fully offline.

**If you see HuggingFace errors after first run**, they're from:
- **Cross-encoder reranker** (`cross-encoder/ms-marco-MiniLM-L-6-v2`) — optional, uses `sentence-transformers`
- **Not PDF processing**

**Fix**: Pre-download once or disable cross-encoder:
```bash
# Option 1: Pre-download (one-time)
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# Option 2: Use embedding reranker (Ollama, fully local)
# In rag_config.yaml:
query:
  reranker_strategy: "embedding"  # Instead of "cross-encoder"
```

---

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

**Use Marker if**:
- You have **scanned PDFs** (OCR needed)
- You have a **GPU** and want LLM-enhanced extraction

---

### Q: Why does the consumer use direct JSON lookup for LeanIX data, and how do the XML and Excel datasets join?

**A:** LeanIX data uses **direct JSON sidecars** (not RAG) for deterministic, O(1) access. See §5.4 for the full rationale and when-to-use guide.

The two sidecars join on **`fact_sheet_id`**: `_model.json` (entities from XML) and `_inventory.json` (fact sheets from Excel, keyed by `fact_sheet_id`). Only the FA Handbook (unstructured PDF) requires RAG+LLM.

---

### Q: What's the difference between Retrieval and Generation?

**A:** The RAG pipeline has two separable stages:

| Stage | What it does | Cost | Output |
|-------|-------------|------|--------|
| **Retrieval** | Query → embedding → cosine similarity search → top-K chunks with scores | ~1–2s per entity | Chunks + similarity scores |
| **Generation** | Retrieved chunks + prompt → Ollama LLM → synthesised text | ~60–90s per entity | Human-readable answer |

**Why it matters**: Some consumers (e.g., Coverage Validator) use **retrieval only** — the cosine score *is* the answer. Running the LLM would add ~60s per entity and produce prose that then has to be re-interpreted as a signal — slower and less precise.

---

### Q: How do I decide between RAG and direct lookup?

**A:** Use this decision table:

| Data Characteristic | Approach | Reason |
|---------------------|----------|--------|
| Structured with canonical IDs | Direct lookup | Deterministic, fast, exact |
| Unstructured text | RAG + LLM | Semantic search needed |
| Key-value with exact matches | Direct lookup | No semantic ambiguity |
| Definitions, rules, policies | RAG + LLM | Context-dependent meaning |
| Relationships (graph) | GraphRAG (planned) | Traversal, not similarity |

---

## References

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Quick start and module overview |
| [RAG_STRATEGY.md](RAG_STRATEGY.md) | Retrieval strategy — hybrid search, reranking, enhancement roadmap |
| [RAG_TUNING.md](RAG_TUNING.md) | Parameter tuning rationale and trade-offs |
| [ORCHESTRATION.md](ORCHESTRATION.md) | Workflow documentation — runbooks, phase status, troubleshooting |
| [elt_llm_ingest/ARCHITECTURE.md](elt_llm_ingest/ARCHITECTURE.md) | Ingestion internals — preprocessors, chunking, change detection |
| [elt_llm_consumer/ARCHITECTURE.md](elt_llm_consumer/ARCHITECTURE.md) | Consumer pipelines — output interpretation, enhancement cycle |

---

**Document Status**: Living Document  
**Next Review**: After Phase 2 planning
