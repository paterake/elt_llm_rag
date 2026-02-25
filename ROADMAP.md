# ELT LLM RAG Roadmap

**Last Updated**: February 2026  
**Status**: Living document — update as milestones are completed

---

## Overview

This roadmap tracks the implementation of the ELT LLM RAG platform as defined in [ARCHITECTURE.md](ARCHITECTURE.md).

**Mission**: Make FA architecture knowledge queryable, with the conceptual model as the frame.

**Strategic Alignment**:
- Data Working Group: Traceability from business terms → conceptual model → physical systems
- Architecture Review Board: Auto-generated SADs with consistent structure
- Data Modellers: Conceptual model as the frame for all artefacts

---

## Progress Summary

| Phase | Focus | Weeks | Status | Completion |
|-------|-------|-------|--------|------------|
| **Phase 0: Foundation** | Core infrastructure | Done | ✅ Complete | 100% |
| **Phase 1: Business Catalogues** | Glossary + Reference Data | 1-4 | 🟡 In Progress | 40% |
| **Phase 2: SAD Generator** | Auto-generated SADs | 5-8 | ⏳ Pending | 0% |
| **Phase 3: ERD Automation** | Diagram generation | 9-12 | ⏳ Pending | 0% |
| **Phase 4: Purview Integration** | Microsoft ecosystem | 13-16 | ⏳ Pending | 0% |
| **Phase 5: Vendor Assessment** | Decision support | 17-20 | ⏳ Pending | 0% |

---

## Phase 0: Foundation ✅ COMPLETE

**Timeline**: Completed February 2026

### Deliverables

| Item | Status | Notes |
|------|--------|-------|
| Core RAG infrastructure (`elt_llm_core`) | ✅ Complete | ChromaDB, Ollama, config, query engine |
| Ingestion pipeline (`elt_llm_ingest`) | ✅ Complete | Smart ingest, preprocessors, LeanIX parser |
| Query interface (`elt_llm_query`) | ✅ Complete | Single/multi-collection, hybrid search |
| API module (`elt_llm_api`) | 🟡 Partial | Basic convenience functions only |
| DAMA-DMBOK ingestion | ✅ Complete | ~11,943 chunks indexed |
| FA Handbook ingestion | ✅ Complete | ~9,673 chunks indexed |
| LeanIX ingestion | ✅ Complete | ~2,261 chunks indexed |
| Hybrid search (BM25 + vector) | ✅ Complete | QueryFusionRetriever implemented |

### Documentation

| Document | Status |
|----------|--------|
| README.md | ✅ Complete |
| ARCHITECTURE.md | ✅ Complete |
| MODULE READMEs (core, ingest, query) | ✅ Complete |
| PROJECT_REVIEW.md | ✅ Complete |
| ROADMAP.md (this file) | ✅ Complete |

---

## Phase 1: Business Catalogues 🟡 IN PROGRESS

**Timeline**: Weeks 1-4 (February-March 2026)  
**Owner**: R. Patel

### 1.1 FAGlossaryPreprocessor

**Purpose**: Extract glossary terms from FA Handbook for catalogue integration.

**Implementation**:
- [ ] Create `FAGlossaryPreprocessor` class in `preprocessor.py`
- [ ] Parse FA Handbook PDF/HTML
- [ ] Extract term, definition, cross-references
- [ ] Link to LeanIX entities (by name matching)
- [ ] Output structured Markdown

**Config**:
```yaml
# config/ingest_fa_glossary.yaml
collection_name: "fa_glossary"
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "FAGlossaryPreprocessor"
  output_format: "markdown"
  enabled: true
file_paths:
  - "~/Documents/__data/fa_handbook.pdf"
```

**Status**: ⏳ Not started

**Dependencies**: FA Handbook source (PDF or HTML)

---

### 1.2 ISO Reference Data Catalogue

**Purpose**: Catalogue ISO codes, ONS standards, and FA reference data for conformance checking.

**Implementation**:
- [ ] Create reference data ingestion configs
- [ ] Build conformance checker script
- [ ] Integrate with Workday/Dynamics data validation

