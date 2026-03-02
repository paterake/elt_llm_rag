# ORCHESTRATION.md

**FA Data Governance RAG Platform — Runbook & Roadmap**

**Last Updated**: 2026-03-02  
**Status**: Phase 1 Complete ✅ | Phase 2-5 Planning

---

## Executive Summary

### What Has Been Achieved

**Phase 1 — Data Asset Catalog** ✅ **COMPLETE**

The platform successfully delivers:

| Requirement | Implementation | Status |
|-------------|----------------|--------|
| Conceptual model as the frame | LeanIX XML (217 entities across 11 domain collections) | ✅ |
| FA Handbook providing SME/business context | RAG collection with ~9,673 chunks | ✅ |
| LeanIX Inventory providing entity descriptions | Excel-driven join via `fact_sheet_id` (100% match rate) | ✅ |
| Glossary terms linked to LeanIX Data Objects | `fa_integrated_catalog.json` + `fa_terms_of_reference.json` | ✅ |
| Export to CSV | Consolidated catalog with CSV export | ✅ |

**Key Achievement**: 100% match rate — all 217 conceptual model entities linked to inventory descriptions with FA Handbook governance context.

**New**: Consolidated Catalog script merges LeanIX + Handbook entities with source attribution and CSV export for Purview import.

---

## Current State Assessment

### ✅ What Works

| Component | Status | Command |
|-----------|--------|---------|
| **Ingestion** | ✅ Complete | `uv run python -m elt_llm_ingest.runner --cfg load_rag` |
| **Query (CLI)** | ✅ Complete | `uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture` |
| **Query (GUI)** | ✅ Complete | `uv run python -m elt_llm_api.app` |
| **Integrated Catalog** | ✅ Complete | `elt-llm-consumer-integrated-catalog` |
| **Coverage Validator** | ✅ Complete | `elt-llm-consumer-coverage-validator --gap-analysis` |
| **Handbook Model Builder** | ✅ Complete | `elt-llm-consumer-handbook-model` |
| **Consolidated Catalog** | ✅ Complete | `elt-llm-consumer-consolidated-catalog` |

### ⚠️ What Needs Attention

| Gap | Impact | Priority |
|-----|--------|----------|
| **Stakeholder review workflow** | Review process not yet run | High |
| **Erwin LDM integration** | Phase 2 dependency | Medium |
| **MS Fabric / Copilot integration** | Phase 3 dependency | Low |

---

## Phase 1: Data Asset Catalog (COMPLETE)

### Objective
Produce a structured catalog linking FA Handbook regulatory terms to LeanIX conceptual model entities and inventory descriptions.

### Direction
**Current**: Conceptual Model → Handbook (entity-driven lookup)  
**Requested**: Handbook → Conceptual Model (glossary term reverse engineering)

**Note**: The current implementation uses the conceptual model as the frame (as per original requirement). To achieve the "Handbook-first" approach, use the Handbook Model Builder output as the starting point.

### Deliverables

| File | Location | Description |
|------|----------|-------------|
| `fa_terms_of_reference.json` | `~/.tmp/elt_llm_consumer/` | Structured ToR per entity: definition + domain context + governance |
| `fa_integrated_catalog.json` | `~/.tmp/elt_llm_consumer/` | Combined catalog for bulk use |
| `fa_handbook_candidate_entities.json` | `~/.tmp/elt_llm_consumer/` | Entities discovered from Handbook only |
| `fa_handbook_candidate_relationships.json` | `~/.tmp/elt_llm_consumer/` | Relationships inferred from Handbook |
| `fa_coverage_report.json` | `~/.tmp/elt_llm_consumer/` | Coverage scoring: Model → Handbook |
| `fa_gap_analysis.json` | `~/.tmp/elt_llm_consumer/` | Gap analysis: Handbook → Model |
| `fa_consolidated_catalog.json` | `~/.tmp/elt_llm_consumer/` | **NEW**: Merged LeanIX + Handbook entities with source attribution |
| `fa_consolidated_catalog.csv` | `~/.tmp/elt_llm_consumer/` | **NEW**: CSV export for Purview import |
| `fa_consolidated_relationships.json` | `~/.tmp/elt_llm_consumer/` | **NEW**: Merged relationships with source lineage |

