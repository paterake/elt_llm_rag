# ELT LLM RAG — Project Review

**Date**: February 2026  
**Reviewer**: Architecture Assessment  
**Scope**: Full workspace review against README.md and ARCHITECTURE.md requirements

---

## Executive Summary

| Aspect | Status | Notes |
|--------|--------|-------|
| **Architecture Alignment** | ✅ **Strong** | Code structure matches ARCHITECTURE.md diagrams |
| **Module Organisation** | ✅ **Good** | Clean separation: core, ingest, query, api |
| **Documentation** | ✅ **Comprehensive** | README + ARCHITECTURE.md cover current state and roadmap |
| **Missing Roadmap** | 🔴 **Gap** | No standalone ROADMAP.md (roadmap only in ARCHITECTURE.md) |
| **Test Coverage** | 🔴 **Gap** | Test directories exist but are empty |
| **API Module** | 🟡 **Partial** | Basic implementation, not mentioned in README |

---

## 1. Workspace Structure Review

### 1.1 Expected vs Actual

**ARCHITECTURE.md specifies:**
```
elt_llm_rag/
├── elt_llm_core/           # Core RAG infrastructure
├── elt_llm_ingest/         # Document ingestion
├── elt_llm_query/          # Query interface
├── elt_llm_api/            # REST API (optional)
```

**Actual structure:**
```
elt_llm_rag/
├── elt_llm_core/           ✅ Present
├── elt_llm_ingest/         ✅ Present
├── elt_llm_query/          ✅ Present
├── elt_llm_api/            ✅ Present (but minimal)
```

**Verdict**: ✅ All expected modules present and correctly named.

---

### 1.2 Module Dependencies

```
pyproject.toml (workspace root)
├── elt_llm_core              # Base — no internal dependencies
├── elt_llm_ingest            # Depends on: elt_llm_core
├── elt_llm_query             # Depends on: elt_llm_core
└── elt_llm_api               # Depends on: elt_llm_core, elt_llm_query
```

**Dependency Graph:**
```
elt_llm_core
    ↑
    ├── elt_llm_ingest
    ├── elt_llm_query ────→ elt_llm_api
    └──────────────────────→
```

**Verdict**: ✅ Clean dependency structure, no circular dependencies.

---

## 2. Module-by-Module Review

### 2.1 elt_llm_core ✅

**Purpose**: Core RAG infrastructure (ChromaDB, Ollama, config, query engine)

**Files Present:**
| File | Purpose | Status |
|------|---------|--------|
| `config.py` | YAML configuration management | ✅ Complete |
| `models.py` | Ollama embedding/LLM creation | ✅ Complete |
| `vector_store.py` | ChromaDB client, collections, docstore paths | ✅ Complete |
| `query_engine.py` | Query interface, response synthesis | ✅ Complete |
| `__init__.py` | Package init | ✅ Present |

**Alignment with ARCHITECTURE.md:**
- ✅ Section 2.2 describes `config.py`, `vector_store.py`, `models.py`, `query_engine.py`
- ✅ Section 4.1 confirms "Core Infrastructure ✅ Complete"

**Dependencies (pyproject.toml):**
```python
dependencies = [
    "llama-index>=0.12.0",
    "llama-index-readers-file>=0.4.0",
    "llama-index-embeddings-ollama>=0.3.0",
    "llama-index-llms-ollama>=0.4.0",
    "llama-index-vector-stores-chroma>=0.4.0",
    "llama-index-retrievers-bm25>=0.3.0",  # ✅ Hybrid search support
    "chromadb>=0.6.0",
    "ollama>=0.3.0",
    "pyyaml>=6.0",
]
```

**Verdict**: ✅ **Fully aligned** with ARCHITECTURE.md. All components present and functional.

---

### 2.2 elt_llm_ingest ✅

**Purpose**: Document ingestion pipeline with preprocessing and smart change detection

**Files Present:**
| File | Purpose | Status |
|------|---------|--------|
| `runner.py` | Generic runner (--cfg parameter, --status, --list) | ✅ Complete |
| `ingest.py` | Main ingestion pipeline | ✅ Complete |
| `preprocessor.py` | Preprocessor framework (LeanIX, Identity) | ✅ Complete |
| `doc_leanix_parser.py` | LeanIX XML extraction | ✅ Complete |
| `file_hash.py` | SHA256 change detection | ✅ Complete |
| `batch_loader.py` | Batch config loading | ✅ Present |
| `clean_slate.py` | Collection reset utility | ✅ Present |
| `cli.py` | CLI entry point | ✅ Present |

