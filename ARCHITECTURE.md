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
- [3. Conceptual Model Alignment](#3-conceptual-model-alignment)
- [4. What's Built](#4-whats-built)
- [5. What Needs to Be Built](#5-what-needs-to-be-built)
- [6. Business Catalogue Opportunities](#6-business-catalogue-opportunities)
- [7. Data Working Group Value](#7-data-working-group-value)
- [8. Implementation Roadmap](#8-implementation-roadmap)

---

## 1. Executive Summary

### 1.1 Purpose

This RAG platform transforms how FA architecture knowledge is:
- **Captured**: From SADs, LeanIX, FA Handbook, DAMA-DMBOK
- **Queried**: Natural language questions across multiple knowledge domains
- **Generated**: Automated SADs, ERDs, vendor assessments, glossaries

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
│  │  - Sentence transformers                                         │    │
│  │  - Smart change detection (SHA256 file hashing)                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                    ↓                                     │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Vector Store (ChromaDB)                                         │    │
│  │  - Tenant: rag_tenants                                           │    │
│  │  - Database: knowledge_base                                      │    │
│  │  - Collections: per source (fa_ea_leanix, dama_dmbok, etc.)      │    │
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
│  │  LLM Synthesis (Ollama: llama3.2, qwen2.5:14b)                   │    │
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
│   └── examples/           # Query configs
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
| **LLM** | Ollama: `llama3.2`, `qwen2.5:14b` | Context: 4096-32768 |
| **Vector Store** | ChromaDB | Tenant/DB/Collection |
| **Chunking** | LlamaIndex | Sentence transformers |
| **Hybrid Search** | BM25 + Vector | QueryFusionRetriever |
| **Preprocessing** | Custom Python | LeanIX XML→Markdown |
| **Dependency Mgmt** | uv | Python 3.11-3.13 |

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
| **Data Architecture** | `fa_ea_leanix` + `fa_ea_sad` | Model queries |
| **Data Quality** | `dama_dmbok` + supplier assessments | DQ rule generation |
| **Reference Data** | `iso_reference_data` (TODO) | Standards conformance |
| **Metadata Management** | All collections + Purview | Catalogue integration |

---

## 4. What's Built

### 4.1 Core Infrastructure ✅

| Component | Status | Description |
|-----------|--------|-------------|
| **ChromaDB Integration** | ✅ Complete | Tenant/database/collection support |
| **Ollama Models** | ✅ Complete | Embedding + LLM configuration |
| **Query Engine** | ✅ Complete | Hybrid search (BM25 + vector) |
| **Configuration** | ✅ Complete | YAML-based configs |
| **Smart Ingest** | ✅ Complete | SHA256 file change detection |

### 4.2 Ingestion Pipelines ✅

| Collection | Documents | Chunks | Status |
|------------|-----------|--------|--------|
| `dama_dmbok` | DAMA-DMBOK2 (PDF) | ~11,943 | ✅ Ingested |
| `fa_handbook` | FA Handbook (PDF) | ~9,673 | ✅ Ingested |
| `fa_ea_leanix` | LeanIX XML (draw.io) | ~2,261 | ✅ Ingested |
| `fa_ea_sad` | SAD (PDF) | TBD | ⏳ Config ready |
| `supplier_assess` | Supplier docs | TBD | ⏳ Config ready |

### 4.3 Preprocessors ✅

| Preprocessor | Input | Output | Status |
|--------------|-------|--------|--------|
| **LeanIXPreprocessor** | draw.io XML | Markdown + JSON | ✅ Complete |
| **IdentityPreprocessor** | Any | Pass-through | ✅ Complete |
| **FAGlossaryPreprocessor** | FA Handbook PDF/HTML | Structured glossary | ⏳ TODO |
| **ReferenceDataPreprocessor** | CSV (ISO/ONS) | Catalogue entries | ⏳ TODO |

### 4.4 Query Configs ✅

| Config | Collections | Use Case |
|--------|-------------|----------|
| `dama_only.yaml` | DAMA-DMBOK | Data management queries |
| `fa_handbook_only.yaml` | FA Handbook | Policy/glossary queries |
| `leanix_only.yaml` | LeanIX | Architecture queries |
| `architecture_focus.yaml` | SAD + LeanIX | Architecture decisions |
| `vendor_assessment.yaml` | LeanIX + Supplier | Vendor evaluation |
| `dama_fa_combined.yaml` | DAMA + FA Handbook | Cross-domain queries |
| `leanix_fa_combined.yaml` | LeanIX + FA Handbook | Business-aligned architecture |

### 4.5 LeanIX Parser Capabilities ✅

The `doc_leanix_parser.py` extracts:

- **Assets**: Fact sheets with type, label, parent group, coordinates
- **Relationships**: Cardinality (ER notation), source→target
- **Domain Groupings**: PARTY, AGREEMENT, PRODUCT, TRANSACTION, etc.
- **Output Formats**: 
  - **Markdown**: RAG-optimized natural language (UUIDs omitted)
  - **JSON**: Full fidelity for LeanIX roundtrip

**Example Markdown Output**:
```markdown
# FA Enterprise Conceptual Data Model

The FA Enterprise Conceptual Data Model contains 156 entities organised into 9 domain groups: 
AGREEMENT, ASSET, CHANNEL, EVENT, LOCATION, PARTY, PRODUCT, REFERENCE DATA, TRANSACTION.

## PARTY Domain

The PARTY domain contains 24 entities in the FA Enterprise Conceptual Data Model. 
The entities within this domain are: Club, County FA, Individual, Organisation, Team, ...

## Entity Relationships

PARTY relates to (zero or more to zero or more) AGREEMENT (including Contract, Policy, Rule...).
PRODUCT relates to (one or more to zero or more) TRANSACTION (including Match, Application, Payment...).
```

---

## 5. What Needs to Be Built

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
            ['fa_ea_leanix', 'fa_handbook', 'dama_dmbok'],
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
        entities = query_collection("fa_ea_leanix", "all entities")
        
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
                ['fa_ea_leanix', 'supplier_assess'],
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
| **Data Objects** | LeanIX conceptual | `fa_ea_leanix` | ✅ Partial |
| **Systems/Applications** | LeanIX | `fa_ea_leanix` | ✅ Partial |
| **Data Flows** | LeanIX relationships | `fa_ea_leanix` | ✅ Partial |
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
| **Reference Data Governance** | Conformance checking against ISO/ONS |
| **Project Architecture Review** | Auto-generate SAD sections for consistency |
| **Vendor Evaluation** | Generate assessment reports with traceability |
| **Data Quality Investigations** | Trace non-conformance to source systems |

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

| Task | Owner | Status |
|------|-------|--------|
| FAGlossaryPreprocessor | R. Patel | TODO |
| ISO Reference Data ingestion | R. Patel | TODO |
| FA Handbook HTML scraper | R. Patel | TODO |
| Multi-collection query optimisation | R. Patel | ✅ Complete |

**Deliverables**:
- Glossary extraction from FA Handbook
- Reference data catalogue (ISO 3166, ISO 4217, ONS)
- Query interface for glossary + reference data

---

### 8.2 Phase 2: SAD Generator (Weeks 5-8)

| Task | Owner | Status |
|------|-------|--------|
| SAD template definition | R. Patel + team | TODO |
| SAD section generator (PoC) | R. Patel | TODO |
| Workday design doc ingestion | R. Patel | TODO |
| SAD generation workflow | R. Patel | TODO |

**Deliverables**:
- SAD Generator PoC (1-2 sections)
- Workday design doc ingestion pipeline
- SAD template aligned with FA standards

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

## Appendix A: Quick Start

### A.1 Ingest Documents

```bash
cd /Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag
uv sync

# Ingest LeanIX conceptual model
cd elt_llm_ingest
uv run python -m elt_llm_ingest.runner --cfg fa_ea_leanix --force

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

collection_name: "fa_ea_leanix"

preprocessor:
  module: "elt_llm_ingest.preprocessor"
  class: "LeanIXPreprocessor"
  output_format: "markdown"
  output_suffix: "_leanix_processed"
  enabled: true

file_paths:
  - "~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml"

metadata:
  domain: "architecture"
  type: "enterprise_architecture"
  source: "LeanIX"

rebuild: true
```

### B.2 Query Config Example

```yaml
# examples/architecture_focus.yaml

collections:
  - name: "fa_ea_leanix"
    weight: 1.0
  - name: "fa_ea_sad"
    weight: 1.0

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
