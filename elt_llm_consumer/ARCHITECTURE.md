# elt_llm_consumer — Architecture

**Module**: `elt_llm_consumer`
**Role**: Structured output layer over the RAG+LLM pipeline

**See also**:
- [RAG_STRATEGY.md](../RAG_STRATEGY.md) — Hybrid retrieval and reranking strategy
- [ARCHITECTURE.md](../ARCHITECTURE.md) — Full system architecture
- `elt_llm_query/query.py` — Query interface used by all consumers

---

## Quick Start

```bash
# Step 1 — Ingest source datasets (run once, or when sources change)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook

# Step 2 — Run the primary consumer
uv run python -m elt_llm_consumer.fa_consolidated_catalog
```

**Output:** `.tmp/fa_consolidated_catalog.json` — stakeholder review JSON

---

## Table of Contents

- [1. What This Module Does](#1-what-this-module-does)
- [2. System Architecture](#2-system-architecture)
- [3. Retrieval vs Generation](#3-retrieval-vs-generation)
- [4. The Three Consumers](#4-the-three-consumers)
  - [4.1 FA Handbook Model Builder](#41-fa-handbook-model-builder)
  - [4.2 FA Coverage Validator](#42-fa-coverage-validator)
  - [4.3 FA Consolidated Catalog](#43-fa-consolidated-catalog)
- [5. Interpreting the Output](#5-interpreting-the-output)
- [6. Conceptual Model Enhancement Cycle](#6-conceptual-model-enhancement-cycle)

---

## 1. What This Module Does

The consumer layer answers one question:

> **Can we map the FA conceptual model to the Handbook, enrich it with governance context and inventory descriptions, and produce a catalog ready for stakeholder review?**

It does this by combining three sources, each with a distinct role:

| Source | Role | How it's accessed |
|--------|------|-------------------|
| **LeanIX XML** (`_model.json`) | The Frame — canonical entity list, domains, relationships | Direct JSON read (no RAG) |
| **LeanIX Inventory** (`_inventory.json`) | Descriptions — precise `fact_sheet_id` lookup | Direct dict lookup (no RAG) |
| **FA Handbook** (`fa_handbook`) | Business context — governance rules, obligations, definitions | RAG + LLM synthesis |

**The key design principle**: only use RAG+LLM where semantic understanding is genuinely needed. Structured data (LeanIX) is read directly — it's faster, deterministic, and exact. The Handbook is the only source that requires retrieval.

---

## 2. System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              Knowledge Sources                                │
│  ┌─────────────────────┐   ┌──────────────────────┐   ┌───────────────────┐  │
│  │  FA Handbook (PDF)  │   │  LeanIX XML (draw.io) │   │  LeanIX Inventory │  │
│  │  Governance rules   │   │  Conceptual model     │   │  Fact sheets      │  │
│  │  Business context   │   │  Entities + domains   │   │  Descriptions     │  │
│  └─────────────────────┘   └──────────────────────┘   └───────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
           │                            │                         │
           ▼                            ▼                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                         Ingestion  (elt_llm_ingest)                           │
│                                                                              │
│  FA Handbook  → chunk + embed → fa_handbook (ChromaDB + docstore)            │
│                                                                              │
│  LeanIX XML   → LeanIXPreprocessor                                           │
│                  ├── _model.json        ← consumer reads directly            │
│                  └── _entities.md       → ChromaDB (query UI only)           │
│                      _relationships.md  → ChromaDB (query UI only)           │
│                                                                              │
│  LeanIX Excel → LeanIXInventoryPreprocessor                                  │
│                  ├── _inventory.json    ← consumer reads directly            │
│                  └── per-type .md       → ChromaDB (query UI only)           │
└──────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                      Query Layer  (elt_llm_query)                             │
│       BM25 (docstore) + Dense Vector (ChromaDB) → Reranker → LLM            │
└──────────────────────────────────────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    Consumer Layer  (elt_llm_consumer)                         │
│                                                                              │
│  fa_handbook_model_builder   → fa_handbook_candidate_entities.json           │
│                                 fa_handbook_candidate_relationships.json      │
│                                                                              │
│  fa_coverage_validator       → fa_coverage_report.json                       │
│                                 fa_gap_analysis.json                          │
│                                                                              │
│  fa_consolidated_catalog     → fa_consolidated_catalog.json  ← PRIMARY      │
│  (PRIMARY OUTPUT)               fa_consolidated_relationships.json            │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Retrieval vs Generation

The RAG pipeline has two separable stages. Each consumer uses one or both:

| Stage | What it does | Cost | Output |
|-------|-------------|------|--------|
| **Retrieval** | Query → embedding → cosine similarity search → top-K chunks with scores | ~1–2s per entity | Chunks + similarity scores |
| **Generation** | Retrieved chunks + prompt → Ollama LLM → synthesised text | ~60–90s per entity | Human-readable answer |

| Consumer | Retrieval | Generation | Why |
|----------|-----------|------------|-----|
| Handbook Model Builder | ✓ | ✓ | Needs entity extraction + ToR prose |
| Coverage Validator | ✓ | ✗ | The cosine score *is* the answer — no prose needed |
| Consolidated Catalog | ✓ | ✓ | Needs governance context synthesised per entity |

**Why the Coverage Validator skips generation**: the question is "does the handbook contain content about this entity?" The top retrieval similarity score answers that directly. Running the LLM would add ~60s per entity and produce prose that then has to be re-interpreted as a signal — slower and less precise.

---

## 4. The Three Consumers

### 4.1 FA Handbook Model Builder

**File**: `fa_handbook_model_builder.py`
**Entry point**: `elt-llm-consumer-handbook-model`
**Sources**: `fa_handbook` only — no LeanIX required

Three passes, all RAG+LLM:

```
Pass 1 — Entity discovery
  14 seed topics (Club, Player, Registration, ...) → query fa_handbook
  Output: fa_handbook_candidate_entities.json

Pass 2 — Relationship inference
  Co-appearing entity pairs → query fa_handbook
  Output: fa_handbook_candidate_relationships.json

Pass 3 — Terms of Reference
  Per unique entity → query fa_handbook → synthesise ToR prose
  Output: fa_handbook_terms_of_reference.json
```

**Purpose**: bootstrap a candidate model from governance text alone. The `fa_handbook_candidate_entities.json` output is also consumed by the Coverage Validator gap analysis.

---

### 4.2 FA Coverage Validator

**File**: `fa_coverage_validator.py`
**Entry point**: `elt-llm-consumer-coverage-validator`
**Sources**: `_model.json` + `fa_handbook`

Runs in two directions — retrieval only, no LLM:

```
Direction 1 — Model → Handbook  (always runs)
  For each model entity:
    query: "{entity_name} FA {domain} rules obligations governance"
    retrieve from fa_handbook (vector search only)
    top cosine similarity score → STRONG / MODERATE / THIN / ABSENT
  Output: fa_coverage_report.json

Direction 2 — Handbook → Model  (--gap-analysis flag)
  fa_handbook_candidate_entities.json ← from Handbook Model Builder
  model entity names ← from _model.json
    normalised name comparison
  Output: fa_gap_analysis.json (MATCHED / MODEL_ONLY / HANDBOOK_ONLY)
```

See [§5](#5-interpreting-the-output) for verdict band definitions.

---

### 4.3 FA Consolidated Catalog

**File**: `fa_consolidated_catalog.py`
**Entry point**: `elt-llm-consumer-consolidated-catalog`
**Runtime**: ~45–60 min for a full domain run
**Output**: `fa_consolidated_catalog.json` — PRIMARY stakeholder review artifact

**Step-by-step pipeline — what each step produces and what the next step uses:**

```
┌────────────────────────────────────────────────────────────────────────┐
│ Step 1: Load Conceptual Model Entities                                  │
│ Source: _model.json  (written by LeanIXPreprocessor during ingest)     │
│ How:    Direct JSON file read — no RAG, no LLM                         │
│ Produces: conceptual_entities                                           │
│           list of ~175 entities: entity_name, domain, subtype,         │
│           fact_sheet_id                                                 │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ conceptual_entities
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Step 2: Load Inventory Descriptions                                     │
│ Source: _inventory.json  (written by LeanIXInventoryPreprocessor)      │
│ How:    For each entity, look up its fact_sheet_id in the inventory     │
│         dict — O(1) Python dict lookup, no RAG, no LLM                 │
│ Produces: inventory_descriptions                                        │
│           dict: normalised entity_name →                               │
│           { description, level, status, type }                         │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ inventory_descriptions
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Step 3: Extract Handbook Defined Terms                                  │
│ Source: fa_handbook docstore (used as a key-value store, not search)   │
│ How:    Iterate every stored chunk and scan with two regex patterns:    │
│           • Inline:  "TERM means DEFINITION" (plain text sentences)    │
│           • Table:   "|TERM|means DEFINITION|" (Definitions tables)    │
│         <br> tags stripped from both term and definition text.         │
│         No RAG query, no LLM — pure text scanning.                     │
│ Produces: handbook_terms                                                │
│           list of ~149 dicts: { term, definition }                     │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ handbook_terms
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Step 4: Match Handbook Terms to Model Entities (name match only)       │
│ Source: handbook_terms (Step 3) + all model entity names (Step 1)      │
│ How:    Build a dict of normalised model entity names. For each of the │
│         149 handbook terms, check if its normalised name is a key in   │
│         that dict. Python dict lookup — no RAG, no LLM.               │
│ Produces: handbook_mappings                                             │
│           dict: term.lower() →                                         │
│             matched:   { mapped_entity, domain, fact_sheet_id,         │
│                          mapping_confidence: "high" }                  │
│             unmatched: { mapped_entity: "Not mapped",                  │
│                          mapping_confidence: "low" }                   │
│ Note:   Typically 2–5% match rate. The model uses short names          │
│         ("Team") while the handbook uses qualified names               │
│         ("Football Team"). Step 5 bridges this gap via RAG.            │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ handbook_mappings
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Step 5: Extract Handbook Context per Entity  (RAG + LLM)               │
│ Source: fa_handbook ChromaDB + docstore (hybrid search)                │
│         handbook_terms (Step 3) — passed as term_definitions so the   │
│         LLM prompt can include a formal definition if one exists       │
│ How:    For each entity in conceptual_entities:                        │
│           1. Build query: "{entity_name} {domain} rules governance..." │
│           2. Hybrid retrieval: BM25 (docstore) + dense vector          │
│              (ChromaDB) → fusion → embedding reranker                  │
│           3. Retrieved chunks + prompt → Ollama → synthesised text     │
│              for: formal_definition, domain_context, governance_rules  │
│           4. If governance is empty, run a second dedicated RAG query  │
│         ~60–90s per entity on a local model.                           │
│ Produces: handbook_context                                              │
│           dict: normalised entity_name →                               │
│           { formal_definition, domain_context, governance_rules }      │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ handbook_context
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Step 6: Load Relationships                                              │
│ Source: _model.json (same file as Step 1)                              │
│ How:    Direct JSON read — no RAG, no LLM                              │
│ Produces: relationships  dict: entity → entity relationships           │
│                                                                        │
│ Step 6b: Extract Handbook Relationship Context  (RAG + LLM)            │
│ Source: relationships (Step 6) + fa_handbook                           │
│ How:    For each relationship pair, query handbook for context         │
│ Produces: entity_relationships list                                    │
└──────────────────────────────┬─────────────────────────────────────────┘
                               │ relationships + entity_relationships
                               ▼
┌────────────────────────────────────────────────────────────────────────┐
│ Step 7: Consolidate                                                     │
│ Inputs: ALL variables from Steps 1–6:                                  │
│           conceptual_entities    → entity list and structure           │
│           handbook_terms         → to identify HANDBOOK_ONLY entries   │
│           handbook_mappings      → confidence + rationale per term     │
│           inventory_descriptions → leanix_description per entity       │
│           handbook_context       → definitions + governance per entity │
│           relationships          → entity-to-entity relationships      │
│ How:    Merge all inputs per entity. Classify each as:                 │
│           BOTH          — entity name matched in model AND handbook    │
│           LEANIX_ONLY   — in model only, no handbook name match        │
│           HANDBOOK_ONLY — handbook term with no matching model entity  │
│ Output: fa_consolidated_catalog.json                                   │
│           hierarchical: domain → subtype → entity                     │
│         fa_consolidated_relationships.json                             │
└────────────────────────────────────────────────────────────────────────┘
```

**Output structure per entity:**
```json
{
  "fact_sheet_id": "12345",
  "entity_name": "Club",
  "domain": "PARTY",
  "subgroup": "Organisation",
  "source": "BOTH",
  "leanix_description": "...",
  "formal_definition": "...",
  "domain_context": "...",
  "governance_rules": "...",
  "review_status": "PENDING",
  "relationships": [...]
}
```

---

## 5. Interpreting the Output

### Coverage Verdict Bands  (`fa_coverage_report.json`)

| Verdict | Score | Interpretation | Action |
|---------|-------|----------------|--------|
| **STRONG** | ≥ 0.70 | Handbook clearly discusses this entity | No action needed |
| **MODERATE** | 0.55–0.70 | Some governance context exists | Review — may need more handbook coverage |
| **THIN** | 0.40–0.55 | Weak signal — handbook may use different terminology | Check `top_chunk_preview` — is the entity named differently? |
| **ABSENT** | < 0.40 | Not meaningfully present in handbook | Is this a technical/data entity rather than a business concept? |

### Gap Analysis Status  (`fa_gap_analysis.json`)

| Status | Meaning | Action |
|--------|---------|--------|
| **MATCHED** | Entity exists in both model and handbook | None |
| **MODEL_ONLY** | In model, not discussed in handbook | Review: technical entity? out of FA scope? |
| **HANDBOOK_ONLY** | Handbook discusses it; not in model | Consider adding to conceptual model |

### Success Metrics

| Metric | Target |
|--------|--------|
| Model-Handbook Alignment | > 80% MATCHED |
| Coverage Quality | > 70% STRONG or MODERATE |
| Entities with formal definitions | > 90% |
| Entities with governance rules | > 70% |

---

## 6. Conceptual Model Enhancement Cycle

The consumers form a natural improvement loop:

```
1. Run Handbook Model Builder
   → fa_handbook_candidate_entities.json (what the handbook thinks exists)

2. Run Coverage Validator (--gap-analysis)
   → fa_coverage_report.json  (which model entities have handbook coverage?)
   → fa_gap_analysis.json     (MATCHED / MODEL_ONLY / HANDBOOK_ONLY)

3. Human SME Review
   HANDBOOK_ONLY → add to LeanIX conceptual model
   MODEL_ONLY    → question: technical detail? remove or keep?
   THIN/ABSENT   → rename entity to match handbook terminology?

4. Update LeanIX model, re-run ingestion, repeat from step 2.

5. When model is stable, run Consolidated Catalog for final output.
   → fa_consolidated_catalog.json  ← stakeholder review + Purview import
```

**Logical model derivation** (after model is stable):
1. Use handbook ToR for business definitions and attributes
2. Use conceptual model for entity structure and relationships
3. SME workshop to resolve ambiguities (naming, cardinalities, keys)
4. Output: ERD or UML class diagram with attributes, keys, constraints

**Important caveat**: LLM output is *candidate* content — not a replacement for data modelling discipline. The system automates discovery and synthesis; human SMEs make the final calls.