**Alignment with ARCHITECTURE.md:**
- ✅ Section 2.2 describes `runner.py`, `ingest.py`, `preprocessor.py`, `doc_leanix_parser.py`, `file_hash.py`
- ✅ Section 4.2 confirms ingestion pipelines for DAMA, FA Handbook, LeanIX
- ✅ Section 4.3 confirms LeanIXPreprocessor ✅ Complete

**Configs Present:**
| Config | Purpose | Status |
|--------|---------|--------|
| `ingest_dama_dmbok.yaml` | DAMA-DMBOK ingestion | ✅ Present |
| `ingest_fa_handbook.yaml` | FA Handbook ingestion | ✅ Present |
| `ingest_fa_ea_leanix.yaml` | LeanIX conceptual model | ✅ Present |
| `ingest_fa_data_architecture.yaml` | FA Data Architecture | ✅ Present |
| `todo_ingest_fa_ea_sad.yaml` | SAD ingestion | ⚠️ Marked TODO |
| `todo_ingest_fa_supplier_assess.yaml` | Supplier assessment | ⚠️ Marked TODO |
| `rag_config.yaml` | Shared RAG config | ✅ Present |
| `load_rag.yaml` | Batch loading | ✅ Present |

**Verdict**: ✅ **Fully aligned** with ARCHITECTURE.md. TODO configs correctly marked as pending.

---

### 2.3 elt_llm_query ✅

**Purpose**: Query interface with single/multi-collection support and hybrid search

**Files Present:**
| File | Purpose | Status |
|------|---------|--------|
| `runner.py` | Generic runner (--cfg, --list, interactive/single mode) | ✅ Complete |
| `query.py` | Query logic (single/multi-collection, hybrid search) | ✅ Complete |
| `cli.py` | CLI entry point | ✅ Present |

**Alignment with ARCHITECTURE.md:**
- ✅ Section 2.2 describes `runner.py`, `query.py`
- ✅ Section 4.4 confirms query configs present
- ✅ Section 4.1 confirms hybrid search (BM25 + vector) implementation

**Query Configs Present:**
| Config | Collections | Status |
|--------|-------------|--------|
| `dama_only.yaml` | DAMA-DMBOK | ✅ Present |
| `fa_handbook_only.yaml` | FA Handbook | ✅ Present |
| `leanix_only.yaml` | LeanIX | ✅ Present |
| `architecture_focus.yaml` | SAD + LeanIX | ✅ Present |
| `vendor_assessment.yaml` | LeanIX + Supplier | ✅ Present |
| `dama_fa_combined.yaml` | DAMA + FA Handbook | ✅ Present |
| `leanix_fa_combined.yaml` | LeanIX + FA Handbook | ✅ Present |
| `all_collections.yaml` | All collections | ✅ Present |

**Verdict**: ✅ **Fully aligned** with ARCHITECTURE.md. All query configs present.

---

### 2.4 elt_llm_api 🟡

**Purpose**: Programmatic API for querying RAG indices

**Files Present:**
| File | Purpose | Status |
|------|---------|--------|
| `api.py` | API functions (ask_dama) | 🟡 Minimal |
| `__init__.py` | Package init | ✅ Present |

**Alignment with ARCHITECTURE.md:**
- ⚠️ Section 2.2 mentions `elt_llm_api/` but only as "(optional)"
- ⚠️ README.md doesn't mention elt_llm_api at all
- ⚠️ ARCHITECTURE.md Section 2.1 diagram doesn't show API layer

**Current Implementation:**
```python
# api.py — Single function
def ask_dama(question: str, rag_config_path: str | Path | None = None) -> QueryResult:
    """Query DAMA-DMBOK collection."""
```

**Gap Analysis:**
| Expected (per ARCHITECTURE.md vision) | Actual | Status |
|---------------------------------------|--------|--------|
| REST API for programmatic access | ❌ Not implemented | Missing |
| Multi-collection query endpoints | ❌ Not implemented | Missing |
| Authentication/authorization | ❌ Not implemented | Missing |
| API documentation | ❌ Not present | Missing |