**Configs**:
```yaml
# config/iso_reference_data.yaml
collection_name: "iso_reference_data"
file_paths:
  - "~/Documents/__data/reference/iso_3166_countries.csv"
  - "~/Documents/__data/reference/iso_4217_currencies.csv"
  - "~/Documents/__data/reference/ons_codes.csv"
  - "~/Documents/__data/reference/fa_county_codes.csv"
```

**Status**: ⏳ Not started

**Dependencies**: ISO/ONS code sources, FA reference data

---

### 1.3 Legal & Compliance

**Purpose**: Clarify licensing for production deployment.

**Tasks**:
- [ ] Check FA's DAMA International corporate membership status
- [ ] Contact DAMA International if deploying beyond personal use
- [ ] Configure LLM to avoid verbatim reproduction (system prompt)
- [ ] Add copyright disclaimers to output
- [ ] Seek legal review for organisation-wide deployment

**Status**: ⏳ Not started

**Dependencies**: Legal team availability, DAMA International response

---

### 1.4 Test Coverage

**Purpose**: Add pytest tests for critical paths.

**Test Files to Create**:
- [ ] `elt_llm_core/tests/test_config.py`
- [ ] `elt_llm_core/tests/test_models.py`
- [ ] `elt_llm_core/tests/test_vector_store.py`
- [ ] `elt_llm_ingest/tests/test_ingest.py`
- [ ] `elt_llm_ingest/tests/test_preprocessor.py`
- [ ] `elt_llm_ingest/tests/test_leanix_parser.py`
- [ ] `elt_llm_query/tests/test_query.py`

**Status**: ⏳ Not started

**Dependencies**: None

---

### Phase 1 Exit Criteria

- [ ] FAGlossaryPreprocessor implemented and tested
- [ ] ISO reference data ingested and queryable
- [ ] DAMA/ISO licensing clarified
- [ ] Test coverage >60% for core modules

---

## Phase 2: SAD Generator ⏳ PENDING

**Timeline**: Weeks 5-8 (March-April 2026)  
**Owner**: R. Patel + Architecture Team

### 2.1 SAD Template Definition

**Purpose**: Define standard SAD structure aligned with FA architecture standards.

**Tasks**:
- [ ] Review existing SAD templates
- [ ] Define standard sections (Business Context, Data Model, Integrations, etc.)
- [ ] Identify traceability requirements (LeanIX entities, FA Handbook terms)

**Status**: ⏳ Not started

**Dependencies**: Architecture Review Board input

---

### 2.2 SAD Section Generator

**Purpose**: Auto-generate SAD sections from RAG queries.

**Implementation**:
```python
# scripts/generate_sad.py

class SADGenerator:
    def generate_section(self, section_name: str, context: dict) -> str:
        """Generate a single SAD section."""
        
    def generate_full_sad(self, project_name: str, sources: dict) -> str:
        """Generate complete SAD document."""
```

**Sections**:
- [ ] Executive Summary
- [ ] Business Context (FA Handbook + LeanIX)
- [ ] Current Architecture (LeanIX)
- [ ] Proposed Architecture (Workday docs)
- [ ] Data Model (LeanIX entities + relationships)
- [ ] Integrations (LeanIX + Workday docs)
- [ ] Reference Data (ISO catalogue)
- [ ] Security & Compliance (FA Handbook + DAMA)
- [ ] Implementation Roadmap

**Status**: ⏳ Not started

**Dependencies**: Phase 1 (glossary + reference data)

---

### 2.3 Workday Design Doc Ingestion

**Purpose**: Ingest Workday design documents for SAD generation context.

**Tasks**:
- [ ] Create ingestion config for Workday docs
- [ ] Test ingestion with sample design documents
- [ ] Validate chunking for technical specifications

**Config**:
```yaml
# config/ingest_workday_design.yaml
collection_name: "workday_design_docs"
file_paths:
  - "~/Documents/__data/workday/design_docs/*.pdf"
metadata:
  domain: "hr_systems"
  type: "design_specification"
  source: "Workday"
```

**Status**: ⏳ Not started

**Dependencies**: Access to Workday design documents

---

### Phase 2 Exit Criteria

