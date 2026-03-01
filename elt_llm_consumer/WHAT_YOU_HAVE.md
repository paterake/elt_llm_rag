# FA Conceptual Model Enhancement — What You Already Have

**Your Challenge**: You have three datasets and want to:
1. Get business context/SME knowledge from FA Handbook for each conceptual model entity
2. Build a report showing conceptual model entity + LeanIX description + FA Handbook context
3. Identify opportunities for enhancing the conceptual model (entities in handbook not in LeanIX)

**Answer**: ✅ **All of this is already built.** Here's your exact workflow.

---

## Your Three Datasets

| Dataset | Format | What It Provides |
|---------|--------|------------------|
| **FA Handbook** | PDF (ingested into RAG) | SME knowledge, governance rules, business definitions |
| **Conceptual Model** | LeanIX draw.io XML export | Canonical entity frame: entities, domains, relationships |
| **LeanIX Inventory** | Excel export | Fact sheet descriptions, system metadata |

---

## What You Already Have Built

| Tool | What It Does | Output Files |
|------|--------------|--------------|
| **Consumer 3: `fa_integrated_catalog`** | ✅ Your requirement #1 + #2 | `fa_terms_of_reference.csv` |
| **Consumer 2: `fa_handbook_model`** | Discovers entities from handbook alone | `fa_handbook_candidate_entities.csv` |
| **Consumer 4: `fa_coverage_validator`** | ✅ Your requirement #3 | `fa_gap_analysis.csv`, `fa_coverage_report.csv` |

---

## Your Exact Workflow

### Step 1: Generate the Integrated Catalog (Requirements #1 + #2)

**Command**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --model qwen2.5:14b
```

**What it does**:
- Reads every entity from your LeanIX conceptual model XML (~217 entities)
- Looks up the LeanIX inventory description (direct Excel join by fact_sheet_id)
- Queries the FA Handbook RAG for business context, governance rules, obligations
- Synthesises a structured Terms of Reference for each entity

**Output**: `~/Documents/__data/resources/thefa/fa_terms_of_reference.csv`

**Columns**:
| Column | Source | Description |
|--------|--------|-------------|
| `fact_sheet_id` | LeanIX XML | Unique identifier |
| `entity_name` | LeanIX XML | Entity name (e.g., "Club", "Player") |
| `domain` | LeanIX XML | Domain group (e.g., "PARTY", "AGREEMENT") |
| `hierarchy_level` | LeanIX Excel | Level in taxonomy |
| `leanix_description` | LeanIX Excel | System description from inventory |
| `formal_definition` | LLM synthesis | Combined definition from inventory + handbook |
| `domain_context` | LLM synthesis | Role within domain, relationships to other entities |
| `governance_rules` | LLM synthesis | FA Handbook rules, obligations, regulations |

**This is your report** showing conceptual model entity + LeanIX description + FA Handbook business context. ✅

**Runtime**: ~35-70 minutes (217 entities × 10-20s each)

---

### Step 2: Discover Handbook-Only Entities (Requirement #3)

**Command**:
```bash
# First, extract candidate entities from the handbook
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model --model qwen2.5:14b

# Then run gap analysis
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis
```

**What it does**:
- **Pass 1** (`handbook-model`): Queries FA Handbook with 14 seed topics (Club, Player, Competition, etc.) to discover all entities mentioned in the handbook
- **Pass 2** (`coverage-validator`): Compares handbook-discovered entities vs. LeanIX conceptual model entities

**Outputs**:

#### `fa_handbook_candidate_entities.csv`
Entities discovered from the handbook alone:
| Column | Description |
|--------|-------------|
| `entity_name` | Term discovered (e.g., "Affiliated Club", "Registered Player") |
| `definition` | Definition from handbook |
| `category` | Type (organisation, role, concept, etc.) |
| `source_topic` | Which seed topic discovered it |

#### `fa_gap_analysis.csv` ← **Your enhancement opportunities**
Bidirectional gap analysis:
| Column | Description |
|--------|-------------|
| `normalized_name` | Lowercase, whitespace-normalised name for matching |
| `model_name` | Name in LeanIX conceptual model (if present) |
| `handbook_name` | Name in FA Handbook (if present) |
| `status` | **MATCHED** / **MODEL_ONLY** / **HANDBOOK_ONLY** |

#### `fa_coverage_report.csv`
Coverage scoring for every conceptual model entity:
| Column | Description |
|--------|-------------|
| `fact_sheet_id` | LeanIX ID |
| `entity_name` | Entity name |
| `domain` | Domain group |
| `top_score` | Cosine similarity (0-1) of best handbook match |
| `verdict` | **STRONG** (≥0.70) / **MODERATE** / **THIN** / **ABSENT** (<0.40) |
| `top_chunk_preview` | Actual handbook text snippet (for investigation) |

**Runtime**: 
- Handbook model: ~14 topics × 15s = ~3-5 minutes
- Coverage validator: ~217 entities × 1-2s = **3-7 minutes** (no LLM, pure retrieval)

---

## Interpreting the Gap Analysis

### `fa_gap_analysis.csv` Status Codes

| Status | Meaning | Action |
|--------|---------|--------|
| **MATCHED** | Entity in both model and handbook | ✅ No action |
| **MODEL_ONLY** | In LeanIX model, not in handbook | ⚠️ Review: Is this a technical entity? Should it have business governance? |
| **HANDBOOK_ONLY** | In handbook, missing from LeanIX model | ➕ **ACTION**: Consider adding to conceptual model |

### `fa_coverage_report.csv` Verdicts

| Verdict | Score | Meaning | Action |
|---------|-------|---------|--------|
| **STRONG** | ≥ 0.70 | Handbook clearly discusses this entity | ✅ Well-aligned |
| **MODERATE** | 0.55-0.70 | Some governance context exists | ~ Review |
| **THIN** | 0.40-0.55 | Weak signal — may be named differently | ⚠️ Check `top_chunk_preview` |
| **ABSENT** | < 0.40 | Not meaningfully in handbook | ❓ Technical entity? Out of scope? |

---

## Additional Opportunities You Already Have

### 1. Business Glossary from LeanIX Inventory

**Command**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model qwen2.5:14b
```

