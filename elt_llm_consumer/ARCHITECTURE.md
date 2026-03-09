# elt_llm_consumer — Architecture

**Module**: `elt_llm_consumer`  
**Role**: Structured output layer over the RAG+LLM pipeline

**Start here**: Read [ARCHITECTURE.md](../ARCHITECTURE.md) §7 for the big picture on the consumer layer and the 7-step pipeline. This document covers module-specific implementation details, output interpretation, and the enhancement cycle.

---

## Table of Contents

- [1. Quick Start](#1-quick-start)
- [2. What This Module Does](#2-what-this-module-does)
- [3. Retrieval vs Generation](#3-retrieval-vs-generation)
- [4. The Three Consumers](#4-the-three-consumers)
- [5. Interpreting the Output](#5-interpreting-the-output)
- [6. Conceptual Model Enhancement Cycle](#6-conceptual-model-enhancement-cycle)

---

## 1. Quick Start

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

## 2. What This Module Does

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

**Three passes, all RAG+LLM**:

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

**Purpose**: Bootstrap a candidate model from governance text alone. The `fa_handbook_candidate_entities.json` output is also consumed by the Coverage Validator gap analysis.

**Default seed topics** (14): Club, Player, Official, Referee, Competition, County FA, Registration, Transfer, Affiliation, Discipline, Safeguarding, Governance, Eligibility, Licence

**Runtime**: ~14 topics × 20-30s ≈ 5-7 min

---

### 4.2 FA Coverage Validator

**File**: `fa_coverage_validator.py`  
**Entry point**: `elt-llm-consumer-coverage-validator`  
**Sources**: `_model.json` + `fa_handbook`

**Runs in two directions — retrieval only, no LLM**:

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

---

### 4.3 FA Consolidated Catalog

**File**: `fa_consolidated_catalog.py`  
**Entry point**: `elt-llm-consumer-consolidated-catalog`  
**Runtime**: ~45–60 min for a full domain run  
**Output**: `fa_consolidated_catalog.json` — PRIMARY stakeholder review artifact

**7-Step Pipeline** (see [ARCHITECTURE.md](../ARCHITECTURE.md) §7.1 for full detail):

```
Step 1: Load Conceptual Model Entities  → conceptual_entities (~175 entities)
Step 2: Load Inventory Descriptions     → inventory_descriptions (dict lookup)
Step 3: Extract Handbook Defined Terms  → handbook_terms (~149 terms)
Step 4: Match Terms to Entities         → handbook_mappings (2-5% match rate)
Step 5: Extract Handbook Context        → handbook_context (RAG+LLM, ~60-90s/entity)
Step 6: Load Relationships              → relationships + entity_relationships
Step 7: Consolidate                     → fa_consolidated_catalog.json
```

**Output structure per entity**:
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
