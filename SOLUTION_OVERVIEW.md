# FA Enterprise Data Glossary — Solution Overview

**Generated**: March 2026  
**Platform**: ELT LLM RAG (`elt_llm_rag`)  
**Target Audience**: Data Architects, Data Modellers, Governance Stakeholders

---

## Executive Summary

**Challenge**: Generate a comprehensive business glossary from the FA Handbook, reverse-engineered and mapped to the LeanIX conceptual data model as the frame.

**Solution**: A RAG+LLM platform that:
1. Extracts ~152 defined terms from the FA Handbook
2. Maps each term to LeanIX conceptual model entities
3. Enriches with governance rules, definitions, and relationships
4. Produces review-ready JSON output for stakeholder validation
5. Ready for downstream import (Purview, Erwin LDM, MS Fabric)

**Command**:
```bash
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog
```

**Output**: `.tmp/fa_consolidated_catalog.json` — your complete glossary and catalogue.

---

## 1. The Challenge

### 1.1 Business Requirements

**Primary Objective**: Generate a comprehensive business glossary from the FA Handbook, reverse-engineered and mapped to the LeanIX conceptual data model as the organising frame.

**Specific Requirements**:

| # | Requirement | Source | Priority |
|---|-------------|--------|----------|
| 1 | Conceptual model as the organising frame for all artefacts | LeanIX XML | Primary |
| 2 | FA Handbook as SME/business context provider | FA Handbook PDF | Primary |
| 3 | LeanIX Inventory for entity descriptions | LeanIX Excel | Primary |
| 4 | Glossary terms linked to LeanIX Data Objects | Handbook → Model mapping | Primary |
| 5 | Structured export format for downstream import | Purview-ready | Primary |
| 6 | Gap analysis: identify Handbook entities missing from conceptual model | Handbook vs Model comparison | Secondary |
| 7 | Capture governance rules and terms of reference per entity | Handbook extraction | Secondary |

**Stakeholder Expectations**:

- **Data Modelling Team**: Review and validate entity definitions and mappings
- **Business SMEs**: Confirm glossary terms reflect operational reality
- **Data Governance Lead**: Approve governance rules and terms of reference
- **Architecture Review Board**: Endorse conceptual model alignment

**Downstream Integration Path**:

- **Phase 1**: Generate review-ready glossary/catalogue (current deliverable)
- **Phase 2**: Import to Microsoft Purview business glossary + embed in Erwin LDM
- **Phase 3**: Publish to intranet + integrate with MS Fabric semantic model for Copilot

---

## 2. The Solution

### 2.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. INGESTION (elt_llm_ingest)                                   │
│    - FA Handbook PDF → fa_handbook collection                   │
│    - LeanIX XML → fa_leanix_dat_enterprise_conceptual_model_*   │
│    - LeanIX Excel → fa_leanix_global_inventory_*                │
│    Technology: LlamaIndex + ChromaDB (vectorstore + docstore)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. RAG STRATEGY (elt_llm_query)                                 │
│    - Hybrid retrieval: BM25 + Vector                            │
│    - Embedding reranker: nomic-embed-text                       │
│    - LLM synthesis: qwen2.5:14b                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. CONSUMER (elt_llm_consumer)                                  │
│    fa_consolidated_catalog.py — TARGET OUTPUT                   │
│                                                                   │
│    Extracts:                                                     │
│    - Conceptual model entities (docstore scan)                  │
│    - Handbook defined terms (docstore markers)                  │
│    - Inventory descriptions (RAG queries)                       │
│    - Handbook context per entity (RAG + LLM)                    │
│    - Relationships (docstore patterns)                          │
│                                                                   │
│    Output: fa_consolidated_catalog.json                          │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| **Vector Store** | ChromaDB | Persistent, tenant/database isolation |
| **DocStore** | LlamaIndex | Metadata index for structured extraction |
| **Embeddings** | Ollama | `nomic-embed-text` (768 dimensions) |
| **LLM** | Ollama | `qwen2.5:14b` (8K context) |
| **Retrieval** | Hybrid | BM25 + Vector via QueryFusionRetriever |
| **Reranking** | Embedding or Cross-encoder | Cosine similarity or CrossEncoder (top-20 → top-8) |
| **Orchestration** | LlamaIndex | Query engine with synthesis |

### 2.3 RAG Strategy

**Why Hybrid Retrieval?**

| Retriever | Strength | Weakness Alone |
|-----------|----------|----------------|
| **Vector (Dense)** | Semantic similarity ("Club" ≈ "Organisation") | Misses exact terms, IDs, version numbers |
| **BM25 (Sparse)** | Exact keyword matches | Misses semantic equivalence |
| **Hybrid (Both)** |  Captures both semantic and exact matches | — |

**Reranking Matters:**
- Initial retrieval optimises for **speed** (approximate nearest neighbours)
- Reranking optimises for **relevance** (careful cosine similarity scoring)
- Ensures LLM receives the **most pertinent chunks** for synthesis

**Retrieval Flow:**
```
Query → Hybrid Retrieval (BM25 + Vector) → Top-20 candidates
      → Embedding Reranker (cosine similarity) → Top-8 chunks
      → LLM Synthesis (qwen2.5:14b) → Structured JSON output
```

