# ELT LLM RAG Architecture

**Workspace**: `elt_llm_rag`  
**Purpose**: Retrieval-Augmented Generation (RAG) platform for FA architecture knowledge, data governance, and automated documentation generation.

**Strategic Alignment**:
- **Data Working Group**: Strengthen credibility through traceability to conceptual models
- **FA Handbook**: Business glossary and policy foundation
- **DAMA-DMBOK2 (2nd Edition)**: Data management best practices
- **LeanIX**: Enterprise architecture source of truth

---

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Current Architecture](#2-current-architecture)
  - [2.1 High-Level Overview](#21-high-level-overview)
  - [2.2 Module Structure](#22-module-structure)
  - [2.3 Technology Stack](#23-technology-stack)
  - [2.4 Retrieval vs Generation Architecture](#24-retrieval-vs-generation-architecture)
- [3. Conceptual Model Alignment](#3-conceptual-model-alignment)
- [4. What's Built](#4-whats-built)
- [5. What Needs to Be Built](#5-what-needs-to-be-built)
- [6. Business Catalogue Opportunities](#6-business-catalogue-opportunities)
- [7. Data Working Group Value](#7-data-working-group-value)
- [8. Implementation Roadmap](#8-implementation-roadmap)
- [9. Legal & Compliance Considerations](#9-legal--compliance-considerations)

---

## 1. Executive Summary

### 1.1 Purpose

This RAG platform transforms how FA architecture knowledge is:
- **Captured**: From SADs, LeanIX, FA Handbook, DAMA-DMBOK, FDM, Confluence
- **Queried**: Natural language questions across multiple knowledge domains — including in real-time during architecture consultations
- **Generated**: Automated SADs, ERDs, vendor assessments, glossaries
- **Validated**: SADs and designs checked against FA standards before ACB submission
- **Analysed**: Query logs surface what knowledge is missing, stale, or inconsistently applied — input to SAD/ACB process review

### 1.2 Strategic Value

| Stakeholder | Value |
|-------------|-------|
| **Data Working Group** | Traceability from business terms → conceptual model → physical systems |
| **Architecture Review Board** | Auto-generated SADs with consistent structure |
| **Data Modellers** | Conceptual model as the frame for all artefacts |
| **Project Teams** | Query-based access to standards, glossaries, patterns |

### 1.3 Core Principle

> **The conceptual model is the frame** — all artefacts (SADs, glossaries, catalogues, ERDs) link back to business entities in LeanIX, grounded in the FA Handbook and DAMA-DMBOK.

---

## 2. Current Architecture

### 2.1 High-Level Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Knowledge Sources                                │
├─────────────────┬─────────────────┬─────────────────┬───────────────────┤
│   FA Handbook   │    LeanIX XML   │   DAMA-DMBOK    │   Workday Docs    │
│   (PDF/HTML)    │  (draw.io)      │   (PDF)         │   (PDF/DOCX)      │
├─────────────────┼─────────────────┼─────────────────┼───────────────────┤
│      FDM        │   Confluence    │                 │                   │
│  (Excel/PDF)    │   (HTML scrape) │                 │                   │
└────────┬────────┴────────┬────────┴────────┬────────┴─────────┬─────────┘
         │                 │                 │                  │
         ↓                 ↓                 ↓                  ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                        Ingestion Layer (elt_llm_ingest)                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Preprocessors                                                   │    │
│  │  - LeanIXPreprocessor: XML → Markdown (assets + relationships)   │    │
│  │  - FAGlossaryPreprocessor: PDF/HTML → structured glossary (TODO) │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Chunking + Embedding (Ollama: nomic-embed-text)                 │    │
│  │  - Sentence splitter (LlamaIndex)                               │    │
│  │  - Smart change detection (SHA256 file hashing)                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Vector Store (ChromaDB)                                         │    │
│  │  - Tenant: rag_tenants                                           │    │
│  │  - Database: knowledge_base                                      │    │
│  │  - Collections: per source (fa_leanix_*, dama_dmbok, etc.)       │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                         Query Layer (elt_llm_query)                      │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Hybrid Search                                                   │    │
│  │  - BM25 (keyword) + Vector (semantic)                            │    │
│  │  - Multi-collection queries                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Embedding Reranker                                              │    │
│  │  - Cosine similarity re-scoring via nomic-embed-text (Ollama)   │    │
│  │  - Replaces flat RRF scores with discriminative relevance scores │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  LLM Synthesis (Ollama: qwen2.5:14b)                              │    │
│  │  - Grounded responses with source attribution                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────┐
│                         Output Generation                                │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │  SAD Generator  │  │  ERD Generator  │  │  Vendor Assessment Gen  │  │
│  │  (TODO)         │  │  (TODO)         │  │  (TODO)                 │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Module Structure

```
elt_llm_rag/
├── elt_llm_core/           # Core RAG infrastructure
│   ├── config.py           # YAML configuration management
│   ├── vector_store.py     # ChromaDB client, tenant/db/collection
│   ├── models.py           # Ollama embedding/LLM models
│   └── query_engine.py     # Query interface, response synthesis
│
├── elt_llm_ingest/         # Document ingestion
│   ├── runner.py           # Generic runner (--cfg parameter)
│   ├── ingest.py           # Ingestion pipeline
│   ├── preprocessor.py     # Preprocessor framework
│   ├── doc_leanix_parser.py # LeanIX XML extraction
│   ├── file_hash.py        # Smart change detection
│   └── config/             # Ingestion configs
│       ├── ingest_fa_ea_leanix.yaml
│       ├── ingest_dama_dmbok.yaml
│       ├── ingest_fa_handbook.yaml
│       └── ...
│
├── elt_llm_query/          # Query interface
│   ├── runner.py           # Generic runner (--cfg parameter)
│   ├── query.py            # Single/multi-collection queries
│   └── llm_rag_profile/    # RAG profiles (collections + persona + settings)
│       ├── architecture_focus.yaml
│       ├── vendor_assessment.yaml
│       ├── leanix_fa_combined.yaml
│       └── ...
│
└── elt_llm_api/            # REST API (optional)
    └── api.py
```

### 2.3 Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| **Embedding Model** | Ollama: `nomic-embed-text` | 768 dimensions |
| **LLM** | Ollama: `qwen2.5:14b` | Context: 8192 |
| **Vector Store** | ChromaDB | Tenant/DB/Collection |
| **Chunking** | LlamaIndex | Sentence splitter |
| **Hybrid Search** | BM25 + Vector | QueryFusionRetriever |
| **Reranker** | Ollama: `nomic-embed-text` | Embedding cosine similarity |
| **Preprocessing** | Custom Python | LeanIX XML→Markdown |
| **Dependency Mgmt** | uv | Python 3.11-3.13 |

---

### 2.4 Retrieval vs Generation Architecture

The RAG system has two distinct layers with a clear separation of concerns:

#### Layer 1: Retrieval (Find the Right Information)

**Technologies**: LlamaIndex + ChromaDB + BM25

**Purpose**: Search your document collections to find the most relevant chunks.

**Output**: Top-K chunks with relevance scores — **NOT an answer**.

| Component | Role | Analogy |
|-----------|------|---------|
| ChromaDB | Vector (semantic) search | Google for meaning |
| BM25 | Keyword (exact) search | Ctrl+F for terms |
| LlamaIndex | Orchestrates retrieval | Librarian finding books |

**Why Hybrid Search?**

Your documents have two types of queries:

1. **Semantic queries** (Vector excels):
   ```
   Query: "How does the FA handle data quality?"
   Vector finds: "Data quality management ensures fitness for purpose..."
   (Semantically similar, even though exact words differ)
   ```

2. **Keyword queries** (BM25 excels):
   ```
   Query: "What does Chapter 7 Section 4.2 say about Club affiliations?"
   BM25 finds: "Chapter 7, Section 4.2: Club affiliations must..."
   (Exact term matching — vectors might miss specific section references)
   ```

**Hybrid = Best of both worlds**

#### Layer 2: Generation (Synthesize an Answer)

**Technology**: Ollama LLM (`qwen2.5:14b`)

**Purpose**: Read the retrieved chunks and generate a grounded answer.

**Input**: Query + Top-K chunks from Layer 1

**Output**: Natural language response with source citations.

**Example**:
```
Query: "What are the FA's data governance responsibilities?"

LLM Response:
"The Data Working Group is responsible for:
1. Defining data policies and standards (FA Handbook, Chapter 7)
2. Establishing decision rights and accountabilities (DAMA-DMBOK, Ch.3)
3. Maintaining traceability from business terms to systems"

[Sources: fa_handbook, dama_dmbok, fa_leanix_relationships]
```

#### Why This Separation Matters

| Without Retrieval (LLM Only) | With Retrieval (RAG) |
|------------------------------|----------------------|
| Generic knowledge from training | Specific to YOUR documents |
| May hallucinate details | Grounded in actual content |
| No citations | Source attribution |
| "Data governance typically involves..." | "The Data Working Group is responsible for..." |

**The key insight**: Your LLM is only as good as the retrieval layer feeding it. Garbage in = garbage out. That's why you invest in hybrid search + reranking — to ensure the LLM sees the **most relevant** context before generating an answer.

#### The Reranker's Role

The **embedding reranker** sits between Layer 1 and Layer 2:

```
Retrieval (Top-20) → Reranker (re-scores by relevance) → Top-8 → LLM
```

**Purpose**: The initial retrieval uses fast approximations (vector similarity + BM25 scores). The reranker does a more careful scoring pass to ensure the **most relevant** chunks reach the LLM.

**Implementation**: Uses cosine similarity between query and chunk embeddings (via `nomic-embed-text` in Ollama). No external dependencies required.

---

#### Ollama: Two Models, Three Calls

Ollama is the local AI runtime. It serves both models with no cloud calls.

| Model | Size | Role |
|-------|------|------|
| `nomic-embed-text` | ~274MB | Embedding — converts text to 768-dim vectors |
| `qwen2.5:14b` | ~9GB | LLM — synthesises the final answer |

`nomic-embed-text` is called **three times** per query lifecycle:

| Stage | When | Purpose |
|-------|------|---------|
| **Ingest** | Once per chunk (at ingest time) | Generate vectors stored in ChromaDB |
| **Query** | Once per query | Embed the query for vector similarity search |
| **Rerank** | Once per query (20 candidates) | Re-score retrieved chunks by cosine similarity |

`qwen2.5:14b` is called **once** per query — only at the synthesis step.

**Consequence**: `nomic-embed-text` cannot be swapped without re-ingesting all collections (the stored vectors would be incompatible). Switching the LLM is a one-line config change with no data impact.

---

## 3. Conceptual Model Alignment

### 3.1 The Frame: FA Enterprise Conceptual Data Model

The LeanIX conceptual model defines **domain groups** and **entities**:

```
┌─────────────────────────────────────────────────────────────────┐
│                    FA Enterprise Conceptual Data Model           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  PARTY                    AGREEMENT                              │
│    ├─ Individual            ├─ Contract                          │
│    ├─ Organisation          ├─ Policy                            │
│    └─ Club                  └─ Rule                              │
│                                                                  │
│  PRODUCT                  TRANSACTION                            │
│    ├─ Competition           ├─ Match                             │
│    ├─ Course                ├─ Application                       │
│    └─ Membership            ├─ Payment                           │
│                                                                  │
│  CHANNEL                  LOCATION                               │
│    ├─ Digital               ├─ Stadium                           │
│    ├─ Broadcast             ├─ Training Ground                   │
│    └─ In-Person             └─ Office                            │
│                                                                  │
│  REFERENCE DATA           ASSET                                  │
│    ├─ Country (ISO 3166)    ├─ Data Object                       │
│    ├─ Currency (ISO 4217)   ├─ Application                       │
│    └─ Codes (ONS)           └─ System                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Traceability Matrix

| Artefact | Links To | Source | Status |
|----------|----------|--------|--------|
| **SAD Sections** | LeanIX entities + relationships | Auto-generated | TODO |
| **Business Glossary** | FA Handbook definitions | Extracted | TODO |
| **Reference Data** | ISO codes, ONS, FA standards | Catalogued | TODO |
| **ERDs** | Conceptual → Logical → Physical | Generated | TODO |
| **Data Lineage** | Source → Target flows | LeanIX + Purview | TODO |
| **Vendor Assessments** | Supplier capabilities vs. requirements | Generated | TODO |

### 3.3 DAMA-DMBOK Alignment

| DAMA KB Area | RAG Collection | Use Case |
|--------------|----------------|----------|
| **Data Governance** | `dama_dmbok` + `fa_handbook` | Policy queries |
| **Data Architecture** | `fa_leanix_*` + `fa_ea_sad` | Model queries |
| **Data Quality** | `dama_dmbok` + supplier assessments | DQ rule generation |
| **Reference Data** | `iso_reference_data` (TODO) | Standards conformance |
| **Metadata Management** | All collections + Purview | Catalogue integration |

---

## 4. What's Built

### 4.1 Core Infrastructure ✅

See [Section 2.4](#24-retrieval-vs-generation-architecture) for the retrieval and generation architecture.

| Component | Status | Description |
|-----------|--------|-------------|
| **ChromaDB Integration** | ✅ Complete | Tenant/database/collection support |
| **Ollama Models** | ✅ Complete | Embedding + LLM configuration |
| **Hybrid Search** | ✅ Complete | BM25 + Vector via QueryFusionRetriever |
| **Embedding Reranker** | ✅ Complete | Cosine similarity re-scoring (no external dependencies) |
| **Configuration** | ✅ Complete | YAML-based configs |
| **Smart Ingest** | ✅ Complete | SHA256 file change detection |

### 4.2 Ingestion Pipelines ✅

For detailed ingestion documentation, see [elt_llm_ingest/README.md](../elt_llm_ingest/README.md).

| Collection | Documents | Chunks | Status |
|------------|-----------|--------|--------|
| `dama_dmbok` | DAMA-DMBOK2 (PDF) | ~11,943 | ✅ Ingested |
| `fa_handbook` | FA Handbook (PDF) | ~9,673 | ✅ Ingested |
| `fa_leanix_*` (11 collections) | LeanIX XML (draw.io) — split by domain | 15 | ✅ Ingested |
| `fa_ea_sad` | SAD (PDF) | TBD | ⏳ Config ready |
| `supplier_assess` | Supplier docs | TBD | ⏳ Config ready |

### 4.3 Query Configs ✅

For detailed query documentation, see [elt_llm_query/README.md](../elt_llm_query/README.md).

| Config | Collections | Use Case |
|--------|-------------|----------|
| `dama_only.yaml` | DAMA-DMBOK | Data management queries |
| `fa_handbook_only.yaml` | FA Handbook | Policy/glossary queries |
| `leanix_only.yaml` | LeanIX | Architecture queries |
| `leanix_relationships.yaml` | `fa_leanix_relationships`, `fa_leanix_overview` | Domain-level relationships |
| `architecture_focus.yaml` | SAD + LeanIX | Architecture decisions |
| `vendor_assessment.yaml` | LeanIX + Supplier | Vendor evaluation |
| `dama_fa_combined.yaml` | DAMA + FA Handbook | Cross-domain queries |
| `leanix_fa_combined.yaml` | LeanIX + FA Handbook | Business-aligned architecture |
| `fa_data_management.yaml` | All collections | Full data management queries |

---

## 5. What Needs to Be Built

### 5.0 Priority 0 (Quick Win): LeanIX Glossary → CSV Export 🔴

**Purpose**: Export glossary terms and Conceptual Data Model entities from LeanIX to CSV — agreed deliverable for the Data Working Group.

**Implementation**: Extend `doc_leanix_parser.py` with a CSV export method:

```python
# scripts/export_leanix_glossary_csv.py

def export_glossary_csv(leanix_xml: str, output_path: str):
    """Export LeanIX entities + domain groups to CSV for glossary/catalogue use.

    Columns: domain_group, entity_name, parent_entity, relationships, fact_sheet_id
    """
    extractor = LeanIXExtractor(leanix_xml)
    extractor.parse_xml()
    extractor.extract_all()

    rows = []
    for asset in extractor.assets.values():
        rows.append({
            "domain_group": asset.parent_group,
            "entity_name": asset.label,
            "fact_sheet_id": asset.fact_sheet_id,
            "relationships": "; ".join([r.target_label for r in extractor.relationships if r.source_label == asset.label]),
        })

    pd.DataFrame(rows).to_csv(output_path, index=False)
```

**Value**: Enables Robin + colleagues to review/extend the glossary in Excel; feeds Purview import.

---

### 5.1 Priority 1: Business Glossary Extractor 🔴

**Purpose**: Extract glossary terms from FA Handbook for catalogue integration.

**Implementation**:
```python
# elt_llm_ingest/preprocessor.py

class FAGlossaryPreprocessor(BasePreprocessor):
    """Extract glossary terms from FA Handbook PDF/HTML.
    
    Output structure:
    # FA Glossary
    
    ## Term: Club
    - Definition: An organisation affiliated with The FA...
    - Source: FA Handbook 2024, §7.2
    - Related Terms: Party, Organisation, Affiliation
    - ISO/Standards: -
    - LeanIX Entity: PARTY > Organisation > Club
    
    ## Term: Country
    - Definition: A sovereign state as defined by...
    - Source: FA Handbook 2024, §3.1
    - Related Terms: Location, Reference Data
    - ISO/Standards: ISO 3166-1 alpha-2
    - LeanIX Entity: REFERENCE DATA > Country
    """
    
    def preprocess(self, input_file: str, output_path: str) -> PreprocessorResult:
        # Parse FA Handbook (PDF or HTML)
        # Locate glossary section
        # Extract term, definition, cross-references
        # Link to LeanIX entities (by name matching)
        # Output structured Markdown
        pass
```

**Dependencies**:
- FA Handbook source (PDF or HTML scrape from https://www.thefa.com/football-rules-governance/lawsandrules/fa-handbook)
- LeanIX entity name matching logic

**Value**:
- Glossary terms linked to conceptual model entities
- Traceability: term → definition → LeanIX entity → systems using it

---

### 5.2 Priority 2: Reference Data Catalogue 🔴

**Purpose**: Catalogue ISO codes, ONS standards, and FA reference data for conformance checking.

**Implementation**:
```yaml
# config/iso_reference_data.yaml

collection_name: "iso_reference_data"

file_paths:
  - "~/Documents/__data/reference/iso_3166_countries.csv"
  - "~/Documents/__data/reference/iso_4217_currencies.csv"
  - "~/Documents/__data/reference/ons_codes.csv"
  - "~/Documents/__data/reference/fa_county_codes.csv"

metadata:
  domain: "reference_data"
  type: "standards"
  conformance_targets:
    - Workday: Country codes
    - Dynamics: Currency codes
    - GP: Supplier codes
```

**Enhancement**: Build a conformance checker:
```python
# scripts/check_conformance.py

def check_conformance(source_system: str, field: str, values: list) -> dict:
    """Check if source system values conform to reference data.
    
    Example:
    check_conformance("Workday", "country", ["GB", "US", "XX"])
    → {"valid": ["GB", "US"], "invalid": ["XX"], "suggestions": {"XX": "GB"}}
    """
    
    # Query RAG for reference data
    result = query_collection("iso_reference_data", f"ISO 3166 code {values}")
    
    # Validate against extracted codes
    # Report non-conformance
    pass
```

**Value**:
- Identify data quality issues (e.g., Workday not conforming to ONS)
- Automate reference data management
- Support data quality initiatives

---

### 5.1b Priority 1b: Business Context Builder — Glossary Linked to Conceptual Model 🔴

**Purpose**: Link FA Handbook glossary terms to LeanIX conceptual model entities to produce a unified business context layer. This is the core deliverable agreed with colleagues — the conceptual model is the frame, the FA Handbook provides the SME definitions on top of it.

**Context**: Three separate outputs need to be joined:
1. FA Handbook glossary terms (from FAGlossaryPreprocessor)
2. LeanIX conceptual model entities (from LeanIXPreprocessor / CSV export)
3. Integration metadata — what is held, owned, transmitted to/from each entity

**Implementation**:
```python
# scripts/build_business_context.py

class BusinessContextBuilder:
    """Link FA Handbook glossary terms to LeanIX conceptual model entities.

    Output: Unified business context — each entry has:
    - Term (from FA Handbook)
    - Definition (FA Handbook source + section)
    - LeanIX entity (domain group + entity name + fact_sheet_id)
    - Related terms (FA Handbook cross-references)
    - Systems holding this data (LeanIX relationships)
    - Systems transmitting this data (integrations)
    - ISO/reference data standards (if applicable)
    """

    def build(self, glossary: list[dict], leanix_entities: list[dict]) -> list[dict]:
        """Match glossary terms to LeanIX entities by name + semantic similarity."""
        # 1. Exact name matching (e.g. "Club" → PARTY > Club)
        # 2. Fuzzy/semantic matching for synonyms (e.g. "Member" → Individual)
        # 3. Manual override file for known mismatches
        # 4. Output: linked glossary CSV + RAG-optimised Markdown
```

**Output formats**:
- **CSV**: Shareable with Robin, Data Working Group, feeds Purview import
- **Markdown**: Ingested into ChromaDB as `fa_business_context` collection
- **DSI layer**: Glossary above Data Source Inventory — drill down from term → entity → systems holding/transmitting it → lineage

**Value**:
- Single source of truth: business term → definition → conceptual model entity → physical systems
- Enables the lineage the colleague described: "glossary sits above DSI, allows drill down showing lineage between sources and targets"
- Feeds Purview business context population (agreed with Robin)
- Queryable: "What is a Club, which systems hold Club data, and where does it flow?"

---

### 5.2b Priority 2b: FDM Ingestion + Conceptual Model Alignment 🔴

**Purpose**: Ingest the Functional Data Model (FDM) and align it with the LeanIX conceptual model as the frame.

**Context**: The conceptual model is the frame — the FDM provides business process-aligned enrichment on top. Agreed with colleague: "There's something we can do at the start to align the FDM and conceptual model."

**Implementation**:
- Create `ingest_fa_fdm.yaml` ingestion config (source: Excel/PDF)
- Build `FDMPreprocessor` to extract entities, attributes, and domain groupings
- Create `fdm_leanix_alignment.yaml` query config to cross-reference FDM entities against LeanIX conceptual model
- Identify gaps: entities in FDM not in LeanIX, and vice versa

**Value**:
- Conceptual model enriched with FDM business process context
- Alignment gaps surfaced for Robin + Data Modeller review
- Combined frame for ERD generation (conceptual → logical)

---

### 5.2c Priority 2c: Confluence Scraper 🟡

**Purpose**: Ingest FA Confluence pages (architecture decisions, standards, process docs) into the RAG knowledge base.

**Implementation**:
```python
# elt_llm_ingest/confluence_scraper.py

class ConfluenceScraper:
    """Scrape Confluence pages and convert to Markdown for RAG ingestion.

    - Authenticates via Confluence REST API or local HTML export
    - Converts page content to clean Markdown
    - Preserves page hierarchy and metadata (space, author, last updated)
    - Outputs to standard ingest format for ChromaDB
    """
```

**Config**:
```yaml
# config/ingest_confluence.yaml
collection_name: "confluence_arch"
preprocessor:
  class: "ConfluencePreprocessor"
spaces:
  - "DATA"        # Data team space
  - "ARCH"        # Architecture space
metadata:
  domain: "internal_knowledge"
  type: "confluence"
```

**Value**:
- Architecture decisions and ADRs queryable alongside LeanIX + FA Handbook
- Institutional knowledge not captured in formal documents made accessible

---

### 5.3 Priority 3: SAD Generator 🟡

**Purpose**: Auto-generate SAD sections from LeanIX + Workday docs + FA Handbook.

**Implementation**:
```python
# scripts/generate_sad.py

class SADGenerator:
    """Generate SAD documents from source artefacts."""
    
    def __init__(self):
        self.rag_config = RagConfig.from_yaml("rag_config.yaml")
    
    def generate_section(self, section_name: str, context: dict) -> str:
        """Generate a single SAD section.
        
        Args:
            section_name: e.g., "Business Context", "Data Model", "Integrations"
            context: Pre-retrieved context from RAG queries
        
        Returns:
            Generated section text (FA SAD template format)
        """
        
        # Build prompt with context
        prompt = f"""
        Generate the {section_name} section for a Solution Architecture Definition.
        
        Context:
        - Conceptual Model: {context.get('leanix_summary', '')}
        - Business Glossary: {context.get('glossary_terms', '')}
        - Design Decisions: {context.get('workday_decisions', '')}
        - Standards: {context.get('dama_guidance', '')}
        
        Format: Follow FA SAD template structure.
        Include traceability to LeanIX entities where applicable.
        """
        
        # Query multi-collection RAG
        result = query_collections(
            ['fa_leanix_overview', 'fa_leanix_relationships', 'fa_handbook', 'dama_dmbok'],
            prompt,
            self.rag_config
        )
        
        return result.response
    
    def generate_full_sad(self, project_name: str, sources: dict) -> str:
        """Generate complete SAD document.
        
        Sections:
        1. Executive Summary
        2. Business Context
        3. Current Architecture
        4. Proposed Architecture
        5. Data Model
        6. Integrations
        7. Reference Data
        8. Security & Compliance
        9. Implementation Roadmap
        """
        
        sections = [
            "Executive Summary",
            "Business Context",
            "Current Architecture",
            "Proposed Architecture",
            "Data Model",
            "Integrations",
            "Reference Data",
            "Security & Compliance",
            "Implementation Roadmap",
        ]
        
        sad_content = f"# Solution Architecture Definition: {project_name}\n\n"
        
        for section in sections:
            sad_content += f"## {section}\n\n"
            sad_content += self.generate_section(section, sources)
            sad_content += "\n\n"
        
        return sad_content
```

**SAD Template Sections**:
| Section | RAG Sources | Generation Logic |
|---------|-------------|------------------|
| Business Context | FA Handbook + LeanIX | Extract relevant business domain |
| Data Model | LeanIX conceptual | Export entity/relationship lists |
| Integrations | LeanIX + Workday docs | Map system interfaces |
| Reference Data | ISO catalogue + FA codes | List conformance requirements |
| Security & Compliance | FA Handbook + DAMA | Policy extraction |

**Value**:
- Reduce SAD authoring time by 70%
- Ensure consistency across SADs
- Maintain traceability to conceptual model

---

### 5.3b Priority 3b: SAD Quality Checker 🟡

**Purpose**: Review submitted SADs against FA standards — flag gaps, inconsistencies, and missing traceability to LeanIX entities. Complements the SAD generator; more defensible value proposition.

**Context**: EA feedback — the consultation and review process is the value. This supports that by making review faster and more consistent, not bypassing it.

**Implementation**:
```python
# scripts/check_sad.py

class SADChecker:
    """Check a submitted SAD against FA architecture standards.

    Checks:
    - Required sections present (FA SAD template)
    - Business entities referenced exist in LeanIX conceptual model
    - Reference data conforms to ISO/ONS standards
    - Integration patterns consistent with reference architecture
    - DAMA-DMBOK data management principles applied

    Output: Structured report with pass/fail/warning per check, with citations.
    """
```

**Value**:
- Consistent pre-ACB review quality gate
- Reduces back-and-forth in consultation by surfacing gaps early
- Traceable to FA standards (not subjective reviewer opinion)

---

### 5.4 Priority 4: ERD Generator 🟡

**Purpose**: Generate ERD diagrams (conceptual, logical, physical) from LeanIX.

**Implementation**:
```python
# scripts/generate_erd.py

class ERDGenerator:
    """Generate ERD diagrams from LeanIX conceptual model."""
    
    def __init__(self, leanix_xml: str):
        self.extractor = LeanIXExtractor(leanix_xml)
        self.extractor.parse_xml()
        self.extractor.extract_all()
    
    def to_plantuml(self, domain: str = None) -> str:
        """Generate PlantUML ERD.
        
        Args:
            domain: Optional domain filter (e.g., "PARTY", "PRODUCT")
        
        Returns:
            PlantUML script
        """
        
        uml = ["@startuml", "!theme plain", ""]
        
        # Filter assets by domain
        assets = self.extractor.assets.values()
        if domain:
            assets = [a for a in assets if a.parent_group == domain]
        
        # Generate entities
        for asset in assets:
            uml.append(f'entity "{asset.label}" {{')
            # Add attributes from LeanIX (if available)
            uml.append(f"  *fact_sheet_id: {asset.fact_sheet_id}")
            uml.append("}")
        
        # Generate relationships
        for rel in self.extractor.relationships:
            if rel.source_label in [a.label for a in assets] and \
               rel.target_label in [a.label for a in assets]:
                cardinality = self._convert_cardinality(rel.cardinality)
                uml.append(f'"{rel.source_label}" {cardinality}-- "{rel.target_label}"')
        
        uml.append("@enduml")
        return "\n".join(uml)
    
    def to_drawio(self) -> str:
        """Generate draw.io XML for ERD."""
        # Similar logic, output draw.io format
        pass
    
    def _convert_cardinality(self, er_notation: str) -> str:
        """Convert ER notation to PlantUML syntax."""
        mapping = {
            "0..*-0..*": "o--o",
            "1..*-0..*": "||--o",
            "0..*-1..1": "o--||",
            "1..1-1..1": "||--||",
        }
        return mapping.get(er_notation, "--")
```

**Output Formats**:
- **PlantUML**: Text-based, version-controlled
- **draw.io**: Visual, importable to LeanIX
- **Mermaid**: GitHub/GitLab native

**Value**:
- Always up-to-date ERDs (regenerate from LeanIX)
- Consistent notation across projects
- Traceability to business entities

---

### 5.4b Priority 4b: Query Analytics & Usage Logging 🟡

**Purpose**: Log what questions are asked, what can't be answered, and what sources are used — surfaces knowledge gaps and stale content.

**Context**: EA feedback: query logs are useful input to the SAD/ACB review — real data about what people actually need to know, not what we think they need.

**Implementation**:
```python
# elt_llm_core/query_logger.py

class QueryLogger:
    """Log queries, sources retrieved, and response quality signals.

    Captures:
    - Query text and timestamp
    - Collections searched
    - Sources retrieved (doc name, chunk, score)
    - Whether a confident answer was returned
    - Unanswered / low-confidence queries flagged for gap analysis
    """
```

**Value**:
- Evidence for SAD/ACB process review: what knowledge is missing
- Identify stale documents (never retrieved = not useful)
- Usage patterns inform roadmap prioritisation

---

### 5.5 Priority 5: Purview Integration 🟢

**Purpose**: Bridge business glossary (FA Handbook + LeanIX) with technical metadata (Purview).

**Implementation**:
```python
# scripts/purview_sync.py

class PurviewSync:
    """Synchronise FA glossary + LeanIX with Microsoft Purview."""
    
    def export_glossary_to_purview(self, output_path: str):
        """Export FA glossary + LeanIX entities to Purview-compatible format.
        
        Output format: CSV or JSON for Purview import
        """
        
        # Query RAG for glossary terms
        glossary = query_collection("fa_handbook", "all glossary terms")
        
        # Query RAG for LeanIX entities
        entities = query_collection("fa_leanix_overview", "all entities")
        
        # Map to Purview schema
        purview_terms = []
        for term in glossary:
            purview_terms.append({
                "qualifiedName": term["name"],
                "description": term["definition"],
                "source": "FA Handbook",
                "relatedEntities": self._find_leanix_links(term),
            })
        
        # Export
        with open(output_path, 'w') as f:
            json.dump(purview_terms, f, indent=2)
    
    def import_schema_from_purview(self, purview_scan_results: str):
        """Import schema discovery results from Purview into RAG.
        
        Ingest scanned schemas for lineage queries.
        """
        
        # Parse Purview scan results
        # Create ingestion config for schemas
        # Index in ChromaDB
        pass
```

**Integration Points**:
| Direction | Data | Purpose |
|-----------|------|---------|
| FA → Purview | Glossary terms + definitions | Business context in Purview |
| FA → Purview | LeanIX entities | Link technical assets to business |
| Purview → FA | Schema discovery results | Lineage queries in RAG |
| Purview → FA | Data lineage | End-to-end flow visualisation |

**Value**:
- Business users see glossary in Purview
- Technical users see lineage in RAG queries
- Bi-directional traceability

---

### 5.6 Priority 6: Vendor Assessment Generator 🟢

**Purpose**: Auto-generate vendor assessment reports from RAG queries.

**Implementation**:
```python
# scripts/generate_vendor_assessment.py

class VendorAssessmentGenerator:
    """Generate vendor assessment reports."""
    
    def generate_comparison(self, vendors: list, criteria: list) -> str:
        """Generate vendor comparison matrix.
        
        Args:
            vendors: List of vendor names
            criteria: Evaluation criteria (e.g., "data cataloguing", "lineage")
        
        Returns:
            Comparison report
        """
        
        # Query RAG for each vendor
        vendor_info = {}
        for vendor in vendors:
            result = query_collections(
                ['fa_leanix_overview', 'supplier_assess'],
                f"Vendor {vendor} capabilities for {criteria}"
            )
            vendor_info[vendor] = result.response
        
        # Generate comparison matrix
        report = "# Vendor Assessment Report\n\n"
        report += "## Evaluation Criteria\n\n"
        for criterion in criteria:
            report += f"- {criterion}\n"
        
        report += "\n## Vendor Comparison\n\n"
        for vendor, info in vendor_info.items():
            report += f"### {vendor}\n\n"
            report += info
            report += "\n\n"
        
        return report
```

**Value**:
- Objective, evidence-based assessments
- Traceability to requirements (LeanIX + FA standards)
- Reduced manual effort

---

## 6. Business Catalogue Opportunities

### 6.1 Catalogue Types

| Catalogue | Source | RAG Collection | Status |
|-----------|--------|----------------|--------|
| **Business Glossary** | FA Handbook | `fa_glossary` | TODO |
| **Reference Data** | ISO/ONS/FA codes | `iso_reference_data` | TODO |
| **Data Objects** | LeanIX conceptual | `fa_leanix_*` | ✅ Partial |
| **Systems/Applications** | LeanIX | `fa_leanix_*` | ✅ Partial |
| **Data Flows** | LeanIX relationships | `fa_leanix_relationships` | ✅ Partial |
| **Policies/Standards** | FA Handbook + DAMA | `fa_handbook` + `dama_dmbok` | ✅ Partial |
| **Schemas** | Purview scans | `purview_schemas` | TODO |
| **Reports/Dashboards** | Workday/Dynamics | `report_catalogue` | TODO |

### 6.2 Catalogue Integration Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Unified Business Catalogue                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │  Business        │  │  Reference       │  │  Data         │  │
│  │  Glossary        │  │  Data            │  │  Objects      │  │
│  │  (FA Handbook)   │  │  (ISO/ONS)       │  │  (LeanIX)     │  │
│  └────────┬─────────┘  └────────┬─────────┘  └───────┬───────┘  │
│           │                     │                     │          │
│           └─────────────────────┼─────────────────────┘          │
│                                 ↓                                 │
│                    ┌────────────────────────┐                    │
│                    │   RAG Query Interface  │                    │
│                    │   (Multi-collection)   │                    │
│                    └───────────┬────────────┘                    │
│                                ↓                                  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │                    Output Generation                         │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │ │
│  │  │ SAD Reports │  │ ERD Diagrams│  │ Vendor Assessments  │  │ │
│  │  └─────────────┘  └─────────────┘  └─────────────────────┘  │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 6.3 Catalogue Query Examples

**Example 1: Glossary + Conceptual Model**
```
Query: "What is a Club and what systems use it?"

RAG retrieves:
- FA Handbook: Definition of "Club"
- LeanIX: Club entity in PARTY domain
- LeanIX: Systems connected to Club (Workday, Dynamics)
- Purview: Tables/columns storing Club data

Response:
"A Club is an organisation affiliated with The FA (FA Handbook §7.2). 
In the conceptual model, Club is a subtype of PARTY > Organisation. 
Systems using Club data include:
- Workday: HR_HIERARCHY table (CLUB_ID column)
- Dynamics: tbl_Club table
Data lineage shows Club data flows from Workday → Data Warehouse → Reports."
```

**Example 2: Reference Data Conformance**
```
Query: "Check if Workday country codes conform to ISO 3166"

RAG retrieves:
- ISO 3166 standard codes
- Workday schema (from Purview scan)
- Conformance rules (FA Handbook)

Response:
"Workday country codes partially conform to ISO 3166:
✓ Valid: GB, US, FR, DE (95% of records)
✗ Invalid: UK (should be GB), XX (unknown)
Recommendation: Update Workday validation rules to enforce ISO 3166."
```

**Example 3: Lineage Query**
```
Query: "Show me lineage for Member data"

RAG retrieves:
- LeanIX: Member entity in PARTY domain
- LeanIX: Relationships to systems
- Purview: Table/column mappings
- FA Handbook: Member definition

Response:
"Member data lineage:
1. Source: Workday (WD_MEMBER table)
2. Integration: Azure Data Factory → Data Warehouse
3. Warehouse: DW_MEMBER dimension
4. Consumption: Power BI (Member Reports)
Business definition: A Member is an Individual with active affiliation (FA Handbook §5.1)."
```

---

## 7. Data Working Group Value

### 7.1 Strengthening Credibility

The RAG platform provides **traceability** that strengthens Data Working Group credibility:

| Claim | Evidence (from RAG) |
|-------|---------------------|
| "This is a FA standard term" | → FA Handbook section reference |
| "This entity is in the conceptual model" | → LeanIX fact sheet ID |
| "This code should conform to ISO" | → ISO 3166/4217 reference |
| "This system uses Club data" | → LeanIX relationship diagram |
| "This is the authoritative definition" | → FA Handbook + DAMA cross-reference |

### 7.2 Data Working Group Use Cases

| Use Case | RAG Support |
|----------|-------------|
| **Term Standardisation** | Query glossary across FA Handbook + DAMA |
| **Conceptual Model Review** | Extract entities/relationships from LeanIX |
| **FDM + Conceptual Model Alignment** | Cross-reference FDM entities against LeanIX frame; surface gaps |
| **Reference Data Governance** | Conformance checking against ISO/ONS |
| **Project Architecture Review** | Auto-generate SAD sections for consistency |
| **SAD Quality Checking** | Pre-ACB review: flag gaps, missing LeanIX traceability, non-conformance |
| **Consultation Co-pilot** | Real-time in-meeting queries: "what does DAMA/FA Handbook say about X?" |
| **SAD/ACB Process Review** | Query logs as evidence: what knowledge is missing, stale, or inconsistently applied |
| **Vendor Evaluation** | Generate assessment reports with traceability |
| **Data Quality Investigations** | Trace non-conformance to source systems |
| **Purview Catalogue Population** | Export glossary + LeanIX entities → Purview business context (agreed with Robin) |
| **DSI Lineage** | Glossary above Data Source Inventory — drill down showing lineage sources to targets |

### 7.3 DAMA-DMBOK Alignment

The RAG platform operationalises DAMA-DMBOK guidance:

| DAMA KB Area | RAG Implementation |
|--------------|-------------------|
| **Data Governance (Ch 3)** | FA Handbook + policy queries |
| **Data Architecture (Ch 4)** | LeanIX conceptual model queries |
| **Data Modelling (Ch 5)** | ERD generation from LeanIX |
| **Data Storage (Ch 6)** | Purview schema integration |
| **Data Security (Ch 7)** | Compliance queries |
| **Reference Data (Ch 8)** | ISO/ONS catalogue + conformance |
| **Data Warehousing (Ch 9)** | Lineage queries |
| **Documents/Content (Ch 10)** | SAD/glossary generation |
| **Metadata (Ch 11)** | Multi-catalogue integration |
| **Data Quality (Ch 12)** | Conformance checking |

---

## 8. Implementation Roadmap

### 8.1 Phase 1: Foundation (Weeks 1-4)

| Task | Owner | Status | Priority |
|------|-------|--------|----------|
| LeanIX → CSV glossary export | R. Patel | TODO | Quick win — agreed with colleague |
| ISO Reference Data ingestion (ISO 3166, ISO 4217, ONS) | R. Patel | TODO | Urgent — active Workday/Dynamics conformance issues |
| FAGlossaryPreprocessor | R. Patel | TODO | Foundation for all catalogue work |
| FDM ingestion + conceptual model alignment | R. Patel + Robin | TODO | Agreed as starting point |
| FA Handbook HTML scraper | R. Patel | TODO | |
| Multi-collection query optimisation | R. Patel | ✅ Complete | |

**Deliverables**:
- LeanIX entities exported to CSV (shareable with Data Working Group)
- Reference data catalogue (ISO 3166, ISO 4217, ONS) with conformance checker
- Glossary extraction from FA Handbook linked to LeanIX entities
- FDM ingested and aligned against conceptual model; gaps identified

---

### 8.2 Phase 2: SAD Quality + Generation (Weeks 5-8)

| Task | Owner | Status |
|------|-------|--------|
| SAD Quality Checker (pre-ACB review tool) | R. Patel | TODO |
| Confluence scraper + ingestion | R. Patel | TODO |
| Query analytics / usage logging | R. Patel | TODO |
| SAD template definition | R. Patel + team | TODO |
| SAD section generator (PoC) | R. Patel | TODO |
| Workday design doc ingestion | R. Patel | TODO |

**Deliverables**:
- SAD Quality Checker — pre-ACB gap analysis with FA standard citations
- Confluence knowledge base ingested
- Query logs capturing usage patterns for SAD/ACB process review input
- SAD Generator PoC (1-2 sections)
- Workday design doc ingestion pipeline

---

### 8.3 Phase 3: ERD Automation (Weeks 9-12)

| Task | Owner | Status |
|------|-------|--------|
| PlantUML ERD generator | R. Patel | TODO |
| draw.io export | R. Patel | TODO |
| Conceptual → Logical mapping | R. Patel + Robin | TODO |
| ERD generation workflow | R. Patel | TODO |

**Deliverables**:
- ERD Generator (PlantUML + draw.io)
- Conceptual model ERDs for all LeanIX domains
- Logical ERD templates

---

### 8.4 Phase 4: Purview Integration (Weeks 13-16)

| Task | Owner | Status |
|------|-------|--------|
| Purview glossary export | R. Patel | TODO |
| Purview schema import | R. Patel | TODO |
| Bi-directional sync workflow | R. Patel | TODO |
| Lineage query interface | R. Patel | TODO |

**Deliverables**:
- FA glossary in Purview
- Schema discovery results in RAG
- End-to-end lineage queries

---

### 8.5 Phase 5: Vendor Assessment (Weeks 17-20)

| Task | Owner | Status |
|------|-------|--------|
| Vendor assessment template | R. Patel + team | TODO |
| Vendor comparison generator | R. Patel | TODO |
| Supplier assessment ingestion | R. Patel | TODO |
| Vendor assessment workflow | R. Patel | TODO |

**Deliverables**:
- Vendor Assessment Generator
- Supplier comparison reports
- Traceability to requirements

---

### 8.6 Success Metrics

| Metric | Baseline | Target |
|--------|----------|--------|
| SAD authoring time | 2-3 weeks | 3-5 days |
| Glossary term lookup | Manual search | <10 seconds |
| ERD creation | Manual (days) | Automated (minutes) |
| Reference data conformance | Unknown | 95%+ validated |
| Vendor assessment time | 1-2 weeks | 2-3 days |
| Data Working Group credibility | Subjective | Evidence-based |

---

## 9. Legal & Compliance Considerations

### 9.1 Data Protection & GDPR (DPO Perspective)

**Core Principle: All data stays local — nothing leaves The FA's infrastructure.**

| Aspect | Implementation | Compliance Status |
|--------|----------------|-------------------|
| **Data Residency** | All files stored on local filesystem (`~/Documents/__data/`) | ✅ FA-controlled storage |
| **Vector Embeddings** | ChromaDB running locally (no cloud SaaS) | ✅ No data egress |
| **LLM Processing** | Ollama running on local machine (localhost:11434) | ✅ No API calls to external providers |
| **Embedding Model** | `nomic-embed-text` runs locally via Ollama | ✅ No data sent to OpenAI, Anthropic, etc. |
| **Query Processing** | All queries processed locally | ✅ No external logging or telemetry |
| **Network Isolation** | No outbound connections required for core functionality | ✅ Air-gap capable |

**GDPR Considerations:**

| Requirement | How This System Complies |
|-------------|-------------------------|
| **Data Minimisation** | Only documents necessary for architecture work are ingested |
| **Purpose Limitation** | System used for architecture knowledge management, not general processing |
| **Storage Limitation** | Documents can be deleted via `--delete` command; hash tracking enables audit |
| **Integrity & Confidentiality** | Local-only processing reduces exposure to external threats |
| **Accountability** | Ingestion configs provide audit trail of what was processed and when |

**DPO Checklist:**

```markdown
- [ ] Confirm local-only deployment (no cloud LLM APIs)
- [ ] Document data sources and lawful basis for processing
- [ ] Ensure deletion capability (already exists via `--delete` flag)
- [ ] Add access controls if deploying beyond personal use
- [ ] Create data processing record for RAG system
- [ ] Review if personal data is ingested (e.g., SADs with names)
```

---

### 9.2 Copyright & Intellectual Property

**Knowledge Source Risk Assessment:**

| Source | Copyright Status | Risk Level | Mitigation |
|--------|------------------|------------|------------|
| **FA Handbook** | © The FA | None (internal use) | FA's own publication |
| **LeanIX Exports** | © The FA (data you own) | None | Your subscription, your data |
| **Workday Design Docs** | © The FA | None | Internal documents |
| **SAD Documents** | © The FA | None | Internal artefacts |
| **DAMA-DMBOK2 (2nd Ed.)** | © DAMA International | Medium | See below |
| **ISO Standards (3166, 4217)** | © ISO | Medium-High | See below |
| **ONS Codes** | © Crown Copyright (OGL) | None | Open Government License |

---

#### DAMA-DMBOK2 Considerations

**Current Status:**
- You have ingested the full DAMA-DMBOK2 PDF into the RAG system
- Embeddings are stored locally in ChromaDB
- LLM generates summaries/answers based on retrieved content
- No verbatim reproduction is intended

**Risk Factors:**

| Factor | Your Situation | Risk Impact |
|--------|----------------|-------------|
| **Personal/Local Use** | ✅ Currently the case | Lower risk |
| **Internal Team Use** | ⚠️ Potential future state | Medium risk |
| **Organisation-Wide Deployment** | ⚠️ Possible future state | Higher risk |
| **Commercial License** | ⚠️ Check if FA has DAMA corporate membership | Mitigates risk |
| **Verbatim Output** | ⚠️ Depends on LLM configuration | Configure to paraphrase |

**UK Copyright Law Context:**

| Exception | Applicability |
|-----------|---------------|
| **Fair Dealing (Research/Study)** | Narrow — primarily personal use |
| **Text & Data Mining (TDM)** | UK has TDM exceptions for non-commercial research; commercial use is less clear |
| **Quotation for Criticism/Review** | May apply if output includes short excerpts with attribution |
| **Incidental Use** | Embeddings may be considered transformative, but untested in UK courts |

**Recommended Actions:**

```markdown
- [ ] Check if The FA has DAMA International corporate membership
- [ ] If yes: confirm whether internal RAG use is covered
- [ ] If no: consider purchasing organizational license or reaching out to DAMA
- [ ] Configure LLM system prompts to avoid verbatim reproduction
- [ ] Add disclaimer to RAG output (see below)
- [ ] For production deployment: seek legal review
```

**Suggested Disclaimer (add to query output):**

```
This response is generated based on DAMA-DMBOK2 (2nd Edition) and other 
architecture documentation. It is a summary for internal reference only. 
Consult the original publication for authoritative guidance.
© DAMA International. All rights reserved.
```

**LLM Configuration (prevent verbatim output):**

```yaml
# rag_config.yaml

query:
  system_prompt: |
    You are a helpful assistant that answers questions based on the provided documents.
    
    IMPORTANT:
    - Summarise concepts in your own words — do not reproduce text verbatim
    - Keep quotations under 50 words and always cite the source
    - Prioritise explaining concepts over copying definitions
    - If asked for exact text, direct the user to the original document
    
    Always ground your answers in the retrieved content.
    Cite the source when relevant (e.g., "According to DAMA-DMBOK2, Chapter 3...").
```

---

#### ISO Standards Considerations

**ISO 3166 (Countries), ISO 4217 (Currencies):**

| Factor | Status |
|--------|--------|
| ISO standards are copyrighted | Yes |
| Country/currency codes are factual | Yes (but compilation is protected) |
| Risk of enforcement | Low (ISO rarely pursues internal use) |
| Mitigation | Use codes factually; don't reproduce full standard tables |

**Recommendation:**
- For reference data catalogues, use codes factually (e.g., "GB = United Kingdom")
- Don't reproduce full ISO standard text or tables verbatim
- Consider linking to official ISO sources instead of embedding full standards

---

### 9.3 Deployment Scenarios & Risk Levels

| Scenario | Deployment Scope | Risk Level | Actions Required |
|----------|------------------|------------|------------------|
| **Personal/Research** | Your machine only | Low | Document lawful basis; ensure local-only |
| **Team Pilot** | Data Working Group (5-10 people) | Medium | DPO review; add access controls |
| **Architecture Team** | FA Architecture (20-50 people) | Medium | Legal review; DAMA license check |
| **Organisation-Wide** | All FA staff (500+) | High | Full legal review; licensing; DPO sign-off |

---

### 9.4 Security Controls

**Current Security Posture:**

| Control | Status | Notes |
|---------|--------|-------|
| **Data Encryption at Rest** | ⚠️ Depends on filesystem | Consider encrypting `chroma_db/` directory |
| **Data Encryption in Transit** | ✅ N/A (local-only) | No network transmission |
| **Access Controls** | ⚠️ Filesystem permissions only | Add authentication for multi-user deployment |
| **Audit Logging** | ⚠️ Basic (ingestion timestamps) | Consider adding query logging |
| **Deletion Capability** | ✅ Implemented | `--delete` flag removes collections |
| **Backup** | ⚠️ User responsibility | Add to backup procedures if production |

**Recommended Enhancements (for production):**

```markdown
- [ ] Enable ChromaDB authentication (if deploying as service)
- [ ] Add query audit logging (who queried what, when)
- [ ] Encrypt ChromaDB persist directory
- [ ] Implement role-based access control (RBAC)
- [ ] Add rate limiting (prevent abuse)
- [ ] Create incident response procedure
```

---

### 9.5 Summary: Compliance Checklist

**Before Production Deployment:**

```markdown
## Data Protection (DPO)
- [ ] Confirm local-only deployment (no external LLM APIs)
- [ ] Document lawful basis for processing each data source
- [ ] Create data processing record
- [ ] Ensure deletion capability is working
- [ ] Review for personal data in ingested documents

## Copyright & IP
- [ ] Check FA's DAMA International membership status
- [ ] Contact DAMA International if deploying beyond personal use
- [ ] Configure LLM to avoid verbatim reproduction
- [ ] Add copyright disclaimers to output
- [ ] Seek legal review for organisation-wide deployment

## Security
- [ ] Encrypt ChromaDB data directory
- [ ] Add authentication (if multi-user)
- [ ] Enable audit logging
- [ ] Document backup/restore procedures
- [ ] Create incident response plan
```

---

**Bottom Line:**

| Use Case | Status |
|----------|--------|
| **Personal experimentation** | ✅ Fine — continue as-is |
| **Team pilot (Data Working Group)** | ⚠️ Get DPO review; document lawful basis |
| **Production deployment** | 🔴 Legal review + licensing required |

**Key Assurance:** The architecture is designed for **data sovereignty** — no FA assets leave your infrastructure, no external APIs are called, and all processing is local. This significantly reduces DPO/GDPR risk compared to cloud-based LLM solutions.

---

## Appendix A: Quick Start

### A.1 Ingest Documents

```bash
cd /Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag
uv sync

# Ingest LeanIX conceptual model
cd elt_llm_ingest
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_ea_leanix --force

# Ingest FA Handbook
uv run python -m elt_llm_ingest.runner --cfg fa_handbook --force

# Ingest DAMA-DMBOK
uv run python -m elt_llm_ingest.runner --cfg dama_dmbok --force
```

### A.2 Query Collections

```bash
cd ../elt_llm_query

# Interactive query (single collection)
uv run python -m elt_llm_query.runner --cfg leanix_only

# Interactive query (multi-collection)
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined

# Single query
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined -q "What is a Club?"
```

### A.3 Check Status

```bash
cd ../elt_llm_ingest

# Show all collections
uv run python -m elt_llm_ingest.runner --status

# Show detailed metadata
uv run python -m elt_llm_ingest.runner --status -v
```

---

## Appendix B: Configuration Reference

### B.1 Ingestion Config Example

```yaml
# config/ingest_fa_ea_leanix.yaml

# Split mode: one XML → 11 domain-scoped collections (fa_leanix_*)
collection_prefix: "fa_leanix"

preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "split"
  enabled: true

file_paths:
  - "~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml"

metadata:
  domain: "architecture"
  type: "enterprise_architecture"
  source: "LeanIX"

chunking:
  chunk_size: 512
  chunk_overlap: 64

rebuild: true
```

### B.2 Query Config Example

```yaml
# llm_rag_profile/architecture_focus.yaml

collections:
  - name: "fa_leanix_overview"
  - name: "fa_leanix_relationships"
  - name: "fa_ea_sad"

query:
  similarity_top_k: 10
  system_prompt: |
    You are a helpful assistant that answers questions based on architecture documentation.
    Always ground your answers in the retrieved content.
    Cite the source (SAD or LeanIX) when relevant.
```

---

## Appendix C: Glossary

| Term | Definition |
|------|------------|
| **Conceptual Model** | Business-aligned data model (LeanIX) showing entities and relationships |
| **FA Handbook** | The FA's official rules, regulations, and governance documentation |
| **DAMA-DMBOK** | Data Management Body of Knowledge (2nd Edition) |
| **LeanIX** | Enterprise architecture platform (source of truth for FA) |
| **Purview** | Microsoft data governance platform |
| **RAG** | Retrieval-Augmented Generation (LLM + vector search) |
| **SAD** | Solution Architecture Definition (FA architecture artefact) |
| **FDM** | Functional Data Model (business process-aligned data model) |
| **ERD** | Entity Relationship Diagram |
| **ISO 3166** | International standard for country codes |
| **ISO 4217** | International standard for currency codes |
| **ONS** | Office for National Statistics (UK geographic codes) |

---

## Appendix D: Contact

**Author**: Rakesh Patel  
**Repository**: `emailrak/elt_llm_rag`  
**Last Updated**: February 2026

---

**Status**: Living document — update as implementation progresses.