**Verdict**: 🟡 **Partially implemented**. Module exists but only has a single convenience function. Not a blocker — ARCHITECTURE.md marks it as optional.

**Recommendation**: Either:
1. **Remove elt_llm_api** until there's a clear use case, OR
2. **Expand it** to be a proper FastAPI/Flask REST API as mentioned in ARCHITECTURE.md Section 5.5 (Purview Integration could use API endpoints)

---

## 3. Configuration Review

### 3.1 RAG Configuration (rag_config.yaml)

**Current Settings:**
```yaml
chroma:
  persist_dir: "../chroma_db"          # ✅ Matches ARCHITECTURE.md
  tenant: "rag_tenants"                 # ✅ Matches
  database: "knowledge_base"            # ✅ Matches

ollama:
  base_url: "http://localhost:11434"    # ✅ Local-only (DPO compliant)
  embedding_model: "nomic-embed-text"   # ✅ Matches
  llm_model: "qwen2.5:14b"              # ✅ Matches ARCHITECTURE.md
  embed_batch_size: 1
  context_window: 8192

chunking:
  strategy: "sentence"                  # ✅ Matches
  chunk_size: 256                       # ⚠️ Different from ARCHITECTURE.md (1024)
  chunk_overlap: 32                     # ⚠️ Different from ARCHITECTURE.md (200)
  sentence_split_threshold: 0.5

query:
  similarity_top_k: 10                  # ✅ Matches
  use_hybrid_search: true               # ✅ BM25 + vector (ARCHITECTURE.md §4.1)
  system_prompt: |                      # ✅ Matches
```

**Chunking Discrepancy:**
| Setting | ARCHITECTURE.md | Actual | Impact |
|---------|-----------------|--------|--------|
| `chunk_size` | 1024 | 256 | 🟡 Smaller chunks = more precise retrieval, more overhead |
| `chunk_overlap` | 200 | 32 | 🟡 Less overlap = less redundancy, potential context loss |

**Verdict**: 🟡 **Minor discrepancy**. Chunking settings differ from documentation. Not a bug — may be intentional optimisation. Update ARCHITECTURE.md to match.

---

### 3.2 Ingestion Configs

**Naming Convention:**
- ✅ `ingest_*.yaml` for active configs
- ✅ `todo_ingest_*.yaml` for pending work
- ✅ Clear, descriptive names

**Content Review:**
```yaml
# ingest_fa_ea_leanix.yaml — Example
collection_name: "fa_ea_leanix"
preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "markdown"
  enabled: true
file_paths:
  - "~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml"
metadata:
  domain: "architecture"
  type: "enterprise_architecture"
  source: "LeanIX"
rebuild: true
```

**Verdict**: ✅ **Fully aligned** with ARCHITECTURE.md Section B.1.

---

### 3.3 Query Configs

**Naming Convention:**
- ✅ `<domain>_only.yaml` for single-collection queries
- ✅ `<domain1>_<domain2>_combined.yaml` for multi-collection
- ✅ Clear, descriptive names

**Content Review:**
```yaml
# architecture_focus.yaml — Example
collections:
  - name: "fa_ea_sad"
    weight: 1.0
  - name: "fa_ea_leanix"
    weight: 1.0
query:
  similarity_top_k: 10
  system_prompt: |
    You are a helpful assistant that answers questions based on architecture documentation.
```

**Verdict**: ✅ **Fully aligned** with ARCHITECTURE.md Section B.2.

---

## 4. Code Quality Review

### 4.1 Type Hints

| Module | Type Hint Coverage | Status |
|--------|-------------------|--------|
| `elt_llm_core` | ✅ Comprehensive (dataclasses, Union, Optional) | Good |
| `elt_llm_ingest` | ✅ Comprehensive | Good |
| `elt_llm_query` | ✅ Comprehensive | Good |
| `elt_llm_api` | ✅ Present | Good |

**Verdict**: ✅ **Excellent** type hint coverage throughout.

---

### 4.2 Error Handling

| Module | Error Handling | Status |
|--------|---------------|--------|
| `elt_llm_core` | ✅ Try/except, logging, graceful degradation | Good |
| `elt_llm_ingest` | ✅ File not found, parse errors, fallback to original | Good |
| `elt_llm_query` | ✅ Exception handling, user-friendly messages | Good |

