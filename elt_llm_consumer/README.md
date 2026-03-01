# elt-llm-consumer

Purpose-built products that drive the LLM+RAG infrastructure to produce structured deliverables.

**All commands run from the repository root.**

---

## What This Module Does

`elt_llm_consumer` wraps `elt_llm_query` to produce specific business deliverables — structured CSVs, reports, or exports — by systematically querying the RAG collections at scale.

Unlike interactive query (one question → one answer), consumer scripts batch-process hundreds of entities and write the results to files for stakeholder use.

---

## Prerequisites

```bash
ollama serve
ollama pull nomic-embed-text
ollama pull qwen2.5:14b

# Collections must be ingested first
uv run python -m elt_llm_ingest.runner --cfg load_rag
```

---

## Consumers

| Script | Entry Point | What It Does |
|--------|-------------|--------------|
| `business_glossary.py` | `elt-llm-consumer-glossary` | LeanIX inventory (Excel) → batch catalog CSV via all FA RAG collections |
| `fa_handbook_model_builder.py` | `elt-llm-consumer-handbook-model` | FA Handbook only → candidate entities, relationships, and terms of reference |
| `fa_integrated_catalog.py` | `elt-llm-consumer-integrated-catalog` | Conceptual model (XML) as frame + inventory descriptions + FA Handbook → integrated ToR and catalog |
| `fa_coverage_validator.py` | `elt-llm-consumer-coverage-validator` | Validate model entities against FA Handbook — no LLM, pure retrieval scoring |

---

## 1. Business Glossary Generator

Driven by the **LeanIX inventory Excel**. Queries all FA collections per entity to produce a catalog entry.

```bash
uv run --package elt-llm-consumer elt-llm-consumer-glossary
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model mistral-nemo:12b
uv run --package elt-llm-consumer elt-llm-consumer-glossary --type dataobjects
RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-glossary
```

**Output**: `fa_business_catalog_dataobjects.csv`, `fa_business_catalog_interfaces.csv`

Re-running overwrites the files. Use `RESUME=1` to append to an existing run.

**Columns** (DataObjects): `fact_sheet_id`, `entity_name`, `domain_group`, `hierarchy_level`, `leanix_description`, `catalog_entry`, `model_used`

**Runtime**: ~229 DataObjects × ~10s ≈ 35–40 min on `qwen2.5:14b`

---

## 2. FA Handbook Model Builder

Builds a candidate conceptual model from the **FA Handbook alone** — no LeanIX required. Useful for bootstrapping or validating the LeanIX model against the governance text.

Two-pass process:
- **Pass 1**: Query `fa_handbook` per seed topic → extract defined terms, roles, and concepts
- **Pass 2**: For entity pairs that co-appeared in the same topic → infer relationships
- **Pass 3**: Consolidate → terms of reference per unique term

```bash
# Full run (14 default seed topics)
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model

# Subset of topics
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model \
  --topics Club Player Competition Registration

uv run --package elt-llm-consumer elt-llm-consumer-handbook-model --model qwen2.5:14b
RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-handbook-model
```

**Output** (written to `~/Documents/__data/resources/thefa/`):
```
fa_handbook_candidate_entities.csv       ← term, definition, category, source_topic
fa_handbook_candidate_relationships.csv  ← entity_a, entity_b, relationship description
fa_handbook_terms_of_reference.csv       ← consolidated ToR per unique term
```

**Default seed topics** (14): Club, Player, Official, Referee, Competition, County FA, Registration, Transfer, Affiliation, Discipline, Safeguarding, Governance, Eligibility, Licence

---

## 3. FA Integrated Catalog

The direct implementation of: *"the conceptual model is the frame, the handbook providing the SME content."*

Three-source join:
1. **LeanIX Conceptual Model (XML)** — canonical entity frame: all modelled entities with domain, hierarchy, and relationships
2. **LeanIX Inventory (Excel)** — descriptions joined directly by `fact_sheet_id` (not via RAG)
3. **FA Handbook + Conceptual Model RAG** — governance rules, obligations, domain context per entity

Every entity in the conceptual model gets a terms of reference entry, regardless of whether it has an inventory description.

```bash
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --model qwen2.5:14b
RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog
```

**Output** (written to `~/Documents/__data/resources/thefa/`):
```
fa_terms_of_reference.csv   ← structured: definition + domain context + governance per entity
fa_integrated_catalog.csv   ← combined catalog_entry column for bulk use
```

**ToR columns**: `fact_sheet_id`, `entity_name`, `domain`, `hierarchy_level`, `related_entities`, `leanix_description`, `formal_definition`, `domain_context`, `governance_rules`, `model_used`

**Runtime**: ~217 conceptual model entities × ~10–20s ≈ 35–70 min on `qwen2.5:14b`

---

---

## 4. FA Coverage Validator

Answers: **does the conceptual model contain the right entities?**

Two-direction analysis — no LLM synthesis, pure retrieval scoring (~3-7 min):

**Direction 1 — Model → Handbook** (always runs): for every entity in the LeanIX XML, retrieve FA Handbook chunks and score similarity. Reveals entities that the handbook does not discuss.

**Direction 2 — Handbook → Model** (`--gap-analysis`): normalised name comparison against Consumer 2 output (`fa_handbook_candidate_entities.csv`). Finds concepts the handbook discusses that are absent from the model.

```bash
# Direction 1 only (coverage scoring)
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator

# Direction 1 + Direction 2 (gap analysis, requires Consumer 2 output)
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis

# Recommended workflow: run Consumer 2 first, then validate
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis

RESUME=1 uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator
```

**Output** (written to `~/Documents/__data/resources/thefa/`):
```
fa_coverage_report.csv  ← entity_name, domain, top_score, verdict, top_chunk_preview
fa_gap_analysis.csv     ← normalized_name, model_name, handbook_name, status
```

**Verdict bands** (cosine similarity of top retrieved chunk):

| Verdict | Score | Meaning |
|---------|-------|---------|
| `STRONG` | ≥ 0.70 | Handbook clearly discusses this entity |
| `MODERATE` | 0.55–0.70 | Handbook mentions it; some context available |
| `THIN` | 0.40–0.55 | Weak signal; may be named differently in handbook |
| `ABSENT` | < 0.40 | Not meaningfully present in handbook |

**Gap status** (Direction 2):

| Status | Meaning |
|--------|---------|
| `MATCHED` | Entity name appears in both model and handbook discovery |
| `MODEL_ONLY` | In conceptual model but not discussed in handbook |
| `HANDBOOK_ONLY` | Handbook discusses it; missing from conceptual model |

**Runtime**: ~217 entities × 1-2 s = 3-7 min (embedding retrieval only, no LLM)

---

## Model Options

| Model | Speed | Quality | Notes |
|-------|-------|---------|-------|
| `qwen2.5:14b` | ~10s/entity | Best | Default — strongest structured output |
| `mistral-nemo:12b` | ~8s/entity | Good | Solid alternative |
| `llama3.1:8b` | ~5s/entity | Medium | Fast iteration / dev use |
| `granite3.1-dense:8b` | ~5s/entity | Medium | IBM enterprise tuning |