---

## 3. What Was Built

### 3.1 Ingestion Layer (`elt_llm_ingest`)

**Collections Created:**

| Collection | Source | Content | Vectors |
|------------|--------|---------|---------|
| `fa_handbook` | FA Handbook PDF | Governance rules, definitions, obligations | ~3,227 |
| `fa_leanix_dat_enterprise_conceptual_model_*` | LeanIX XML (draw.io) | Conceptual model entities + relationships | ~28 |
| `fa_leanix_global_inventory_*` | LeanIX Excel | System/application descriptions | ~331 |

**Command:**
```bash
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory
```

### 3.2 Query Layer (`elt_llm_query`)

**Capabilities:**
- Single/multi-collection queries
- Hybrid retrieval (BM25 + Vector)
- Embedding reranking
- LLM synthesis with system prompts
- Structured output parsing

**Configuration**: see `elt_llm_ingest/config/rag_config.yaml` and [RAG_STRATEGY.md](RAG_STRATEGY.md) for full config reference.

### 3.3 Consumer Layer (`elt_llm_consumer`)

**Primary Consumer: `fa_consolidated_catalog.py`**

**What It Does:**
1. Scans conceptual model docstores → extracts ~217 entities
2. RAG queries → inventory descriptions per entity
3. Scans Handbook docstore → extracts ~152 defined terms
4. RAG queries → maps Handbook terms to model entities
5. RAG queries → extracts Handbook context (definitions, governance)
6. Scans docstores → extracts relationships
7. Consolidates → classified JSON output

**Command:**
```bash
# Full consolidation (with relationships)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Faster run (skip relationships)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships
```

**Runtime:** ~5-10 minutes

---

## 4. Output Specification

### 4.1 JSON Structure

**File:** `.tmp/fa_consolidated_catalog.json`

**Per Entity:**
```json
{
  "fact_sheet_id": "12345",
  "entity_name": "Club",
  "domain": "PARTY",
  "hierarchy_level": "Level 1",
  "source": "BOTH",
  "leanix_description": "An organisation affiliated with The Association...",
  "formal_definition": "Club means any club which plays the game of football...",
  "domain_context": "Central entity in PARTY domain, relates to Player, Competition...",
  "governance_rules": "Rule A1: Club must be affiliated. Rule C2: Club must appoint...",
  "handbook_term": "Club",
  "mapping_confidence": "high",
  "mapping_rationale": "Direct match to PARTY > Club entity in conceptual model",
  "review_status": "PENDING",
  "review_notes": "",
  "relationships": [
    {
      "target_entity": "Player",
      "relationship_type": "employs",
      "cardinality": "1..*",
      "direction": "unidirectional"
    },
    {
      "target_entity": "Competition",
      "relationship_type": "participates_in",
      "cardinality": "1..*",
      "direction": "unidirectional"
    }
  ]
}
```

### 4.2 Entity Classification

| Source | Meaning | Count |
|--------|---------|-------|
| `BOTH` | Entity in conceptual model AND Handbook | ~150 |
| `LEANIX_ONLY` | In model but not discussed in Handbook | ~50 |
| `HANDBOOK_ONLY` | In Handbook but missing from model (gap) | ~20 |

### 4.3 Review Status Workflow

| Status | Meaning | Action |
|--------|---------|--------|
| `PENDING` | Awaiting review | Data Architect review |
| `APPROVED` | Reviewed and approved | Ready for Purview import |
| `REJECTED` | Reviewed and rejected | Reason in `review_notes` |
| `NEEDS_CLARIFICATION` | Requires SME input | Escalate to business owner |

---

## 5. Requirements Traceability

| Original Requirement | Implementation | Output Field |
|---------------------|--------------|--------------|
| **1. Conceptual model as frame** | Drives entity extraction | `entity_name`, `domain`, `fact_sheet_id` |
| **2. FA Handbook SME context** | RAG extraction per entity | `formal_definition`, `domain_context`, `governance_rules` |
| **3. LeanIX Inventory descriptions** | RAG join by entity | `leanix_description` |
| **4. Glossary terms mapped** | Handbook → Model mapping | `handbook_term`, `mapping_confidence`, `mapping_rationale` |
| **5. Export format** | Structured JSON | Complete JSON file |
| **6. Gap analysis** | Source classification | `source: HANDBOOK_ONLY` |
| **7. Governance rules** | Handbook ToR extraction | `governance_rules` |

---

## 6. Stakeholder Review Process

### 6.1 Review Session

**Attendees:**
- Data Architects
- Business SMEs
- Data Governance Team

**Agenda:**
1. Walk through `fa_consolidated_catalog.json`
2. Review sample entities (Club, Player, Competition, Referee)
3. Validate Handbook mappings (confidence scores, rationale)
4. Identify gaps (HANDBOOK_ONLY entities)
5. Assign review actions

### 6.2 Review Workflow