**Example (ingest.py):**
```python
try:
    reader = SimpleDirectoryReader(input_files=[str(path)])
    docs = reader.load_data()
except Exception as e:
    logger.error("Failed to load %s: %s", path, e)
    # Continues processing other files
```

**Verdict**: ✅ **Robust** error handling with appropriate logging.

---

### 4.3 Logging

| Module | Logging Coverage | Status |
|--------|-----------------|--------|
| `elt_llm_core` | ✅ logger = logging.getLogger(__name__) | Good |
| `elt_llm_ingest` | ✅ Comprehensive debug/info/warning | Good |
| `elt_llm_query` | ✅ Present (suppresses noisy libraries) | Good |

**Verdict**: ✅ **Professional** logging throughout.

---

### 4.4 Documentation (Docstrings)

| Module | Docstring Coverage | Status |
|--------|-------------------|--------|
| `elt_llm_core` | ✅ All classes/functions documented | Excellent |
| `elt_llm_ingest` | ✅ All classes/functions documented | Excellent |
| `elt_llm_query` | ✅ All classes/functions documented | Excellent |

**Example (config.py):**
```python
@dataclass
class ChromaConfig:
    """ChromaDB configuration.

    Attributes:
        persist_dir: Directory for persistent storage.
        tenant: Chroma tenant name.
        database: Chroma database name.
    """
```

**Verdict**: ✅ **Excellent** docstring coverage with clear attribute descriptions.

---

## 5. Test Coverage Review 🔴

### 5.1 Current State

| Module | Test Directory | Test Files | Coverage |
|--------|---------------|------------|----------|
| `elt_llm_core` | ❌ Not present | N/A | 0% |
| `elt_llm_ingest` | ✅ `tests/` | `__init__.py` only | 0% |
| `elt_llm_query` | ✅ `tests/` | `__init__.py` only | 0% |
| `elt_llm_api` | ✅ `tests/` | `test_dama_api.py` | Partial |

**Verdict**: 🔴 **Critical Gap**. Test directories exist but are empty (except api).

---

### 5.2 Missing Tests

**Priority Test Cases:**

```python
# elt_llm_core/tests/test_config.py
- test_rag_config_from_yaml()
- test_rag_config_file_not_found()
- test_chunking_config_defaults()

# elt_llm_core/tests/test_models.py
- test_create_embedding_model()
- test_create_llm_model()
- test_check_ollama_connection()

# elt_llm_ingest/tests/test_ingest.py
- test_load_documents_pdf()
- test_load_documents_file_not_found()
- test_build_index()
- test_run_ingestion()

# elt_llm_ingest/tests/test_preprocessor.py
- test_leanix_preprocessor()
- test_identity_preprocessor()

# elt_llm_query/tests/test_query.py
- test_query_single_collection()
- test_query_multiple_collections()
- test_load_index()
```

**Recommendation**: Add pytest tests for critical paths. Start with:
1. Config loading (foundational)
2. Preprocessor (LeanIX extraction is key differentiator)
3. Query interface (user-facing functionality)

---

## 6. Roadmap Review

### 6.1 Current State

**ARCHITECTURE.md contains:**
- ✅ Section 8: Implementation Roadmap (20 weeks, 5 phases)
- ✅ Section 5: What Needs to Be Built (6 priorities)
- ✅ Section 9: Legal & Compliance Considerations

**Missing:**
- 🔴 No standalone `ROADMAP.md` file
- 🔴 No `TODO.md` or `BACKLOG.md` for tracking
- 🔴 No GitHub Issues or project board linkage

### 6.2 Roadmap Content (ARCHITECTURE.md §8)

| Phase | Weeks | Focus | Status |
|-------|-------|-------|--------|
| **Phase 1: Foundation** | 1-4 | Glossary extractor, reference data | 🟡 In progress |
| **Phase 2: SAD Generator** | 5-8 | SAD template, section generator | ⏳ Not started |
| **Phase 3: ERD Automation** | 9-12 | PlantUML/draw.io export | ⏳ Not started |
| **Phase 4: Purview Integration** | 13-16 | Bi-directional sync | ⏳ Not started |
| **Phase 5: Vendor Assessment** | 17-20 | Vendor comparison generator | ⏳ Not started |

**Verdict**: 🟡 **Roadmap exists but not tracked**. Content is comprehensive but not actionable as a living document.

---

### 6.3 Recommendations

**Create standalone roadmap artifact:**