### Entity Classification (in Consolidated Catalog)

| Source | Description | Action Required |
|--------|-------------|-----------------|
| **BOTH** | Entity exists in LeanIX CM and Handbook | Review definition alignment |
| **LEANIX_ONLY** | Entity in LeanIX CM but not discussed in Handbook | May need Handbook update or model review |
| **HANDBOOK_ONLY** | Entity discovered in Handbook but missing from LeanIX CM | **Candidate for conceptual model addition** |

### Review Status Tracking

| Status | Description |
|--------|-------------|
| `PENDING` | Awaiting stakeholder review (default) |
| `APPROVED` | Reviewed and approved for Purview import |
| `REJECTED` | Reviewed and rejected (with reason in `review_notes`) |
| `NEEDS_CLARIFICATION` | Requires SME input before approval |

### Runbook: Generate Phase 1 Outputs

```bash
# Step 1: Ensure collections are ingested
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Step 2: Generate integrated catalog (conceptual model as frame)
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --model qwen2.5:14b

# Step 3: Build candidate model from Handbook only (Handbook-first approach)
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model --model qwen2.5:14b

# Step 4: Run gap analysis (identify Handbook entities missing from Model)
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis

# Step 5: Generate consolidated catalog (merge LeanIX + Handbook with source attribution)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --model qwen2.5:14b

# Step 6 (optional): Enrich HANDBOOK_ONLY entities with additional RAG queries
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --enrich-handbook-only

# Step 7: Review outputs
ls -lh ~/.tmp/elt_llm_consumer/
```

### Review Workflow

**Recommended stakeholder review session**:

