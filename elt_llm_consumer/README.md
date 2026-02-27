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

## Business Glossary Generator

Generates a business catalogue CSV by joining the LeanIX inventory (Excel) with FA Handbook and conceptual model content retrieved from RAG.

**Sources queried per entity**:
- `fa_leanix_dat_enterprise_conceptual_model_*` — entity definitions, domain groupings, relationships
- `fa_leanix_global_inventory_*` — descriptions from LeanIX inventory (DataObjects, Interfaces, Applications)
- `fa_handbook` — SME governance content, business rules, definitions
- `fa_data_architecture` — data architecture context

### Run

```bash
# Default: all entity types, qwen2.5:14b model
uv run --package elt-llm-consumer elt-llm-consumer-glossary

# Specify model
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model mistral-nemo:12b
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model llama3.1:8b
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model granite3.1-dense:8b

# Only DataObjects (229 entities)
uv run --package elt-llm-consumer elt-llm-consumer-glossary --type dataobjects

# Only Interfaces (271 data flows)
uv run --package elt-llm-consumer elt-llm-consumer-glossary --type interfaces

# Custom paths
uv run --package elt-llm-consumer elt-llm-consumer-glossary \
  --excel ~/Documents/__data/resources/thefa/LeanIX_inventory.xlsx \
  --output-dir ~/Documents/__data/outputs/glossary
```

### Output

Written to `~/Documents/__data/resources/thefa/`:

```
fa_business_glossary_dataobjects_<timestamp>.csv   ← 229 DataObject entities
fa_business_glossary_interfaces_<timestamp>.csv    ← 271 Interface data flows
```

**DataObjects CSV columns**:

| Column | Source |
|--------|--------|
| `fact_sheet_id` | LeanIX |
| `entity_name` | LeanIX conceptual model |
| `domain_group` | LeanIX (PARTY, AGREEMENTS, PRODUCT, etc.) |
| `hierarchy_level` | LeanIX inventory |
| `leanix_description` | LeanIX inventory (blank for ~99 entities) |
| `catalog_entry` | LLM synthesis from RAG (all FA collections) |
| `model_used` | Ollama model name |

**Interfaces CSV columns**:

| Column | Source |
|--------|--------|
| `fact_sheet_id` | LeanIX |
| `interface_name` | LeanIX inventory |
| `source_system` | LeanIX inventory |
| `target_system` | LeanIX inventory |
| `flow_description` | LeanIX inventory |
| `catalog_entry` | LLM synthesis from RAG |
| `model_used` | Ollama model name |

### Runtime

~229 DataObjects × ~10s each ≈ **35-40 minutes** on `qwen2.5:14b`.
Results are checkpointed every 10 entities — safe to interrupt and resume.

Smaller/faster models (`llama3.1:8b`, `granite3.1-dense:8b`) reduce runtime at the cost of response depth.