```markdown
# ROADMAP.md

## Q1 2026 (Weeks 1-12)
- [ ] FAGlossaryPreprocessor (Week 1-4)
- [ ] ISO Reference Data ingestion (Week 1-4)
- [ ] SAD Generator PoC (Week 5-8)
- [ ] ERD Generator (PlantUML) (Week 9-12)

## Q2 2026 (Weeks 13-24)
- [ ] Purview Integration (Week 13-16)
- [ ] Vendor Assessment Generator (Week 17-20)
- [ ] Production hardening (Week 21-24)
```

**Link to GitHub Issues:**
- Create issues for each Phase deliverable
- Tag with priority (P0, P1, P2)
- Link to ARCHITECTURE.md sections

---

## 7. Alignment with Strategic Goals

### 7.1 Data Working Group Credibility

**ARCHITECTURE.md §7 states:**
> "The RAG platform provides traceability that strengthens Data Working Group credibility"

**Current Capabilities:**
| Claim | Evidence Available | Status |
|-------|-------------------|--------|
| "This is a FA standard term" | ✅ FA Handbook RAG collection | Ready |
| "This entity is in the conceptual model" | ✅ LeanIX RAG collection | Ready |
| "This code should conform to ISO" | ⏳ ISO reference data (TODO) | Pending |
| "This system uses Club data" | ✅ LeanIX relationships | Ready |
| "This is the authoritative definition" | ✅ Multi-collection queries | Ready |

**Verdict**: ✅ **80% aligned**. Core traceability in place; reference data catalogue pending.

---

### 7.2 Conceptual Model as the Frame

**ARCHITECTURE.md §3 states:**
> "The conceptual model is the frame — all artefacts link back to business entities in LeanIX"

**Current Implementation:**
- ✅ LeanIX parser extracts entities + relationships
- ✅ Domain groupings (PARTY, AGREEMENT, PRODUCT, etc.) preserved
- ✅ Markdown output links entities to domains
- ⏳ Glossary terms not yet linked to LeanIX entities (FAGlossaryPreprocessor TODO)
- ⏳ Reference data not yet linked (ISO catalogue TODO)

**Verdict**: 🟡 **70% aligned**. Foundation solid; linkage layers pending.

---

### 7.3 DAMA-DMBOK Alignment

**ARCHITECTURE.md §7.3 states:**
> "The RAG platform operationalises DAMA-DMBOK guidance"

**Current Implementation:**
| DAMA KB Area | RAG Implementation | Status |
|--------------|-------------------|--------|
| Data Governance (Ch 3) | FA Handbook + policy queries | ✅ Ready |
| Data Architecture (Ch 4) | LeanIX conceptual model queries | ✅ Ready |
| Data Modelling (Ch 5) | ⏳ ERD generation (TODO) | Pending |
| Reference Data (Ch 8) | ⏳ ISO/ONS catalogue (TODO) | Pending |
| Metadata (Ch 11) | Multi-catalogue integration | 🟡 Partial |

**Verdict**: 🟡 **60% aligned**. Governance + architecture ready; modelling + reference data pending.

---

## 8. Legal & Compliance Review

### 8.1 Data Protection (DPO)

**ARCHITECTURE.md §9.1 states:**
> "Core Principle: All data stays local — nothing leaves The FA's infrastructure"

**Verification:**
| Requirement | Implementation | Status |
|-------------|---------------|--------|
| Local data storage | ✅ `~/Documents/__data/` | Compliant |
| Local vector store | ✅ ChromaDB persistent (local) | Compliant |
| Local LLM | ✅ Ollama localhost:11434 | Compliant |
| No external APIs | ✅ No OpenAI/Anthropic calls | Compliant |
| Deletion capability | ✅ `--delete` flag | Compliant |

**Verdict**: ✅ **Fully compliant** with DPO requirements for local-only deployment.

---

### 8.2 Copyright & IP

**ARCHITECTURE.md §9.2 states:**
> "DAMA-DMBOK2: Medium risk — check corporate membership"

**Current State:**
| Source | Risk | Mitigation | Status |
|--------|------|------------|--------|
| FA Handbook | None (FA-owned) | N/A | ✅ Clear |
| LeanIX exports | None (FA data) | N/A | ✅ Clear |
| DAMA-DMBOK2 | Medium | ⏳ Check corporate membership | ⚠️ Action needed |
| ISO standards | Medium-High | ⏳ Use factually only | ⚠️ Action needed |
| ONS codes | None (OGL license) | N/A | ✅ Clear |

