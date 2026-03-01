# elt_llm_consumer — Architecture

**Module**: `elt_llm_consumer`
**Role**: Structured output layer over the RAG+LLM pipeline

---

## Table of Contents

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
  fa_business_catalog_dataobjects.csv
  fa_business_catalog_interfaces.csv
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
    Output: fa_handbook_candidate_entities.csv
        ↓
  Pass 2 — Relationship inference
    For co-appearing entity pairs: query fa_handbook → infer relationships
    Output: fa_handbook_candidate_relationships.csv
        ↓
  Pass 3 — ToR consolidation
    Per unique entity: query fa_handbook → synthesise terms of reference
    Output: fa_handbook_terms_of_reference.csv
```

**Purpose**: bootstrapping — build a candidate conceptual model from the
governance text alone, before or independent of LeanIX. Also produces the
`fa_handbook_candidate_entities.csv` input consumed by the Coverage Validator
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
  fa_terms_of_reference.csv
  fa_integrated_catalog.csv
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
    fa_coverage_report.csv

  Verdict bands (cosine similarity of top chunk):
    STRONG    ≥ 0.70  — handbook clearly discusses this entity
    MODERATE  0.55–0.70 — some governance context available
    THIN      0.40–0.55 — weak signal; may be named differently
    ABSENT    < 0.40  — not meaningfully present in handbook


Direction 2 — Handbook → Model  (--gap-analysis, instant)
──────────────────────────────────────────────────────────
  fa_handbook_candidate_entities.csv   ← Consumer 2 output
  LeanIX Conceptual Model entity list  ← Consumer 3 driver
          ↓
    Normalised name comparison
          ↓
    fa_gap_analysis.csv

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
  Output: fa_handbook_candidate_entities.csv
          fa_handbook_candidate_relationships.csv
          fa_handbook_terms_of_reference.csv

Step 2 — Validate the conceptual model against the handbook
───────────────────────────────────────────────────────────
  elt-llm-consumer-coverage-validator --gap-analysis
  Output: fa_coverage_report.csv      ← which model entities have handbook coverage
          fa_gap_analysis.csv         ← MATCHED / MODEL_ONLY / HANDBOOK_ONLY

  Review results:
  - ABSENT entities → likely misnamed in model or out of FA scope
  - HANDBOOK_ONLY   → missing entities; consider adding to conceptual model
  - THIN entities   → may need handbook terminology review

Step 3 — Generate the integrated catalog (model as frame)
──────────────────────────────────────────────────────────
  elt-llm-consumer-integrated-catalog --model qwen2.5:14b
  Output: fa_terms_of_reference.csv
          fa_integrated_catalog.csv

  Every entity in the conceptual model gets a structured terms of reference
  entry, enriched by the inventory description and handbook governance content.
```

Consumer 1 (`elt-llm-consumer-glossary`) is complementary — it is inventory-
driven and covers all registered fact sheets, including those not in the
conceptual model, making it useful for a broader operational catalog rather
than an architecturally-scoped one.
