# ELT LLM Consumer

**Purpose**: Batch catalog generation from FA Handbook + LeanIX

---

## Quick Command

### Generate Consolidated Catalog (Primary)
```bash
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY --skip-relationships
```

**Runtime**: ~45-60 min (PARTY domain, 28 entities)  
**Output**: `.tmp/fa_consolidated_catalog_party.json`

**Options**:
- `--domain PARTY` — Filter to single domain
- `--skip-relationships` — Skip relationship extraction (faster)
- `--model qwen3.5:9b` — Override LLM model

---

## All Commands

| Command | Purpose | Runtime |
|---------|---------|---------|
| `elt-llm-consumer-consolidated-catalog` | **Primary** — Generate structured catalog | ~45-60 min |
| `elt-llm-consumer-handbook-model` | Extract entities from Handbook alone | ~5-7 min |
| `elt-llm-consumer-coverage-validator` | Validate model coverage (no LLM) | ~3-5 min |

---

## Typical Workflow

### 1. Generate Catalog
```bash
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --domain PARTY --skip-relationships
```

### 2. Review Output
```bash
# Open .tmp/fa_consolidated_catalog_party.json
# Review with Data Architects
# Update review_status fields (APPROVED/REJECTED/NEEDS_CLARIFICATION)
```

### 3. Compare with Agent (Optional)
```bash
# Run agent catalog (faster)
uv run --package elt-llm-agent elt-llm-agent-consolidated-catalog --domain PARTY

# Compare outputs
uv run --package elt-llm-agent python -m elt_llm_agent.compare_catalogs
```

---

## Documentation

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 7-step pipeline, output interpretation |

---

## When to Use

| Use Case | Tool |
|----------|------|
| Stakeholder review, Purview import | `elt_llm_consumer` |
| Quick scan, debugging, exploration | `elt_llm_agent` |

---

## Performance

| Domain | Entities | Runtime |
|--------|----------|---------|
| PARTY | 28 | ~45-60 min |
| All domains | 175 | ~3-4 hours |