**Verdict**: 🟡 **Action required**. DAMA and ISO licensing needs clarification before production deployment.

---

## 9. Summary: Strengths & Gaps

### 9.1 Strengths ✅

| Area | Strength |
|------|----------|
| **Architecture** | Clean modular design, no circular dependencies |
| **Code Quality** | Type hints, docstrings, error handling all excellent |
| **Documentation** | README + ARCHITECTURE.md comprehensive |
| **DPO Compliance** | Local-only processing, no external APIs |
| **Core Functionality** | Ingestion + query working end-to-end |
| **LeanIX Integration** | Unique capability (XML→Markdown extraction) |
| **Hybrid Search** | BM25 + vector for better retrieval |
| **Smart Ingest** | SHA256 change detection saves reprocessing |

---

### 9.2 Gaps 🔴

| Gap | Impact | Priority |
|-----|--------|----------|
| **No tests** | Risk of regressions, hard to refactor | P0 |
| **No standalone roadmap** | Hard to track progress, not actionable | P1 |
| **API module incomplete** | Limits programmatic integration options | P2 |
| **DAMA/ISO licensing unclear** | Legal risk for production deployment | P0 |
| **Chunking settings mismatch** | Documentation doesn't match implementation | P2 |

---

### 9.3 Recommendations

**Immediate (P0):**
1. **Add pytest tests** for core modules (config, models, preprocessor)
2. **Clarify DAMA licensing** — check FA corporate membership status
3. **Create ROADMAP.md** as standalone, actionable document

**Short-term (P1):**
4. **Implement FAGlossaryPreprocessor** (ARCHITECTURE.md §5.1)
5. **Implement ISO reference data ingestion** (ARCHITECTURE.md §5.2)
6. **Link roadmap to GitHub Issues** for tracking

**Medium-term (P2):**
7. **Expand or remove elt_llm_api** — decide on REST API strategy
8. **Update ARCHITECTURE.md** chunking settings to match implementation
9. **Add query audit logging** (ARCHITECTURE.md §9.4)

---

## 10. Overall Verdict

| Aspect | Score | Notes |
|--------|-------|-------|
| **Architecture** | 9/10 | Clean, modular, well-organised |
| **Code Quality** | 9/10 | Professional-grade code |
| **Documentation** | 8/10 | Comprehensive but chunking mismatch |
| **Testing** | 2/10 | Critical gap |
| **Roadmap** | 6/10 | Content exists, not actionable |
| **Compliance** | 7/10 | DPO good, licensing unclear |
| **Strategic Alignment** | 8/10 | Strong alignment with Data Working Group goals |

**Overall: 7/10 — Strong foundation, production readiness requires tests + licensing clarity**

---

## Appendix: Quick Reference

### A.1 Module Status Summary

| Module | Purpose | Status | Priority |
|--------|---------|--------|----------|
| `elt_llm_core` | Core RAG infrastructure | ✅ Complete | Foundation |
| `elt_llm_ingest` | Document ingestion | ✅ Complete | Foundation |
| `elt_llm_query` | Query interface | ✅ Complete | Foundation |
| `elt_llm_api` | Programmatic API | 🟡 Partial | Optional |

### A.2 Roadmap Priorities

| Priority | Deliverable | ARCHITECTURE.md Section |
|----------|-------------|------------------------|
| P0 | FAGlossaryPreprocessor | §5.1 |
| P0 | ISO Reference Data Catalogue | §5.2 |
| P1 | SAD Generator | §5.3 |
| P1 | ERD Generator | §5.4 |
| P2 | Purview Integration | §5.5 |
| P2 | Vendor Assessment Generator | §5.6 |

### A.3 Test Plan

| Module | Test Files to Create |
|--------|---------------------|
| `elt_llm_core` | `tests/test_config.py`, `tests/test_models.py`, `tests/test_vector_store.py` |
| `elt_llm_ingest` | `tests/test_ingest.py`, `tests/test_preprocessor.py`, `tests/test_leanix_parser.py` |
| `elt_llm_query` | `tests/test_query.py`, `tests/test_runner.py` |

---

**Review Complete**: February 2026  
**Next Review**: After Phase 1 delivery (Week 4)
