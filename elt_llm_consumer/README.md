# elt-llm-consumer

Purpose-built products that drive the LLM+RAG infrastructure to produce structured deliverables.

**All commands run from the repository root.**

---

## What This Module Does

`elt_llm_consumer` wraps `elt_llm_query` to produce specific business deliverables — structured JSON files — by systematically querying the RAG collections at scale.

Unlike interactive query (one question → one answer), consumer scripts batch-process hundreds of entities and write the results to files for stakeholder use.

**Output format**: All consumers produce **JSON** (not CSV) to properly support multi-line content, hierarchical structures, and nested fields from combined data sources.

**Output location**: All generated files are written to `project/.tmp/` by default (configurable via `--output-dir`).

---

## Prerequisites

```bash
# 1. Start Ollama
ollama serve
ollama pull nomic-embed-text
ollama pull qwen2.5:14b

# 2. Ingest collections (if not already done)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
```

---

## Quick Start: Target Output

**FA Consolidated Catalog** — your primary deliverable for stakeholder review:

```bash
# Full consolidation (entities + Handbook context + relationships)
# Runtime: ~5-10 min
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Faster run (skip relationship extraction)
# Runtime: ~3-5 min
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships

# With specific model override
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --model qwen2.5:14b
```

**Output**:
- `.tmp/fa_consolidated_catalog.json` ← **Your target output**
- `.tmp/fa_consolidated_relationships.json` ← Relationships (if not skipped)

**What it answers (7 requirements)**:
1. ✅ Entities from the conceptual model
2. ✅ Handbook-only entities (not in conceptual model)
3. ✅ LeanIX inventory descriptions
4. ✅ FA Handbook context (SME definition, glossary, ToR, governance)
5. ✅ Relationships from conceptual model
6. ✅ Relationships from inventory
7. ✅ Relationships from Handbook

---

## All Consumers

| # | Script | Entry Point | Purpose | Runtime |
|---|--------|-------------|---------|---------|
| ⭐ | `fa_consolidated_catalog.py` | `elt-llm-consumer-consolidated-catalog` | **Target output** — merged catalog with all 7 requirements | ~5-10 min |
| 1 | `fa_integrated_catalog.py` | `elt-llm-consumer-integrated-catalog` | Conceptual model + Handbook context (ToR per entity) | ~35-70 min |
| 2 | `fa_handbook_model_builder.py` | `elt-llm-consumer-handbook-model` | Extract candidate entities from Handbook alone | ~20-40 min |
| 3 | `fa_coverage_validator.py` | `elt-llm-consumer-coverage-validator` | Validate model coverage against Handbook (no LLM) | ~3-7 min |
| 4 | `business_glossary.py` | `elt-llm-consumer-glossary` | LeanIX inventory → business glossary via RAG | ~35-40 min |

---

## 1. FA Consolidated Catalog ⭐

**File**: `fa_consolidated_catalog.py`

**Purpose**: Single consolidated catalog merging all sources — the target output for stakeholder review.

**Architecture** (RAG+LLM only — no direct file parsing):
```
Step 1: Scan conceptual model docstores → ~217 entities
Step 2: RAG query → Inventory descriptions per entity
Step 3: Scan Handbook docstore → ~152 defined terms
Step 4: RAG query → Map Handbook terms → Model entities
Step 5: RAG query → Handbook context per entity (governance, definitions)
Step 6: Scan docstores → Relationships
Step 7: Consolidate → JSON output
```

**Usage**:
```bash
# Full consolidation
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Skip relationships (faster)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships

# Model override
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --model qwen2.5:14b
```

**Output**:
```
.tmp/fa_consolidated_catalog.json       ← Merged catalog with all 7 requirements
.tmp/fa_consolidated_relationships.json ← Relationships with source attribution
```

**JSON structure** (per entity):
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
1. Run consumer → generates JSON
2. Review with Data Architects
3. Update `review_status` fields in JSON (APPROVED/REJECTED/NEEDS_CLARIFICATION)
4. Import to Purview or downstream systems

---

## 2. FA Integrated Catalog

**File**: `fa_integrated_catalog.py`

**Purpose**: Generate Terms of Reference (ToR) for each conceptual model entity.

**Usage**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog

# Targeted re-run for specific entities
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog \
  --entities 'Club,Player,Referee'

# Resume after interruption
RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog
```

**Output**:
```
.tmp/fa_terms_of_reference.json  ← ToR per entity
.tmp/fa_integrated_catalog.json  ← Combined catalog
```

**Runtime**: ~217 entities × 10-20s ≈ 35-70 min

---

## 3. FA Handbook Model Builder

**File**: `fa_handbook_model_builder.py`

**Purpose**: Extract candidate entities and relationships from FA Handbook alone (no LeanIX required).

**Usage**:
```bash
# Full run (14 default seed topics)
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model

# Subset of topics
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model \
  --topics Club Player Competition

# Resume after interruption
RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-handbook-model
```

**Output**:
```
.fa_handbook_candidate_entities.json       ← Terms, definitions, categories
.fa_handbook_candidate_relationships.json  ← Inferred relationships
.fa_handbook_terms_of_reference.json       ← Consolidated ToR per term
```

**Default seed topics** (14): Club, Player, Official, Referee, Competition, County FA, Registration, Transfer, Affiliation, Discipline, Safeguarding, Governance, Eligibility, Licence

**Runtime**: ~14 topics × 20-30s ≈ 5-7 min

---

## 4. FA Coverage Validator

**File**: `fa_coverage_validator.py`

**Purpose**: Validate conceptual model coverage against FA Handbook.

**Two-direction analysis**:
- **Direction 1** (always runs): Model → Handbook coverage scoring
- **Direction 2** (`--gap-analysis`): Handbook → Model gap detection

**Usage**:
```bash
# Coverage scoring only
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator

# Gap analysis (requires handbook-model output)
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis

# Recommended workflow
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis
```

**Output**:
```
.fa_coverage_report.json  ← Coverage scores per entity
.fa_gap_analysis.json     ← Gap analysis (MATCHED / MODEL_ONLY / HANDBOOK_ONLY)
```

**Verdict bands**:
| Verdict | Score | Meaning |
|---------|-------|---------|
| `STRONG` | ≥ 0.70 | Handbook clearly discusses this entity |
| `MODERATE` | 0.55-0.70 | Some governance context available |
| `THIN` | 0.40-0.55 | Weak signal; may be named differently |
| `ABSENT` | < 0.40 | Not meaningfully present in handbook |

**Runtime**: ~217 entities × 1-2s = 3-7 min (no LLM, retrieval only)

---

## 5. Business Glossary Generator

**File**: `business_glossary.py`

**Purpose**: Generate business glossary from LeanIX inventory via RAG queries.

**Usage**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-glossary

# By type
uv run --package elt-llm-consumer elt-llm-consumer-glossary --type dataobjects
uv run --package elt-llm-consumer elt-llm-consumer-glossary --type interfaces

# Resume after interruption
RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-glossary
```

**Output**:
```
.fa_business_catalog_dataobjects.json
.fa_business_catalog_interfaces.json
```

**Runtime**: ~229 DataObjects × 10s ≈ 35-40 min

---

## Model Options

| Model | Speed | Quality | Use Case |
|-------|-------|---------|----------|
| `qwen2.5:14b` | ~10s/entity | Best | Default — strongest structured output |
| `mistral-nemo:12b` | ~8s/entity | Good | Solid alternative |
| `llama3.1:8b` | ~5s/entity | Medium | Fast iteration / dev use |
| `granite3.1-dense:8b` | ~5s/entity | Medium | IBM enterprise tuning |

---

## Recommended Workflow

**For target output (Consolidated Catalog)**:
```bash
# 1. Ingest sources (if not done)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory

# 2. Generate consolidated catalog
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships

# 3. Review output with Data Architects
# Open: .tmp/fa_consolidated_catalog.json

# 4. Update review_status fields in JSON

# 5. Import to downstream systems
```

**For conceptual model enhancement**:
```bash
# 1. Extract Handbook entities
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model

# 2. Run gap analysis
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis

# 3. Review gaps
# Open: .tmp/fa_gap_analysis.json
# Look for: HANDBOOK_ONLY entities (candidates for model addition)

# 4. Update LeanIX conceptual model

# 5. Re-ingest and re-validate
```
