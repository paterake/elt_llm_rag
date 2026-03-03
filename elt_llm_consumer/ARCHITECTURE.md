# elt_llm_consumer — Architecture

**Module**: `elt_llm_consumer`
**Role**: Structured output layer over the RAG+LLM pipeline

**See also**: 
- [RAG_STRATEGY.md](../RAG_STRATEGY.md) — Hybrid retrieval and reranking strategy
- [ARCHITECTURE.md](../ARCHITECTURE.md) — Full system architecture
- `elt_llm_query/query.py` — Query interface used by all consumers

---

## Quick Start

**Two-step workflow:**

```bash
# 1. Ingest source datasets (builds ChromaDB + DocStore)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory

# 2. Run consumer script (queries via elt_llm_query, outputs JSON)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
```

**Output:** `fa_consolidated_catalog.json` (stakeholder review)

---

## Table of Contents

- [0. Strategic Value Proposition](#0-strategic-value-proposition)
  - [0.1 Answering the Challenge](#01-answering-the-challenge)
  - [0.2 Summary Architecture Diagram](#02-summary-architecture-diagram)
- [1. The ELT Analogy](#1-the-elt-analogy)
- [2. Where the Consumer Layer Sits](#2-where-the-consumer-layer-sits)
- [3. RAG+LLM Architecture](#3-ragllm-architecture)
  - [3.1 Two-Step Workflow](#31-two-step-workflow)
  - [3.2 Role of RAG Profiles](#32-role-of-rag-profiles)
  - [3.3 Hybrid Strategy](#33-hybrid-strategy)
- [4. Consumers](#4-consumers)
  - [4.1 FA Handbook Model Builder](#41-fa-handbook-model-builder)
  - [4.2 FA Coverage Validator](#42-fa-coverage-validator)
  - [4.3 FA Consolidated Catalog](#43-fa-consolidated-catalog)
- [5. Source Joins](#5-source-joins)
- [6. Recommended Workflow](#6-recommended-workflow)
- [7. Conceptual Model Enhancement Cycle](#7-conceptual-model-enhancement-cycle)
  - [7.1 The Feedback Loop](#71-the-feedback-loop)
  - [7.2 Gap Analysis Interpretation Guide](#72-gap-analysis-interpretation-guide)
  - [7.3 Logical Model Creation](#73-logical-model-creation)
  - [7.4 Are You Being Naive?](#74-are-you-being-naive)
  - [7.5 Success Metrics](#75-success-metrics)

---

## 0. Strategic Value Proposition

### 0.1 Answering the Challenge

**Challenge**: Can we effectively map the conceptual model to the FA Handbook, use the handbook for SME/business context, use LeanIX inventory for descriptions, and then create a logical model using knowledge of the FA Handbook?

**Answer**: **Yes** — and this is exactly what the consumer layer implements. The architecture deliberately separates three distinct sources, each playing a specific role:

| Source | Role | Implementation |
|--------|------|----------------|
| **Conceptual Model** (LeanIX XML) | **The Frame** — canonical entity list with domains, hierarchy, relationships | Drives `fa_consolidated_catalog` (primary) and `fa_coverage_validator` |
| **LeanIX Inventory** (Excel) | **Descriptions** — precise fact_sheet_id lookup for system definitions | Joined in-memory (not via RAG) for accuracy |
| **FA Handbook** (PDF RAG) | **SME/Business Context** — governance rules, obligations, regulatory context | Queried per entity for governance content |

**Are you being naive?** No — but there are important nuances:

| What You Proposed | What the System Does | Caveat |
|-------------------|----------------------|--------|
| Map conceptual model to handbook |  Coverage validator scores every entity against handbook content | Some entities may be named differently in handbook (fuzzy matching helps) |
| Handbook provides SME context |  LLM synthesises governance rules per entity | Handbook may not cover technical/implementation entities (e.g., specific data objects) |
| LeanIX inventory for descriptions |  Direct join by fact_sheet_id | Inventory quality varies — some descriptions are sparse or outdated |
| Create logical model from handbook |  Handbook model builder extracts candidate entities | Handbook entities are **business concepts**, not necessarily **data structures** — human review required |

**The key insight**: The coverage validator doesn't just show gaps — it provides an **evidence-based feedback loop** for improving the conceptual model.

---

### 0.2 Summary Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Knowledge Sources                                  │
│  ┌──────────────────────┐  ┌─────────────────────┐  ┌────────────────────┐  │
│  │  FA Handbook (PDF)   │  │  LeanIX XML (draw.io)│  │  LeanIX Inventory  │  │
│  │  - Governance rules  │  │  - Conceptual model  │  │  - Fact sheets     │  │
│  │  - Business context  │  │  - Entities + domains│  │  - Descriptions    │  │
│  │  - Obligations       │  │  - Relationships     │  │  - System metadata │  │
│  └──────────────────────┘  └─────────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
           │                              │                        │
           ↓                              ↓                        ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Ingestion Layer (elt_llm_ingest)                          │
│  - FA Handbook → chunked + embedded → fa_handbook collection                │
│  - LeanIX XML → parsed → fa_leanix_dat_enterprise_conceptual_model_*        │
│  - LeanIX Excel → chunked + embedded → fa_leanix_global_inventory_*         │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│              RAG Collections (ChromaDB — Semantic Layer)                     │
│  fa_handbook  │  fa_leanix_dat_enterprise_conceptual_model_*                │
│  fa_leanix_global_inventory_*  │  fa_data_architecture  │  dama_dmbok       │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Consumer Layer (elt_llm_consumer)                          │
│                                                                             │
│  All consumers query via: elt_llm_query.query_collections()                 │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 1: FA Handbook Model Builder                                 │  │
│  │  Driver: 14 seed topics (Club, Player, Competition, etc.)              │  │
│  │  Sources: fa_handbook (RAG only — no LeanIX required)                  │  │
│  │  Output: fa_handbook_candidate_entities.json,                          │  │
│  │          fa_handbook_candidate_relationships.json,                      │  │
│  │          fa_handbook_terms_of_reference.json                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 2: FA Coverage Validator                                     │  │
│  │  Driver: LeanIX Conceptual Model                                       │  │
│  │  Sources: fa_handbook (retrieval ONLY — no LLM, ~5 min)                │  │
│  │  Output: fa_coverage_report.json, fa_gap_analysis.json                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 3: FA Consolidated Catalog  (TARGET OUTPUT)                │  │
│  │  Driver: All sources merged                                            │  │
│  │  Sources:                                                              │  │
│  │    - Conceptual model (docstore scan)                                  │  │
│  │    - Inventory (RAG enrichment)                                        │  │
│  │    - Handbook (RAG enrichment + docstore markers)                      │  │
│  │  Output: fa_consolidated_catalog.json (stakeholder review)             │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Conceptual Model Enhancement Cycle                        │
│                                                                             │
│  fa_gap_analysis.json reveals:                                                │
│  - MATCHED       → Model aligned with handbook                              │
│  - MODEL_ONLY    → Question: Should this be in handbook? Out of scope?      │
│  - HANDBOOK_ONLY → Gap: Consider adding to conceptual model                 │
│                                                                             │
│  fa_coverage_report.json reveals:                                             │
│  - STRONG (≥0.70) → Well-covered entity                                     │
│  - MODERATE       → Some governance context                                 │
│  - THIN           → Weak signal — may need renaming or handbook update       │
│  - ABSENT (<0.40) → Not in handbook — technical entity or misalignment       │
│                                                                             │
│  Human review → Update LeanIX conceptual model → Re-run validation          │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Logical Model Creation                               │
│                                                                             │
│  Input: Enhanced conceptual model (LeanIX) + Handbook ToR + Gap analysis    │
│  Process:                                                                    │
│    1. Use handbook ToR for business definitions and attributes              │
│    2. Use conceptual model for entity structure and relationships           │
│    3. Human SME review to resolve ambiguities                               │
│    4. Derive logical model with attributes, keys, cardinalities             │
│  Output: Logical data model (e.g., ERD, UML class diagram)                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. RAG+LLM Architecture

### 3.1 Two-Step Workflow

**Step 1: Ingestion** (elt_llm_ingest)
```bash
# Builds ChromaDB vector store + DocStore metadata index
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
```

**Output:** RAG-ready collections in ChromaDB + DocStore

**Step 2: Consumer** (elt_llm_consumer)
```bash
# Queries collections via elt_llm_query, outputs JSON
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
```

**Output:** `fa_consolidated_catalog.json` (stakeholder review)

---

### 3.2 Role of RAG Profiles

**Profiles** (`elt_llm_query/llm_rag_profile/`) define:
- Which collections to query
- LLM model settings
- System prompts
- Retrieval config (top_k, reranker, etc.)

**Consumers can either:**

1. **Use a profile** (recommended for consistency):
   ```python
   from elt_llm_core.config import RagConfig
   from elt_llm_query.query import query_collections

   rag_config = RagConfig.from_profile("fa_data_management")
   result = query_collections(rag_config.query.collections, query, rag_config)
   ```

2. **Resolve collections directly** (what `fa_consolidated_catalog` does):
   ```python
   from elt_llm_query.query import resolve_collection_prefixes

   collections = resolve_collection_prefixes(
       ["fa_leanix_dat_enterprise_conceptual_model"], rag_config
   )
   result = query_collections(collections, query, rag_config)
   ```

---

### 3.3 Hybrid Strategy

**What uses RAG+LLM synthesis:**
- Handbook context enrichment (governance rules, definitions)
- Handbook term → Model entity mapping
- Inventory description lookup

**What uses docstore scan (structured metadata):**
- Conceptual model entity extraction
- Relationship extraction

**Why hybrid:**
- RAG+LLM is slow for bulk extraction (~15s per entity)
- Docstore scan is fast (seconds for all entities)
- Both query the **index** — neither parses source files directly

This balances **scalability** (fast extraction) with **quality** (LLM synthesis where it adds value).

---

## 1. The ELT Analogy

`elt_llm_consumer` maps directly to the visualisation / reporting layer in a
conventional ELT pipeline:

```
ELT Pipeline                     ELT LLM RAG

Raw Sources                       FA Handbook PDF, LeanIX XML, DAMA PDF
      ↓                                     ↓
Extract / Transform / Load        Chunk + Embed → ChromaDB (elt_llm_ingest)
      ↓                                     ↓
Data Warehouse / Semantic Layer   RAG Collections — queryable knowledge store
      ↓                                     ↓
BI Reports / Scheduled Exports    Consumers — batch jobs that drive the
                                  query layer and write structured outputs
```

The RAG collections are the **semantic layer** (queryable, enriched, indexed).
The consumers are the **BI reports** — purpose-built jobs that ask specific
questions at scale and write the answers to JSON files for stakeholder use.

A query profile (`llm_rag_profile/`) is analogous to a saved SQL query — it
configures which collections and persona to use. A consumer is the **driver**
that iterates 200+ entities, constructs per-entity prompts, and manages
checkpointing and file output. A profile alone cannot do this.

---

## 2. Where the Consumer Layer Sits

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Knowledge Sources                             │
│  FA Handbook PDF  │  LeanIX XML (draw.io)  │  LeanIX Inventory Excel │
└──────────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────────┐
│                    Ingestion  (elt_llm_ingest)                        │
│  Chunk → Embed (nomic-embed-text) → ChromaDB collections             │
└──────────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────────┐
│            RAG Collections  (ChromaDB — semantic layer)               │
│  fa_handbook  │  fa_leanix_dat_enterprise_conceptual_model_*         │
│  fa_leanix_global_inventory_*  │  dama_dmbok  │  fa_data_architecture │
└──────────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────────┐
│                     Query Layer  (elt_llm_query)                      │
│  BM25 + Vector hybrid search → Embedding reranker → LLM synthesis   │
└──────────────────────────────────────────────────────────────────────┘
                                 ↓
┌──────────────────────────────────────────────────────────────────────┐
│                  Consumer Layer  (elt_llm_consumer)                   │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  Consumer 1: fa_handbook_model_builder                      │      │
│  │  Handbook → candidate entities + relationships + ToR        │      │
│  └─────────────────────────────────────────────────────────────┘      │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  Consumer 2: fa_coverage_validator                          │      │
│  │  Model vs Handbook — retrieval scoring only, no LLM         │      │
│  └─────────────────────────────────────────────────────────────┘      │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  Consumer 3: fa_consolidated_catalog  (TARGET OUTPUT)       │      │
│  │  All sources merged → stakeholder review JSON               │      │
│  └─────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
                                 ↓
                     Structured JSON outputs
                  (Consolidated Catalog, ToR, Gap Report)
```

---

## 3. Retrieval vs Generation

The RAG pipeline has two separable stages. Consumers use either or both,
depending on what they need to produce:

```
Stage 1: Retrieval (embedding search only)
─────────────────────────────────────────
  Query string → nomic-embed-text → cosine similarity against ChromaDB
  Output: top-K chunks with similarity scores
  Cost: ~1-2 s per entity
  No LLM involved.

Stage 2: Generation (LLM synthesis)
────────────────────────────────────
  Retrieved chunks + prompt → qwen2.5:14b → synthesised text
  Output: human-readable answer grounded in retrieved content
  Cost: ~10-20 s per entity
  Requires Ollama + loaded model.
```

| Consumer | Uses Retrieval | Uses Generation | Rationale |
|----------|---------------|-----------------|-----------|
| Handbook Model Builder |  |  | Needs entity extraction + ToR prose |
| **Coverage Validator** |  | **✗** | Only needs a signal — *does content exist?* The similarity score is the answer |
| Consolidated Catalog |  |  | Needs Handbook context + term mapping synthesis |

**Why the coverage validator skips generation**: the question being asked is
"does the FA Handbook contain meaningful content about this entity?" The
retrieval similarity score answers this directly. Synthesising a paragraph via
the LLM would add 10-20 s per entity and produce output that then has to be
re-interpreted as a coverage signal — slower and less precise than reading the
raw score.

---

## 4. Consumers

### 4.1 FA Handbook Model Builder

**File**: `fa_handbook_model_builder.py`
**Entry point**: `elt-llm-consumer-handbook-model`
**Driver**: 14 seed topics (no LeanIX required)

```
Seed topics: Club, Player, Registration, ...
        ↓
  Pass 1 — Entity discovery
    Per topic: query fa_handbook → extract defined terms + roles
    Output: fa_handbook_candidate_entities.json
        ↓
  Pass 2 — Relationship inference
    For co-appearing entity pairs: query fa_handbook → infer relationships
    Output: fa_handbook_candidate_relationships.json
        ↓
  Pass 3 — ToR consolidation
    Per unique entity: query fa_handbook → synthesise terms of reference
    Output: fa_handbook_terms_of_reference.json
```

**Purpose**: bootstrapping — build a candidate conceptual model from the
governance text alone, before or independent of LeanIX. Also produces the
`fa_handbook_candidate_entities.json` input consumed by the Coverage Validator
Direction 2 gap analysis.

---

### 4.2 FA Coverage Validator

**File**: `fa_coverage_validator.py`
**Entry point**: `elt-llm-consumer-coverage-validator`
**Driver**: LeanIX conceptual model XML

Two-direction validation — no LLM, pure retrieval scoring:

```
Direction 1 — Model → Handbook  (always runs, ~5 min)
──────────────────────────────────────────────────────
  LeanIX Conceptual Model XML
          ↓  (LeanIXExtractor)
    ~217 entities
          ↓
    For each entity:
      Query: "{entity_name} FA {domain} rules obligations governance handbook"
      Retrieve from fa_handbook (vector search only, no LLM)
      Top cosine similarity score = coverage signal
          ↓
    fa_coverage_report.json

  Verdict bands (cosine similarity of top chunk):
    STRONG    ≥ 0.70  — handbook clearly discusses this entity
    MODERATE  0.55–0.70 — some governance context available
    THIN      0.40–0.55 — weak signal; may be named differently
    ABSENT    < 0.40  — not meaningfully present in handbook


Direction 2 — Handbook → Model  (--gap-analysis, instant)
──────────────────────────────────────────────────────────
  fa_handbook_candidate_entities.json   ← Consumer 2 output
  LeanIX Conceptual Model entity list  ← Consumer 3 driver
          ↓
    Normalised name comparison
          ↓
    fa_gap_analysis.json

  Status per entity:
    MATCHED       — present in both model and handbook
    MODEL_ONLY    — in model, not discussed in handbook
    HANDBOOK_ONLY — handbook discusses it; missing from model
```

**Why no LLM**: the coverage question ("does the handbook contain content about
this entity?") is answered by the retrieval similarity score itself. The LLM's
job is synthesis — reading retrieved chunks and writing prose. For a binary
signal of presence/absence, the cosine score is more precise and ~10× faster
than reading a synthesised answer and re-interpreting it.

---

### 4.3 FA Consolidated Catalog

**File**: `fa_consolidated_catalog.py`
**Entry point**: `elt-llm-consumer-consolidated-catalog`
**Driver**: All sources merged via RAG+LLM
**Output**: `fa_consolidated_catalog.json` (stakeholder review)
**Runtime**: ~3-4 hr with `num_queries=3` (default); ~45-60 min with `num_queries=1` in `rag_config.yaml`

**Purpose**: Single consolidated catalog merging all sources — the target output
for stakeholder review and Purview import.

**What it answers (7 requirements)**:
1.  Entities from the conceptual model
2.  Handbook-only entities (not in conceptual model)
3.  LeanIX inventory descriptions
4.  FA Handbook context (SME definition, glossary, ToR, governance)
5.  Relationships from conceptual model
6.  Relationships from inventory
7.  Relationships from Handbook

**Architecture**:
```
Step 1: Extract entities from conceptual model docstores
        (scan fa_leanix_dat_enterprise_conceptual_model_* docstores)
        ↓
        ~217 entities with name, domain, hierarchy

Step 2: Get inventory descriptions via RAG
        (query fa_leanix_global_inventory_* per entity)
        ↓
        Descriptions enriched per entity

Step 3: Extract Handbook defined terms from docstore
        (scan fa_handbook docstore for definition markers)
        ↓
        ~152 defined terms with definitions

Step 4: Map Handbook terms → Model entities via RAG
        (query_collections per term)
        ↓
        Mapping with confidence scores

Step 5: Get Handbook context per entity via RAG
        (query_collections for governance/domain context)
        ↓
        FORMAL_DEFINITION | DOMAIN_CONTEXT | GOVERNANCE

Step 6: Extract relationships from conceptual model docstores
        (scan for relationship patterns)
        ↓
        Entity → Entity relationships

Step 7: Consolidate and classify
        - BOTH: In both model and Handbook
        - LEANIX_ONLY: Only in model
        - HANDBOOK_ONLY: Only in Handbook (candidate for addition)
        ↓
        fa_consolidated_catalog.json
```

**Hybrid strategy**:
- **Docstore scan** for structured metadata (entities, relationships) — fast
- **RAG+LLM** for synthesis (Handbook context, term mapping) — high quality
- **Neither parses source files** — all queries go through the index

**Output structure**:
```json
{
  "fact_sheet_id": "12345",
  "entity_name": "Club",
  "domain": "PARTY",
  "source": "BOTH",
  "leanix_description": "...",
  "formal_definition": "...",
  "domain_context": "...",
  "governance_rules": "...",
  "mapping_confidence": "high",
  "review_status": "PENDING",
  "relationships": [...]
}
```

**Review workflow**:
1. Run consumer → generates JSON with all entities
2. Data Architects review → update `review_status` fields
3. Import to Purview or downstream systems

---

## 5. Source Joins

Each consumer has a different relationship to its sources:

| Source | Consumer 1 (handbook-model) | Consumer 2 (coverage-validator) | Consumer 3 (consolidated-catalog) |
|--------|-----------|-----------|-----------|
| LeanIX XML (conceptual model) | — |  Driver |  Via docstore scan |
| LeanIX Inventory Excel | — | — |  Via RAG |
| `fa_handbook` collection |  RAG |  Retrieval only |  RAG + docstore markers |
| `fa_leanix_dat_*` collections | — | — |  Docstore scan |
| Consumer 1 JSON output | — |  Gap analysis | — |

**No direct file parsing**: all consumers query via the index (ChromaDB + DocStore). The consolidated catalog uses docstore scan for fast structured extraction and RAG+LLM for synthesis where quality matters.

---

## 6. Recommended Workflow

The consumers form a natural progression from discovery to validation to
production output:

```
Step 1 — Discover what the handbook models
─────────────────────────────────────────
  elt-llm-consumer-handbook-model
  Output: fa_handbook_candidate_entities.json
          fa_handbook_candidate_relationships.json
          fa_handbook_terms_of_reference.json

Step 2 — Validate the conceptual model against the handbook
───────────────────────────────────────────────────────────
  elt-llm-consumer-coverage-validator --gap-analysis
  Output: fa_coverage_report.json      ← which model entities have handbook coverage
          fa_gap_analysis.json         ← MATCHED / MODEL_ONLY / HANDBOOK_ONLY

  Review results:
  - ABSENT entities → likely misnamed in model or out of FA scope
  - HANDBOOK_ONLY   → missing entities; consider adding to conceptual model
  - THIN entities   → may need handbook terminology review

Step 3 — Generate the consolidated catalog (primary output)
────────────────────────────────────────────────────────────
  elt-llm-consumer-consolidated-catalog
  Output: fa_consolidated_catalog.json    ← Stakeholder review
          fa_consolidated_relationships.json

  All sources merged: LeanIX entities (docstore), inventory descriptions
  (RAG), and Handbook context (RAG + term mapping + governance).
```

---

## 7. Conceptual Model Enhancement Cycle

### 7.1 The Feedback Loop

The coverage validator is not just a reporting tool — it is the **engine for continuous improvement** of the conceptual model:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Iterative Model Refinement Cycle                          │
│                                                                             │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 1: Baseline                                       │         │
│         │  - Current LeanIX conceptual model (XML)                │         │
│         │  - FA Handbook (governance source of truth)             │         │
│         └──────────────────────┬──────────────────────────────────┘         │
│                                ↓                                            │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 2: Consumer 2 — Handbook Model Builder            │         │
│         │  Extract candidate entities from handbook alone         │         │
│         │  Output: fa_handbook_candidate_entities.json             │         │
│         └──────────────────────┬──────────────────────────────────┘         │
│                                ↓                                            │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 3: Consumer 4 — Coverage Validator                │         │
│         │  --gap-analysis                                         │         │
│         │  Output: fa_gap_analysis.json, fa_coverage_report.json    │         │
│         └──────────────────────┬──────────────────────────────────┘         │
│                                ↓                                            │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 4: Human SME Review                               │         │
│         │  ┌───────────────────────────────────────────────────┐  │         │
│         │  │  fa_gap_analysis.json:                             │  │         │
│         │  │  - MATCHED       ✓ Model aligned                  │  │         │
│         │  │  - MODEL_ONLY    ? Should this be in handbook?    │  │         │
│         │  │                  (technical entity? out of scope?)│  │         │
│         │  │  - HANDBOOK_ONLY → ACTION: Consider adding to     │  │         │
│         │  │                    conceptual model               │  │         │
│         │  └───────────────────────────────────────────────────┘  │         │
│         │  ┌───────────────────────────────────────────────────┐  │         │
│         │  │  fa_coverage_report.json:                          │  │         │
│         │  │  - STRONG (≥0.70)  ✓ Well-covered                 │  │         │
│         │  │  - MODERATE        ~ Some context                 │  │         │
│         │  │  - THIN            ⚠ Weak signal — rename?        │  │         │
│         │  │  - ABSENT (<0.40)  ✗ Not in handbook — technical? │  │         │
│         │  └───────────────────────────────────────────────────┘  │         │
│         └──────────────────────┬──────────────────────────────────┘         │
│                                ↓                                            │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 5: Model Updates in LeanIX                        │         │
│         │  - Add HANDBOOK_ONLY entities to conceptual model       │         │
│         │  - Review MODEL_ONLY entities: keep or remove?          │         │
│         │  - Rename/restructure THIN entities for clarity         │         │
│         │  - Document ABSENT entities as technical (non-business) │         │
│         └──────────────────────┬──────────────────────────────────┘         │
│                                ↓                                            │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 6: Regenerate Integrated Catalog                  │         │
│         │  elt-llm-consumer-integrated-catalog                    │         │
│         │  Output: Updated fa_terms_of_reference.json              │         │
│         └──────────────────────┬──────────────────────────────────┘         │
│                                ↓                                            │
│         ┌─────────────────────────────────────────────────────────┐         │
│         │  Step 7: Logical Model Derivation                       │         │
│         │  - Use enhanced conceptual model + handbook ToR         │         │
│         │  - Add attributes, keys, cardinalities                  │         │
│         │  - Output: ERD, UML class diagram                       │         │
│         └─────────────────────────────────────────────────────────┘         │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

### 7.2 Gap Analysis Interpretation Guide

| Status | Count | Interpretation | Action |
|--------|-------|----------------|--------|
| **MATCHED** | — | Entity exists in both model and handbook |  No action needed |
| **MODEL_ONLY** | — | Entity in model but not discussed in handbook |  **Review**: Is this a technical implementation detail? Should it have business governance? Consider marking as "technical entity" or removing if not needed |
| **HANDBOOK_ONLY** | — | Handbook discusses it, but not in model | ➕ **Add to model**: This is a gap — the conceptual model is missing a business entity |

**Coverage Verdict Interpretation**:

| Verdict | Score Range | Interpretation | Action |
|---------|-------------|----------------|--------|
| **STRONG** | ≥ 0.70 | Handbook clearly discusses this entity |  Well-aligned |
| **MODERATE** | 0.55–0.70 | Some governance context exists | ~ Review — may need more handbook coverage or entity refinement |
| **THIN** | 0.40–0.55 | Weak signal — handbook may use different terminology |  **Investigate**: Check `top_chunk_preview` in report — is entity named differently? |
| **ABSENT** | < 0.40 | Not meaningfully present in handbook | ❓ **Question**: Is this a technical/data object (not business)? Or is handbook outdated? |

---

### 7.3 Logical Model Creation

Once the conceptual model has been enhanced through the feedback loop, the logical model can be derived:

**Input Artefacts**:
1. **Enhanced LeanIX conceptual model** (XML, post-gap-analysis updates)
2. **FA Handbook Terms of Reference** (from Consumer 2 or 3)
3. **Gap analysis reports** (understanding of what was added/removed)
4. **LeanIX inventory descriptions** (for system context)

**Derivation Process**:

```
Step 1: Entity Enrichment
─────────────────────────
  For each entity in enhanced conceptual model:
    - Extract business definition from handbook ToR
    - Identify attributes mentioned in handbook (e.g., "Club has name, address, affiliation date")
    - Note cardinalities from relationships (e.g., "Club has many Players")

Step 2: Attribute Specification
───────────────────────────────
  For each entity:
    - List all attributes (from handbook + inventory + SME knowledge)
    - Define data types (string, date, identifier, etc.)
    - Identify primary keys (natural or surrogate)
    - Mark mandatory vs optional attributes

Step 3: Relationship Refinement
───────────────────────────────
  For each relationship:
    - Specify cardinality (1:1, 1:N, M:N)
    - Identify relationship attributes (if any)
    - Note referential integrity rules

Step 4: SME Review Workshop
────────────────────────────
  - Walk through logical model with Data Working Group
  - Validate attributes against business understanding
  - Resolve ambiguities (e.g., is "Club ID" the same as "Affiliation Number"?)

Step 5: Notation & Output
─────────────────────────
  - Export to ERD tool (e.g., draw.io, ER/Studio, PowerDesigner)
  - Or generate UML class diagram
  - Document in LeanIX as logical model layer
```

**Output Artefacts**:
- Logical ERD (entity-relationship diagram with attributes and cardinalities)
- UML class diagram (if using object-oriented notation)
- Attribute dictionary (name, type, constraints, definition source)
- Relationship matrix (source, target, cardinality, definition)

---

### 7.4 Are You Being Naive?

**Short answer**: No — but success depends on **human SME review** at key points.

**What works well**:
-  Automated extraction of candidate entities from handbook
-  Automated coverage scoring (retrieval is fast and objective)
-  Gap identification (clear signal on what's missing/misaligned)
-  Three-source join (model + inventory + handbook)

**Where human judgment is essential**:
-  **Entity naming mismatches**: Handbook says "Affiliated Organisation", model says "Club" — same thing?
-  **Technical vs business entities**: Model has "API_Payload_Log" — should this be in a business conceptual model?
-  **Attribute derivation**: Handbook mentions "Club must have a secretary" — is this an attribute, a relationship, or a role?
-  **Cardinality interpretation**: Handbook says "Players register with Clubs" — is this 1:N, M:N, or time-dependent?

**The system's role**: Automate the **discovery, scoring, and synthesis** — surface evidence for human experts to make informed decisions.

**The risk**: Treating LLM output as authoritative without SME validation. The handbook model builder output is **candidate** entities — not a replacement for data modelling discipline.

---

### 7.5 Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Model-Handbook Alignment** | >80% MATCHED | `fa_gap_analysis.json`: MATCHED / total |
| **Coverage Quality** | >70% STRONG/MODERATE | `fa_coverage_report.json`: (STRONG + MODERATE) / total |
| **Gap Resolution Rate** | Track over iterations | Count of HANDBOOK_ONLY entities added to model per cycle |
| **Terms of Reference Completeness** | 100% of model entities | `fa_terms_of_reference.json`: rows with non-empty definitions |

---

**Bottom line**: The architecture provides the **evidence base** for conceptual model improvement. The gap analysis doesn't just show problems — it tells you **exactly what to fix** and **where the handbook content is** to guide the fix.