- [ ] SAD Generator PoC (1-2 sections)
- [ ] Workday design docs ingested
- [ ] SAD template aligned with FA standards
- [ ] At least one full SAD generated end-to-end

---

## Phase 3: ERD Automation ⏳ PENDING

**Timeline**: Weeks 9-12 (April-May 2026)  
**Owner**: R. Patel + Robin (Data Modeller)

### 3.1 PlantUML ERD Generator

**Purpose**: Generate ERD diagrams from LeanIX conceptual model.

**Implementation**:
```python
# scripts/generate_erd.py

class ERDGenerator:
    def to_plantuml(self, domain: str = None) -> str:
        """Generate PlantUML ERD."""
        
    def to_drawio(self) -> str:
        """Generate draw.io XML for ERD."""
```

**Status**: ⏳ Not started

**Dependencies**: LeanIX conceptual model (already ingested)

---

### 3.2 draw.io Export

**Purpose**: Generate draw.io diagrams for import back to LeanIX.

**Tasks**:
- [ ] Implement draw.io XML generator
- [ ] Test import to LeanIX
- [ ] Validate visual formatting

**Status**: ⏳ Not started

**Dependencies**: PlantUML generator complete

---

### 3.3 Conceptual → Logical Mapping

**Purpose**: Extend ERDs from conceptual to logical layer.

**Tasks**:
- [ ] Define logical model conventions (with Robin)
- [ ] Map LeanIX entities to logical tables/columns
- [ ] Generate logical ERDs

**Status**: ⏳ Not started

**Dependencies**: Data modeller availability

---

### Phase 3 Exit Criteria

- [ ] ERD Generator (PlantUML + draw.io) working
- [ ] Conceptual model ERDs for all LeanIX domains
- [ ] Logical ERD templates defined
- [ ] At least one domain fully modelled (conceptual → logical)

---

## Phase 4: Purview Integration ⏳ PENDING

**Timeline**: Weeks 13-16 (May-June 2026)  
**Owner**: R. Patel + Data Platform Team

### 4.1 Purview Glossary Export

**Purpose**: Export FA glossary + LeanIX entities to Microsoft Purview.

**Implementation**:
```python
# scripts/purview_sync.py

class PurviewSync:
    def export_glossary_to_purview(self, output_path: str):
        """Export FA glossary to Purview-compatible format."""
```

**Status**: ⏳ Not started

**Dependencies**: Phase 1 (glossary extraction)

---

### 4.2 Purview Schema Import

**Purpose**: Import schema discovery results from Purview into RAG.

**Tasks**:
- [ ] Parse Purview scan results
- [ ] Create ingestion config for schemas
- [ ] Index in ChromaDB for lineage queries

**Status**: ⏳ Not started

**Dependencies**: Purview admin access, scan results available

---

### 4.3 Bi-directional Sync Workflow

**Purpose**: Maintain sync between FA glossary (RAG) and Purview.

**Tasks**:
- [ ] Define sync frequency (daily/weekly)
- [ ] Implement automated sync script
- [ ] Add conflict resolution logic

**Status**: ⏳ Not started

**Dependencies**: Export + import working

---

### Phase 4 Exit Criteria

- [ ] FA glossary exported to Purview
- [ ] Schema discovery results imported to RAG
- [ ] Bi-directional sync workflow running
- [ ] End-to-end lineage queries working

---

## Phase 5: Vendor Assessment ⏳ PENDING

**Timeline**: Weeks 17-20 (June-July 2026)  
**Owner**: R. Patel + Procurement Team

### 5.1 Vendor Assessment Template

**Purpose**: Define standard vendor assessment structure.

**Tasks**:
- [ ] Review existing vendor assessment templates
- [ ] Define evaluation criteria (technical, compliance, cost)
- [ ] Identify traceability requirements (LeanIX capabilities, FA standards)

**Status**: ⏳ Not started

**Dependencies**: Procurement team input

---

### 5.2 Vendor Comparison Generator

**Purpose**: Auto-generate vendor comparison reports from RAG queries.