1. **Participants**: Data Modeller (Robin Holley), SME (User), Data Lead (Carman/Andy Laurie)
2. **Inputs**: 
   - `fa_consolidated_catalog.json` (complete picture with source attribution)
   - `fa_gap_analysis.json` (what's missing from model)
   - `fa_consolidated_relationships.json` (relationship lineage)
3. **Process**:
   - Review `HANDBOOK_ONLY` entities → decide which to add to LeanIX conceptual model
   - Review `LEANIX_ONLY` entities → verify Handbook coverage is adequate
   - Review `BOTH` entities → ensure definitions align between sources
   - Update `review_status` field in JSON for each entity (APPROVED/REJECTED/NEEDS_CLARIFICATION)
4. **Outputs**: 
   - Approved entity list for Purview import
   - Backlog of entities to add to LeanIX conceptual model
   - Updated JSON with review status

**Post-review CSV export**:
```bash
# After updating review_status in JSON, re-export CSV
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --csv-only
```

---

## Phase 2: Purview + Erwin LDM Integration

### Objective
Import reviewed catalog into Microsoft Purview as a governed business glossary and embed entity definitions/relationships into an Erwin Logical Data Model (LDM).

### Prerequisites
- ✅ Phase 1 outputs complete
- ✅ Stakeholder review completed (review_status fields updated)
- ⏳ Purview access & API credentials
- ⏳ Erwin LDM license + integration method

### Required Enhancements

| Enhancement | Status | Description | Effort |
|-------------|--------|-------------|--------|
| **CSV Export** | ✅ Complete | Purview-compatible CSV with term, description, domain, steward | Low |
| **Structured Citations** | ⏳ Pending | Add source attribution (Handbook section, LeanIX ID) | Low |
| **GraphRAG** | ⏳ Pending | Enable relationship traversal for Erwin LDM | High |
| **Relationship Export** | ⏳ Pending | Export entity relationships (not just definitions) | Medium |

### Runbook: Phase 2 (TBD)

```bash
# Step 1: Ensure consolidated catalog CSV is up to date
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --csv-only

# Step 2: Import to Purview (manual or API)
# TBD: Purview import process
# Expected: Import fa_consolidated_catalog.csv via Purview API or UI

# Step 3: Generate Erwin LDM (GraphRAG required)
# TBD: Erwin integration method
```

### Deliverables
- `purview_glossary.csv` — Business glossary for import (from `fa_consolidated_catalog.csv`)
- `erwin_ldm.json` — Logical data model with entities + relationships
- Import confirmation / error report

---

## Phase 3: Intranet Publishing

### Objective
Publish the catalog to the FA intranet for organisation-wide access.

### Prerequisites
- ✅ Phase 2 complete
- ⏳ Intranet CMS access
- ⏳ Publishing workflow approval

### Considerations

| Aspect | Requirement |
|--------|-------------|
| **Format** | HTML / searchable web interface |
| **Access Control** | Role-based (SMEs, Data Modellers, General Users) |
| **Update Cadence** | Sync with LeanIX refresh cycle |
| **Search** | Full-text search across glossary terms |

### Runbook: Phase 3 (TBD)

```bash
# Step 1: Generate static site / HTML export
# TBD: Publishing mechanism

# Step 2: Deploy to intranet
# TBD: CMS integration

# Step 3: Configure search indexing
# TBD: Search engine integration
```

---

## Phase 4: MS Fabric / Copilot Integration

### Objective
Integrate with MS Fabric's agentic semantic model for use in Microsoft Copilot.

### Prerequisites
- ✅ Phase 3 complete
- ⏳ MS Fabric tenant access
- ⏳ Semantic model configuration
- ⏳ Copilot licensing

### RAG Implications

| Requirement | Description |
|-------------|-------------|
| **Structured Output** | JSON with term, definition, steward, domain, related asset IDs |
| **GraphRAG** | Relationship data feeds semantic model dimensions/facts |
| **Caching** | Repeated Copilot queries across users require response caching |

### Runbook: Phase 4 (TBD)

```bash
# Step 1: Export Fabric-compatible format
# TBD: Semantic model schema

# Step 2: Configure Copilot grounding
# TBD: Fabric integration

# Step 3: Enable caching layer
# TBD: Cache strategy
```

---

## Phase 5: Vendor Assessment & SAD Generation

### Objective
Automate SAD (Solution Architecture Document) generation and vendor assessments using RAG-grounded standards.

### Prerequisites
- ✅ Phase 1-4 complete
- ⏳ SAD templates defined
- ⏳ Vendor assessment criteria documented

### Deliverables
- Auto-generated SADs with consistent structure
- Vendor capability assessments against FA standards
- Compliance checking against reference data (ISO, ONS)

---

## Quick Reference: All Commands

### Ingestion

```bash
# Ingest all collections
uv run python -m elt_llm_ingest.runner --cfg load_rag

# Check collection status
uv run python -m elt_llm_ingest.runner --status

# List ingestion configs
uv run python -m elt_llm_ingest.runner --list

# Reset specific collection (e.g. LeanIX)
uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix

# Full reset
uv run python -m elt_llm_ingest.clean_slate
uv run python -m elt_llm_ingest.runner --cfg load_rag
```

### Query

```bash
# List query profiles
uv run python -m elt_llm_query.runner --list

# Single query (FA sources)
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture -q "What is a Club?"

# Single query (full data management)
uv run python -m elt_llm_query.runner --cfg fa_data_management -q "What are the key PARTY domain entities?"

# Interactive session
uv run python -m elt_llm_query.runner --cfg fa_handbook_only
```

### API / GUI

```bash
# Start Gradio GUI (http://localhost:7860)
uv run python -m elt_llm_api.app
```

### Consumer Scripts (Phase 1 Deliverables)

```bash
# Generate integrated catalog (conceptual model as frame)
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --model qwen2.5:14b

# Generate business glossary (LeanIX inventory as driver)
uv run --package elt-llm-consumer elt-llm-consumer-glossary --model qwen2.5:14b

# Build candidate model from Handbook only
uv run --package elt-llm-consumer elt-llm-consumer-handbook-model --model qwen2.5:14b

# Validate coverage + gap analysis
uv run --package elt-llm-consumer elt-llm-consumer-coverage-validator --gap-analysis

# Generate consolidated catalog (merge LeanIX + Handbook with source attribution)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --model qwen2.5:14b

# Enrich HANDBOOK_ONLY entities with additional RAG queries
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --enrich-handbook-only

# Re-export CSV after review status updates
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --csv-only
```

### Model Options

| Model | Speed | Quality | Use Case |
|-------|-------|---------|----------|
| `qwen2.5:14b` | ~10s/entity | Best | Production runs |
| `mistral-nemo:12b` | ~8s/entity | Good | Alternative |
| `llama3.1:8b` | ~5s/entity | Medium | Development / iteration |

---

## Troubleshooting

### Common Issues

| Issue | Resolution |
|-------|------------|
| **Ollama not running** | `ollama serve` (in separate terminal) |
| **Model not found** | `ollama pull nomic-embed-text` and `ollama pull qwen2.5:14b` |
| **Collections missing** | Run `uv run python -m elt_llm_ingest.runner --cfg load_rag` |
| **Consumer script fails** | Check `~/.tmp/elt_llm_consumer/` exists and is writable |
| **Out of memory** | Reduce batch size or use smaller model (`llama3.1:8b`) |

### Output Location

All consumer outputs written to:
```
~/.tmp/elt_llm_consumer/
```

To change output directory:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-integrated-catalog --output-dir /custom/path
```

---

## Next Steps

### Immediate (Week 1-2)
1. ✅ Run stakeholder review session with Robin Holley, Carman/Andy Laurie
2. ✅ Update `review_status` fields in `fa_consolidated_catalog.json`
3. ⏳ Export final CSV: `--csv-only`
4. ⏳ Define Purview import process

### Short-Term (Month 1-2)
1. ⏳ Implement GraphRAG for relationship traversal
2. ⏳ Establish Erwin LDM integration method
3. ⏳ Phase 2 execution (Purview import)

### Medium-Term (Month 3-6)
1. ⏳ Intranet publishing (Phase 3)
2. ⏳ MS Fabric / Copilot integration (Phase 4)
3. ⏳ SAD / vendor assessment automation (Phase 5)

---

## Contacts

| Role | Name |
|------|------|
| Data Modeller | Robin Holley |
| SME / Stakeholder | [User] |
| Data Lead | Carman / Andy Laurie |

---

## Appendix: File Reference

### Input Sources

| Source | Format | Location |
|--------|--------|----------|
| FA Handbook | PDF | `~/Documents/__data/fa/handbook/` |
| LeanIX Conceptual Model | XML (draw.io) | `~/Documents/__data/leanix/xml/` |
| LeanIX Inventory | Excel | `~/Documents/__data/leanix/inventory/` |
| DAMA-DMBOK | PDF | `~/Documents/__data/dama/` |

### Output Files

| File | Phase | Purpose |
|------|-------|---------|
| `fa_terms_of_reference.json` | 1 | Structured ToR per entity |
| `fa_integrated_catalog.json` | 1 | Combined catalog |
| `fa_handbook_candidate_entities.json` | 1 | Handbook-discovered entities |
| `fa_handbook_candidate_relationships.json` | 1 | Handbook-discovered relationships |
| `fa_coverage_report.json` | 1 | Coverage scoring |
| `fa_gap_analysis.json` | 1 | Gap analysis |
| `fa_consolidated_catalog.json` | 1 | Merged LeanIX + Handbook entities with source attribution |
| `fa_consolidated_catalog.csv` | 1 | CSV export for Purview import |
| `fa_consolidated_relationships.json` | 1 | Merged relationships with source lineage |
| `purview_glossary.csv` | 2 | Purview import (TBD) |
| `erwin_ldm.json` | 2 | Erwin LDM (TBD) |

---

**Document Status**: Living Document  
**Next Review**: After Phase 2 planning
