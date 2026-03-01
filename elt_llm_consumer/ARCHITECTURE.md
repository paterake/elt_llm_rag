# elt_llm_consumer — Architecture

**Module**: `elt_llm_consumer`
**Role**: Structured output layer over the RAG+LLM pipeline

**See also**: [RAG_STRATEGY.md](../RAG_STRATEGY.md) for detailed documentation on the hybrid retrieval and reranking strategy used by the query layer.

---

## Table of Contents

- [0. Strategic Value Proposition](#0-strategic-value-proposition)
  - [0.1 Answering the Challenge](#01-answering-the-challenge)
  - [0.2 Summary Architecture Diagram](#02-summary-architecture-diagram)
- [1. The ELT Analogy](#1-the-elt-analogy)
- [2. Where the Consumer Layer Sits](#2-where-the-consumer-layer-sits)
- [3. Retrieval vs Generation](#3-retrieval-vs-generation)
- [4. Consumers](#4-consumers)
  - [4.1 Business Glossary Generator](#41-business-glossary-generator)
  - [4.2 FA Handbook Model Builder](#42-fa-handbook-model-builder)
  - [4.3 FA Integrated Catalog](#43-fa-integrated-catalog)
  - [4.4 FA Coverage Validator](#44-fa-coverage-validator)
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
| **Conceptual Model** (LeanIX XML) | **The Frame** — canonical entity list with domains, hierarchy, relationships | Drives `fa_integrated_catalog` and `fa_coverage_validator` |
| **LeanIX Inventory** (Excel) | **Descriptions** — precise fact_sheet_id lookup for system definitions | Joined in-memory (not via RAG) for accuracy |
| **FA Handbook** (PDF RAG) | **SME/Business Context** — governance rules, obligations, regulatory context | Queried per entity for governance content |

**Are you being naive?** No — but there are important nuances:

| What You Proposed | What the System Does | Caveat |
|-------------------|----------------------|--------|
| Map conceptual model to handbook | ✅ Coverage validator scores every entity against handbook content | Some entities may be named differently in handbook (fuzzy matching helps) |
| Handbook provides SME context | ✅ LLM synthesises governance rules per entity | Handbook may not cover technical/implementation entities (e.g., specific data objects) |
| LeanIX inventory for descriptions | ✅ Direct join by fact_sheet_id | Inventory quality varies — some descriptions are sparse or outdated |
| Create logical model from handbook | ✅ Handbook model builder extracts candidate entities | Handbook entities are **business concepts**, not necessarily **data structures** — human review required |

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
│  - Inventory Excel → (not ingested — used directly by consumers)            │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│              RAG Collections (ChromaDB — Semantic Layer)                     │
│  fa_handbook  │  fa_leanix_dat_enterprise_conceptual_model_*                │
│  fa_data_architecture  │  dama_dmbok                                         │
└─────────────────────────────────────────────────────────────────────────────┘
           │
           ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                   Consumer Layer (elt_llm_consumer)                          │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 1: Business Glossary Generator                               │  │
│  │  Driver: LeanIX Inventory Excel (all DataObjects + Interfaces)         │  │
│  │  Sources: fa_handbook + fa_data_architecture + fa_leanix_* (RAG)       │  │
│  │  Output: fa_business_catalog_dataobjects.json,                         │  │
│  │          fa_business_catalog_interfaces.json                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 2: FA Handbook Model Builder                                 │  │
│  │  Driver: 14 seed topics (Club, Player, Competition, etc.)              │  │
│  │  Sources: fa_handbook (RAG only — no LeanIX required)                  │  │
│  │  Output: fa_handbook_candidate_entities.json,                          │  │
│  │          fa_handbook_candidate_relationships.json,                      │  │
│  │          fa_handbook_terms_of_reference.json                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 3: FA Integrated Catalog                                     │  │
│  │  Driver: LeanIX Conceptual Model XML (canonical frame)                 │  │
│  │  Sources:                                                              │  │
│  │    - Inventory Excel (direct join by fact_sheet_id — NOT RAG)          │  │
│  │    - fa_handbook (RAG — governance context)                            │  │
│  │    - fa_leanix_dat_* (RAG — domain context)                            │  │
│  │  Output: fa_terms_of_reference.json, fa_integrated_catalog.json          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Consumer 4: FA Coverage Validator                                     │  │
│  │  Driver: LeanIX Conceptual Model XML                                   │  │
│  │  Sources: fa_handbook (retrieval ONLY — no LLM, ~5 min)                │  │
│  │  Analysis:                                                             │  │
│  │    - Direction 1: Model → Handbook (coverage scoring)                  │  │
│  │    - Direction 2: Handbook → Model (gap analysis, requires Consumer 2) │  │
│  │  Output: fa_coverage_report.json, fa_gap_analysis.json                   │  │
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
questions at scale and write the answers to CSV files for stakeholder use.

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
│  ┌─────────────────────┐    ┌─────────────────────────────────────┐  │
│  │  Consumer 1         │    │  Consumer 2                         │  │
│  │  business_glossary  │    │  fa_handbook_model_builder          │  │
│  │  Inventory → CSV    │    │  Handbook → candidate model + ToR   │  │
│  └─────────────────────┘    └─────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────┐    ┌─────────────────────────────────────┐  │
│  │  Consumer 3         │    │  Consumer 4                         │  │
│  │  fa_integrated_     │    │  fa_coverage_validator              │  │
│  │  catalog            │    │  Model vs Handbook — no LLM         │  │
│  │  3-source join      │    │  Retrieval scoring only             │  │
│  └─────────────────────┘    └─────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                                 ↓
                     Structured CSV outputs
                  (Terms of Reference, Catalog, Gap Report)
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
| Business Glossary | ✅ | ✅ | Needs synthesised catalog entries |
| Handbook Model Builder | ✅ | ✅ | Needs entity extraction + ToR prose |
| Integrated Catalog | ✅ | ✅ | Needs per-entity ToR + governance narrative |
| **Coverage Validator** | ✅ | **✗** | Only needs a signal — *does content exist?* The similarity score is the answer |

**Why the coverage validator skips generation**: the question being asked is
"does the FA Handbook contain meaningful content about this entity?" The
retrieval similarity score answers this directly. Synthesising a paragraph via
the LLM would add 10-20 s per entity and produce output that then has to be
re-interpreted as a coverage signal — slower and less precise than reading the
raw score.

---

## 4. Consumers

### 4.1 Business Glossary Generator

**File**: `business_glossary.py`
**Entry point**: `elt-llm-consumer-glossary`
**Driver**: LeanIX inventory Excel (all DataObjects and Interfaces)

```
LeanIX Inventory Excel
        ↓
  Iterate all rows                      ← driver: every fact sheet in inventory
        ↓
  For each entity:
    Query → all FA RAG collections      ← BM25 + vector + reranker
    LLM synthesises catalog entry       ← qwen2.5:14b
        ↓
  fa_business_catalog_dataobjects.json
  fa_business_catalog_interfaces.json
```

**Design choice**: inventory Excel as driver means every registered fact sheet
gets an entry, including those not explicitly modelled in the conceptual model.

---

### 4.2 FA Handbook Model Builder

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

### 4.3 FA Integrated Catalog

**File**: `fa_integrated_catalog.py`
**Entry point**: `elt-llm-consumer-integrated-catalog`
**Driver**: LeanIX conceptual model XML (not inventory)

> *The direct implementation of: "the conceptual model is the frame, the FA
> Handbook provides the SME definitions on top of it."*

```
LeanIX Conceptual Model XML          ← canonical entity list (frame)
        ↓  (LeanIXExtractor)
  ~217 explicitly modelled entities
        ↓
  For each entity:
    ├── Inventory Excel               ← direct dict lookup by fact_sheet_id
    │   (no RAG — precision join)         NOT queried via RAG
    │
    ├── fa_handbook RAG               ← governance rules + obligations
    │   (BM25 + vector + reranker)
    │
    └── fa_leanix_dat_* RAG           ← domain context + relationships
        (BM25 + vector + reranker)
        ↓
  LLM synthesises: FORMAL_DEFINITION | DOMAIN_CONTEXT | GOVERNANCE
        ↓
  fa_terms_of_reference.json
  fa_integrated_catalog.json
```

**Key design decisions**:

- **XML as driver** (not inventory): only explicitly modelled entities get a
  catalog entry. The conceptual model defines what matters architecturally.
- **Inventory joined directly** (not via RAG): descriptions are joined by
  `fact_sheet_id` from an in-memory dict. RAG retrieval of structured
  descriptions would introduce noise; a direct lookup is exact and instant.
- **Every entity gets an entry**: even if the inventory has no description, the
  XML entity still appears in the catalog — governed only by the handbook and
  model context.

---

### 4.4 FA Coverage Validator

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

## 5. Source Joins

Each consumer has a different relationship to its sources:

| Source | Consumer 1 | Consumer 2 | Consumer 3 | Consumer 4 |
|--------|-----------|-----------|-----------|-----------|
| LeanIX XML (conceptual model) | — | — | ✅ Driver | ✅ Driver |
| LeanIX Inventory Excel | ✅ Driver | — | ✅ Direct join | — |
| `fa_handbook` collection | ✅ RAG | ✅ RAG | ✅ RAG | ✅ Retrieval only |
| `fa_leanix_dat_*` collections | — | — | ✅ RAG | — |
| `fa_leanix_global_inventory_*` | ✅ RAG | — | — | — |
| `dama_dmbok` collection | ✅ RAG | — | — | — |
| Consumer 2 CSV output | — | — | — | ✅ Gap analysis |

**Direct join vs RAG join**: Consumer 3 joins inventory descriptions directly
from Excel by `fact_sheet_id` (exact, instant, no retrieval noise) rather than
querying the `fa_leanix_global_inventory_*` RAG collections. RAG is reserved for
content that requires semantic search: the FA Handbook and the conceptual model
relationship context.

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

Step 3 — Generate the integrated catalog (model as frame)
──────────────────────────────────────────────────────────
  elt-llm-consumer-integrated-catalog --model qwen2.5:14b
  Output: fa_terms_of_reference.json
          fa_integrated_catalog.json

  Every entity in the conceptual model gets a structured terms of reference
  entry, enriched by the inventory description and handbook governance content.
```

Consumer 1 (`elt-llm-consumer-glossary`) is complementary — it is inventory-
driven and covers all registered fact sheets, including those not in the
conceptual model, making it useful for a broader operational catalog rather
than an architecturally-scoped one.

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
| **MATCHED** | — | Entity exists in both model and handbook | ✅ No action needed |
| **MODEL_ONLY** | — | Entity in model but not discussed in handbook | ⚠️ **Review**: Is this a technical implementation detail? Should it have business governance? Consider marking as "technical entity" or removing if not needed |
| **HANDBOOK_ONLY** | — | Handbook discusses it, but not in model | ➕ **Add to model**: This is a gap — the conceptual model is missing a business entity |

**Coverage Verdict Interpretation**:

| Verdict | Score Range | Interpretation | Action |
|---------|-------------|----------------|--------|
| **STRONG** | ≥ 0.70 | Handbook clearly discusses this entity | ✅ Well-aligned |
| **MODERATE** | 0.55–0.70 | Some governance context exists | ~ Review — may need more handbook coverage or entity refinement |
| **THIN** | 0.40–0.55 | Weak signal — handbook may use different terminology | ⚠️ **Investigate**: Check `top_chunk_preview` in report — is entity named differently? |
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
- ✅ Automated extraction of candidate entities from handbook
- ✅ Automated coverage scoring (retrieval is fast and objective)
- ✅ Gap identification (clear signal on what's missing/misaligned)
- ✅ Three-source join (model + inventory + handbook)

**Where human judgment is essential**:
- ⚠️ **Entity naming mismatches**: Handbook says "Affiliated Organisation", model says "Club" — same thing?
- ⚠️ **Technical vs business entities**: Model has "API_Payload_Log" — should this be in a business conceptual model?
- ⚠️ **Attribute derivation**: Handbook mentions "Club must have a secretary" — is this an attribute, a relationship, or a role?
- ⚠️ **Cardinality interpretation**: Handbook says "Players register with Clubs" — is this 1:N, M:N, or time-dependent?

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