```bash
# 1. Generate output
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# 2. Open JSON for review
# File: .tmp/fa_consolidated_catalog.json

# 3. During review session:
#    - Update review_status fields
#    - Add review_notes for clarifications
#    - Flag HANDBOOK_ONLY entities for model consideration

# 4. Save updated JSON

# 5. Export for downstream (Phase 2)
# JSON → Purview CSV / Erwin LDM / Fabric semantic model
```

### 6.3 Gap Analysis Discussion

**HANDBOOK_ONLY entities** (not in conceptual model):
- Are these genuine gaps to add to the model?
- Or operational/procedural concepts outside model scope?
- Example: "Academy Player" — sub-type or new entity?

**LEANIX_ONLY entities** (not in Handbook):
- Technical/data entities outside governance scope?
- Or Handbook gaps to address?

---

## 7. Downstream Integration (Phases 2-3)

### 7.1 Phase 2: Purview + Erwin LDM

**Microsoft Purview Import:**
```csv
term,description,steward,domain,related_terms,source_system,status
Club,An organisation affiliated...,Data Office,PARTY,Player; Competition,BOTH,APPROVED
```

**Erwin Logical Data Model:**
- Entities → Logical entities with attributes
- Relationships → Foreign keys, cardinalities
- Definitions → Column comments, business rules

### 7.2 Phase 3: Intranet + MS Fabric / Copilot

**Intranet Publication:**
- Searchable glossary (term → definition)
- Linked to conceptual model visualisation
- Governance rules by entity

**MS Fabric Semantic Model:**
- Glossary terms → semantic model metadata
- Copilot Q&A grounded in authoritative definitions
- Measures/dimensions linked to business context

**Copilot Integration:**
```
User: "What is a Club in FA terms?"
Copilot: "Club means any club which plays the game of football in England 
         and is recognised as such by The Association. [Source: FA Handbook, Rule A1.2]
         Related entities: Player, Competition, County FA."
```

---

## 8. Quality Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Handbook term extraction** | >95% coverage | Terms extracted / Total defined terms |
| **Mapping accuracy** | >90% high confidence | High confidence mappings / Total mappings |
| **Entity coverage** | 100% conceptual model | Entities with Handbook context / Total entities |
| **Relationship extraction** | >80% recall | Relationships extracted / Total in model |
| **Review completion** | 100% entities reviewed | APPROVED+REJECTED / Total entities |

---

## 9. Next Steps

### 9.1 Immediate (This Week)

- [ ] Run `fa_consolidated_catalog.py`
- [ ] Review output with data modelling team
- [ ] Update `review_status` fields
- [ ] Identify HANDBOOK_ONLY entities for model consideration

### 9.2 Phase 2 (Next Month)

- [ ] Transform JSON → Purview import format
- [ ] Import to Purview business glossary
- [ ] Export to Erwin LDM format
- [ ] Embed definitions in logical data model

### 9.3 Phase 3 (Next Quarter)

- [ ] Publish glossary to intranet
- [ ] Integrate with MS Fabric semantic model
- [ ] Configure Copilot grounding
- [ ] Set up ongoing governance workflow

---

## 10. Technical Reference

### 10.1 Commands Quick Reference

```bash
# Ingestion (one-time setup)
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_handbook
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_global_inventory

# Primary output generation
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Faster iteration (skip relationships)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships

# Model override
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --model qwen2.5:14b
```

### 10.2 Output Files

| File | Location | Purpose |
|------|----------|---------|
| `fa_consolidated_catalog.json` | `.tmp/` | Stakeholder review (master output) |
| `fa_consolidated_relationships.json` | `.tmp/` | Relationships with source attribution |

### 10.3 Supporting Consumers

| Consumer | Purpose | When to Use |
|----------|---------|-------------|
| `coverage-validator` | Coverage scoring (STRONG/MODERATE/THIN/ABSENT) | Model refinement cycle |
| `handbook-model` | Handbook-only entity extraction | No LeanIX available; gap discovery |

---

## 11. Conclusion

**What We've Delivered:**

 **Automated glossary extraction** from FA Handbook (~152 terms)  
 **Mapped to conceptual model** with confidence scores  
 **Enriched with governance** — definitions, rules, relationships  
 **Gap analysis** — identifies Handbook-only entities  
 **Review-ready output** — JSON for stakeholder validation  
 **Downstream ready** — Purview, Erwin, Fabric integration  

**Architecture Principles:**

- **RAG-first** — no bespoke parsers, scalable via index queries
- **LLM+RAG** — retrieval for context, LLM for synthesis
- **Hybrid retrieval** — BM25 + Vector for completeness
- **Reranking** — ensures highest quality chunks for LLM
- **Self-contained** — each consumer independent, reproducible

**Business Value:**

- **Time saved**: Manual glossary creation (weeks) → automated (minutes)
- **Quality**: Consistent definitions, traceable to authoritative sources
- **Governance**: Rules and obligations captured per entity
- **Collaboration**: Shared review process, clear ownership
- **Future-ready**: Purview, Erwin, Fabric integration path defined

---

**Contact**: [Your Name]  
**Repository**: `elt_llm_rag`  
**Documentation**: See `elt_llm_consumer/README.md`, `elt_llm_consumer/ARCHITECTURE.md`