**What it does**: Driven by LeanIX Inventory Excel (all DataObjects + Interfaces), queries all FA RAG collections to produce catalog entries.

**Output**: `fa_business_catalog_dataobjects.csv`, `fa_business_catalog_interfaces.csv`

**Use case**: Broader operational catalog covering all registered fact sheets, not just conceptual model entities.

---

### 2. Relationship Extraction from Handbook

The `fa_handbook_model_builder` also extracts relationships:

**Output**: `fa_handbook_candidate_relationships.csv`
| Column | Description |
|--------|-------------|
| `entity_a` | Source entity |
| `entity_b` | Target entity |
| `relationship_description` | How they relate (from handbook) |
| `source_topic` | Which topic revealed this |

**Use case**: Compare handbook-discovered relationships vs. LeanIX model relationships — are you missing important business relationships?

---

### 3. Iterative Model Refinement

**Workflow**:
```bash
# Cycle 1
elt-llm-consumer-handbook-model
elt-llm-consumer-coverage-validator --gap-analysis
# → Review fa_gap_analysis.csv, update LeanIX XML
# Cycle 2
elt-llm-consumer-handbook-model  # Re-run with updated baseline
elt-llm-consumer-coverage-validator --gap-analysis
# → Compare gap counts — are HANDBOOK_ONLY entities decreasing?
```

**Metrics to track**:
- Count of `HANDBOOK_ONLY` entities per cycle (should decrease as you add them)
- Count of `STRONG` coverage verdicts (should increase)
- Count of `ABSENT` entities (should stabilise — these are technical entities)

---

## What You're NOT Missing (But Could Build)

| Opportunity | Status | Effort |
|-------------|--------|--------|
| **Logical model derivation** (attributes, keys, cardinalities) | ❌ Not built | Medium — requires LLM prompt engineering + SME review workflow |
| **Automated LeanIX update** (push changes back via API) | ❌ Not built | Low-Medium — LeanIX has GraphQL API |
| **Attribute extraction from handbook** | ⚠️ Partial (in ToR output) | Low — extend handbook model builder prompts |
| **Data quality rules extraction** | ❌ Not built | Medium — similar to entity extraction, focused on rules/constraints |
| **Lineage mapping** (handbook → model → systems) | ⚠️ Partial (inventory has system links) | Medium — extend integrated catalog |

---

## Your Immediate Next Steps

### Today (30 minutes setup):
```bash
# 1. Ensure collections are ingested
uv run python -m elt_llm_ingest.runner --cfg load_rag

# 2. Generate integrated catalog (requirement #1 + #2)
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --model qwen2.5:14b

# 3. Extract handbook entities (for requirement #3)
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model --model qwen2.5:14b
```

### Tomorrow (10 minutes):
```bash
# 4. Run gap analysis (requirement #3)
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis
```

### Review Session (1-2 hours):
Open these files in Excel:
1. `fa_terms_of_reference.csv` — your integrated report
2. `fa_gap_analysis.csv` — filter on `HANDBOOK_ONLY` → enhancement candidates
3. `fa_coverage_report.csv` — filter on `ABSENT` or `THIN` → investigate naming/coverage issues

**Questions to ask**:
- For each `HANDBOOK_ONLY`: Should this be added to the conceptual model?
- For each `MODEL_ONLY`: Is this a technical implementation detail?
- For `THIN/ABSENT`: Is the entity named differently in the handbook? (Check `top_chunk_preview`)

---

## Summary: You Have Everything You Need

| Your Requirement | Tool | Command | Output |
|------------------|------|---------|--------|
| **#1: Get handbook context per entity** | `fa_integrated_catalog` | `elt-llm-consumer-integrated-catalog` | `fa_terms_of_reference.csv` |
| **#2: Report with entity + description + context** | `fa_integrated_catalog` | (same) | `fa_terms_of_reference.csv` |
| **#3: Identify enhancement opportunities** | `fa_coverage_validator` | `elt-llm-consumer-coverage-validator --gap-analysis` | `fa_gap_analysis.csv` |

**You are not missing anything fundamental.** The architecture is complete. What you need now is:
1. **Run the tools** (commands above)
2. **Review the outputs** with SMEs (Data Working Group)
3. **Update the LeanIX conceptual model** based on gap analysis
4. **Iterate** (re-run gap analysis to measure improvement)

The only "missing" pieces are **downstream** (logical model derivation, automated LeanIX updates) — but your core challenge is fully addressed by the existing consumer layer.