**Implementation**:
```python
# scripts/generate_vendor_assessment.py

class VendorAssessmentGenerator:
    def generate_comparison(self, vendors: list, criteria: list) -> str:
        """Generate vendor comparison matrix."""
```

**Status**: ⏳ Not started

**Dependencies**: Phase 1 (reference data for compliance checking)

---

### 5.3 Supplier Assessment Ingestion

**Purpose**: Ingest supplier assessment guidelines for RAG queries.

**Tasks**:
- [ ] Create ingestion config for supplier docs
- [ ] Test ingestion with sample assessments
- [ ] Validate retrieval for vendor queries

**Config**:
```yaml
# config/ingest_supplier_assess.yaml
collection_name: "supplier_assess"
file_paths:
  - "~/Documents/__data/procurement/supplier_assessment/*.pdf"
```

**Status**: ⏳ Not started

**Dependencies**: Access to supplier assessment documents

---

### Phase 5 Exit Criteria

- [ ] Vendor Assessment Generator working
- [ ] Supplier comparison reports generated
- [ ] Traceability to requirements validated
- [ ] At least one real vendor assessment completed

---

## Success Metrics

| Metric | Baseline | Phase 1 Target | Phase 3 Target | Phase 5 Target |
|--------|----------|----------------|----------------|----------------|
| SAD authoring time | 2-3 weeks | - | 1-2 weeks | 3-5 days |
| Glossary term lookup | Manual search | <10 seconds | <5 seconds | <5 seconds |
| ERD creation | Manual (days) | - | Automated (minutes) | Automated (minutes) |
| Reference data conformance | Unknown | 50% validated | 80% validated | 95%+ validated |
| Vendor assessment time | 1-2 weeks | - | - | 2-3 days |
| Data Working Group credibility | Subjective | Evidence-based | Strong evidence | Definitive |

---

## Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **DAMA licensing issues** | High | Medium | Check corporate membership early; have fallback (summarise only) |
| **ISO licensing issues** | Medium | Medium | Use codes factually; link to official sources |
| **Data modeller availability** | Medium | High | Start with conceptual-only; involve Robin when available |
| **Purview integration blockers** | High | Medium | Engage Data Platform Team early; start with export-only |
| **Test coverage remains low** | Medium | High | Make tests part of Definition of Done for each phase |

---

## GitHub Issues Mapping

**Create issues for tracking:**

| Phase | Issue Label | Example Issues |
|-------|-------------|----------------|
| Phase 1 | `P1`, `glossary`, `reference-data` | #1 FAGlossaryPreprocessor, #2 ISO reference data ingestion |
| Phase 2 | `P2`, `sad-generator` | #10 SAD template definition, #11 SAD section generator |
| Phase 3 | `P3`, `erd-automation` | #20 PlantUML ERD generator, #21 draw.io export |
| Phase 4 | `P4`, `purview` | #30 Purview glossary export, #31 Purview schema import |
| Phase 5 | `P5`, `vendor-assessment` | #40 Vendor assessment template, #41 Vendor comparison generator |

---

## Appendix: Quick Reference

### A.1 Current Capabilities

| Capability | Status | Query Example |
|------------|--------|---------------|
| DAMA-DMBOK queries | ✅ Ready | "What is data governance?" |
| FA Handbook queries | ✅ Ready | "What are the rules for Club affiliation?" |
| LeanIX conceptual model | ✅ Ready | "What entities are in the PARTY domain?" |
| Multi-collection queries | ✅ Ready | "How does DAMA define data governance vs FA Handbook?" |
| Hybrid search (BM25 + vector) | ✅ Ready | "List all ISO country codes" |

### A.2 Upcoming Capabilities

| Capability | Phase | Expected |
|------------|-------|----------|
| FA Glossary extraction | Phase 1 | Week 4 |
| ISO reference data catalogue | Phase 1 | Week 4 |
| SAD Generator PoC | Phase 2 | Week 8 |
| ERD Generator (PlantUML) | Phase 3 | Week 12 |
| Purview glossary export | Phase 4 | Week 16 |
| Vendor Assessment Generator | Phase 5 | Week 20 |

---

**Next Review**: End of Phase 1 (Week 4)  
**Contact**: Rakesh Patel
