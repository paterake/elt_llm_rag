# FA Enterprise Data Glossary — Solution Overview

**Generated**: March 2026
**Platform**: ELT LLM RAG (`elt_llm_rag`)
**Target Audience**: Data Architects, Data Modellers, Governance Stakeholders

---

## Executive Summary

**Challenge**: Generate a comprehensive business glossary from the FA Handbook, reverse-engineered and mapped to the LeanIX conceptual data model as the frame.

**Solution**: A RAG+LLM platform that:
1. Extracts ~149 defined terms from the FA Handbook
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

## 0. AI Architecture Overview

This solution combines **AI components** (RAG, LLM, prompts) with **custom code** (ingestion, consumers) to deliver an automated glossary extraction and mapping system.

### 0.1 What is RAG? (Retrieval-Augmented Generation)

**Definition**: RAG is an AI architecture that combines:
- **Retrieval**: Fetching relevant documents/chunks from a knowledge base
- **Generation**: Using an LLM to synthesize answers based on retrieved context

**Why RAG?**
- LLMs have knowledge cutoffs and can't access your private documents
- RAG grounds the LLM in YOUR data (FA Handbook, LeanIX models)
- Reduces hallucinations — LLM only answers based on retrieved evidence
- Enables citation of sources (section numbers, rule numbers)

**Our RAG Implementation:**

```
┌──────────────────────────────────────────────────────────────┐
│ RAG PIPELINE FOR FA HANDBOOK                                 │
│                                                              │
│ 1. INGESTION                                                 │
│    FA Handbook PDF → pymupdf4llm → Markdown                  │
│    Markdown → TableAwareSentenceSplitter → 3,562 chunks     │
│    Chunks → nomic-embed-text → 768-dim vectors              │
│    Vectors + chunks → ChromaDB (vector store + docstore)    │
│                                                              │
│ 2. RETRIEVAL (at query time)                                 │
│    User query → Hybrid search (BM25 + Vector)               │
│    → Top-24 candidates from 3,562 chunks                    │
│    → Embedding reranker (cosine similarity)                 │
│    → Top-10 most relevant chunks                            │
│                                                              │
│ 3. GENERATION                                                │
│    Query + 10 chunks → qwen3.5:9b LLM                       │
│    → Structured response (definition, context, governance)  │
│    → JSON output with citations                             │
└──────────────────────────────────────────────────────────────┘
```

**RAG Configuration** (`elt_llm_ingest/config/rag_config.yaml`):

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `chunking.strategy` | `table_aware` | Preserves table rows as single chunks |
| `chunking.chunk_size` | 256 | Prose chunk size (tokens) |
| `chunking.table_chunk_size` | 1536 | Table row max size (tokens) |
| `query.similarity_top_k` | 8 | Chunks passed to LLM |
| `query.reranker_top_k` | 10 | Chunks after reranking |
| `query.num_queries` | 3 | Query variants for diversity |
| `query.use_hybrid_search` | `true` | BM25 + Vector combined |
| `query.use_mmr` | `true` | Maximal Marginal Relevance (diversity) |

**Key Features:**
- **Hybrid search**: BM25 (keyword) + Vector (semantic) — captures both exact matches and conceptual similarity
- **Reranking**: Initial retrieval optimizes for speed, reranking optimizes for relevance
- **MMR (Maximal Marginal Relevance)**: Prevents near-duplicate chunks from dominating results
- **Table-aware chunking**: FA Handbook definitions table (Rules §8) kept intact — no split definitions

---

### 0.2 What is the LLM? (Large Language Model)

**Our LLM**: `qwen3.5:9b` via Ollama

| Specification | Value |
|---------------|-------|
| **Model** | Qwen 3.5 (Alibaba) |
| **Parameters** | 9 billion |
| **Context window** | 16,384 tokens |
| **Embedding model** | `nomic-embed-text` (768 dimensions) |
| **Runtime** | Ollama (local, CPU/M3) |

**Why This Model?**
- **Local execution**: No API calls, data stays on-premises
- **9B parameters**: Good balance of quality vs. resource usage (~6.6GB VRAM)
- **16K context**: Can process 10+ retrieved chunks simultaneously
- **Strong reasoning**: Good at extraction, synthesis, and classification tasks

**LLM Tasks in This Solution:**

| Task | Prompt | Output |
|------|--------|--------|
| **Handbook context extraction** | `handbook_context.yaml` | Definition + context + governance |
| **Governance extraction** | `governance_extraction.yaml` | Governance rules only |
| **Domain inference** | `domain_inference.yaml` | Domain/subgroup classification |
| **Relationship extraction** | `entity_relationship.yaml` | Entity-to-entity relationships |

**What the LLM Does NOT Do:**
- ❌ Parse LeanIX XML/Excel (done by custom code)
- ❌ Match handbook terms to entities (done by string matching)
- ❌ Consolidate results (done by Python logic)
- ❌ Store/retrieve vectors (done by ChromaDB)

---

### 0.3 Prompt Engineering

**What is Prompt Engineering?**
Designing input prompts to guide the LLM toward desired outputs. Well-engineered prompts:
- Specify the task clearly
- Provide context and constraints
- Define output format (JSON, sections, etc.)
- Include examples or decision rules

**Our Prompts** (in `elt_llm_consumer/config/prompts/`):

#### 1. `handbook_context.yaml` — Primary Entity Query

**Purpose**: Extract complete terms-of-reference for a conceptual model entity.

**Variables**: `{entity_name}`, `{domain}`

**Output Structure**:
```
FORMAL_DEFINITION: [exact quote or paraphrase]
DOMAIN_CONTEXT: [role in domain, related concepts]
GOVERNANCE: [rules with section/rule citations]
```

**Key Prompt Techniques**:
- **Subtype awareness**: "The FA Handbook may refer to this entity... as 'Contract {entity_name}', 'Registered {entity_name}'..."
- **Citation requirement**: "Cite section and rule numbers where possible"
- **Fallback handling**: "If no handbook rules apply, state 'Not documented in FA Handbook...'"

---

#### 2. `governance_extraction.yaml` — Dedicated Governance Query

**Purpose**: Fallback governance query when primary prompt returns empty/hedged results.

**Variables**: `{entity_name}`

**When Used**:
- Always for `_GOVERNANCE_INTENSIVE_ENTITIES` (Club, Player, Match Official, etc.)
- For other entities when initial governance is empty or starts with "Not documented..."

**Key Prompt Techniques**:
- **Structured coverage**: Lists specific governance types (registration, eligibility, compliance, etc.)
- **Prose output**: Returns governance rules as continuous text (not structured sections)

---

#### 3. `domain_inference.yaml` — HANDBOOK_ONLY Classification

**Purpose**: Classify handbook terms that don't match any conceptual model entity.

**Variables**: `{taxonomy_context}`, `{entity_name}`, `{handbook_definition}`

**Output**: JSON with domain, subgroup, confidence, reasoning

**Decision Logic** (Three-Tier):
```
TIER 1 — Map to existing taxonomy (preferred)
  → inference_tier: "existing"

TIER 2 — Propose new taxonomy
  → inference_tier: "new_proposed"

TIER 3 — Unknown (last resort)
  → inference_tier: "unknown"
```

**Key Prompt Techniques**:
- **Decision process**: Explicit priority order (Tier 1 > Tier 2 > Tier 3)
- **Confidence scoring**: "high | medium | low" based on semantic clarity
- **Alternative consideration**: "alternative_domain" field for ambiguous cases

---

#### 4. `entity_relationship.yaml` — Relationship Extraction

**Purpose**: Extract entity-to-entity relationships from FA Handbook for a domain pair.

**Variables**: `{source_domain}`, `{source_entities}`, `{target_domain}`, `{target_entities}`, `{domain_cardinality}`

**Output**: JSON array of relationship records (forward + inverse pairs)

**Key Prompt Techniques**:
- **Bidirectional requirement**: "return BOTH the forward and inverse directions"
- **Evidence requirement**: "brief quote or paraphrase from the Handbook (max 30 words)"
- **Inference flag**: `inferred: true/false` distinguishes explicit vs. inferred relationships

---

#### 5. `handbook_model_builder.yaml` — (Future Use)

**Purpose**: Build handbook-only entity model (not currently used in main flow).

---

### 0.4 Custom Code (Non-AI Components)

**What Requires Custom Code?**

RAG+LLM handles **unstructured data** (FA Handbook PDF), but **structured data** (LeanIX XML/Excel) requires custom parsing and deterministic logic.

#### Ingestion Layer (`elt_llm_ingest`)

| Component | Purpose | AI or Custom? |
|-----------|---------|---------------|
| `preprocessor.py` | LeanIX XML → Markdown, Excel → Markdown | **Custom** (XML parsing, Excel reading) |
| `preprocessor.py` | PDF → Markdown (pymupdf4llm) | **Library** (third-party) |
| `chunking.py` | Table-aware sentence splitter | **Custom** (table detection logic) |
| `ingest.py` | Orchestrate ingestion pipeline | **Custom** (LlamaIndex integration) |
| `file_hash.py` | Track file changes for incremental ingestion | **Custom** (hash computation) |

**Key Custom Logic:**

1. **Table-Aware Chunking** (`chunking.py`):
   ```python
   # Detects table content via pipe-delimiter patterns
   if "|" in line:  # Table row detected
       keep_as_single_chunk()  # Up to 1536 tokens
   else:
       standard_sentence_split()  # 256 tokens
   ```

2. **LeanIX Preprocessor** (`preprocessor.py`):
   ```python
   # Parses draw.io XML, extracts entities/relationships
   # Produces: _model.json, _entities.md, _relationships.md
   # Splits by domain for targeted RAG queries
   ```

---

#### Consumer Layer (`elt_llm_consumer`)

| Component | Purpose | AI or Custom? |
|-----------|---------|---------------|
| `fa_consolidated_catalog.py` | Main consolidation logic | **Custom** (orchestration) |
| Step 1: Load entities | Read `_model.json` | **Custom** (JSON parsing) |
| Step 2: Inventory lookup | O(1) dict lookup by fact_sheet_id | **Custom** (deterministic) |
| Step 3: Extract handbook terms | Docstore scan with regex | **Custom** (pattern matching) |
| Step 4: Match terms to entities | Normalized name + alias matching | **Custom** (string matching) |
| Step 5: Handbook context | RAG+LLM per entity | **AI** (uses prompts) |
| Step 6: Load relationships | Read `_model.json` | **Custom** (JSON parsing) |
| Step 7: Consolidate | Merge and classify | **Custom** (business logic) |

**Key Custom Logic:**

1. **Entity Alias Map** (`fa_consolidated_catalog.py`):
   ```python
   _ENTITY_ALIASES = {
       "fa county": ["county association", "county football association"],
       "competition league": ["competition", "league"],
       "match official": ["referee", "assistant referee"],
       # ... 25+ alias mappings
   }
   ```

2. **No-Coverage Exclusions**:
   ```python
   _NO_HANDBOOK_COVERAGE = frozenset([
       "Supplier", "Household", "Business Unit", "Prospect",
       "Customer", "Event Attendee", "Casual & Contingent Labourers",
       "Managed Service Workers",
   ])
   # Skips RAG calls for these — saves 8 LLM calls
   ```

3. **Governance-Intensive Entities**:
   ```python
   _GOVERNANCE_INTENSIVE_ENTITIES = frozenset([
       "Club", "Player", "Match Official", "Club Official",
       "County Association", "Competition", "Competition League", "FA County",
   ])
   # Always runs dedicated governance query for these
   ```

---

### 0.5 Configuration (YAML-Based Control)

**What's Configured vs. Coded?**

| Aspect | Configuration File | Custom Code |
|--------|-------------------|-------------|
| **RAG parameters** | `rag_config.yaml` | Reads config |
| **Chunking strategy** | `rag_config.yaml` | Implements strategy |
| **LLM model** | `rag_config.yaml` | Calls Ollama API |
| **Prompts** | `config/prompts/*.yaml` | Loads and formats |
| **Ingestion sources** | `config/ingest_*.yaml` | Executes pipeline |
| **Entity aliases** | — | Hardcoded in code |
| **Exclusion lists** | — | Hardcoded in code |

**Configuration Files:**

| File | Purpose |
|------|---------|
| `elt_llm_ingest/config/rag_config.yaml` | Global RAG/LLM settings |
| `elt_llm_ingest/config/ingest_fa_handbook.yaml` | FA Handbook ingestion |
| `elt_llm_ingest/config/ingest_fa_leanix_*.yaml` | LeanIX ingestion |
| `elt_llm_consumer/config/prompts/*.yaml` | LLM prompts |

---

### 0.6 AI vs. Custom Code Summary

| Component | AI (RAG+LLM) | Custom Code | Why |
|-----------|--------------|-------------|-----|
| **FA Handbook parsing** | ❌ | ✅ | PDF → Markdown requires library |
| **FA Handbook chunking** | ❌ | ✅ | Table detection is rule-based |
| **FA Handbook embedding** | ✅ | ❌ | nomic-embed-text model |
| **FA Handbook retrieval** | ✅ | ❌ | Hybrid search (BM25 + Vector) |
| **FA Handbook synthesis** | ✅ | ❌ | qwen3.5:9b LLM |
| **LeanIX XML parsing** | ❌ | ✅ | Structured data → custom parser |
| **LeanIX Excel parsing** | ❌ | ✅ | Structured data → openpyxl |
| **Term matching** | ❌ | ✅ | String matching + alias map |
| **Domain inference** | ✅ | ❌ | LLM classification |
| **Consolidation logic** | ❌ | ✅ | Business rules + merging |
| **Output formatting** | ❌ | ✅ | JSON structure |

**Design Principle**: 
- **AI for unstructured**: RAG+LLM for FA Handbook (PDF text)
- **Custom for structured**: Direct parsing for LeanIX (XML/Excel)
- **Hybrid where needed**: LLM inference for domain classification, custom logic for consolidation

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
│                → _model.json (JSON sidecar next to source)      │
│    - LeanIX Excel → fa_leanix_global_inventory_*                │
│                   → _inventory.json (JSON sidecar next to source)│
│    Technology: LlamaIndex + ChromaDB (vectorstore + docstore)   │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. RAG STRATEGY (elt_llm_query)                                 │
│    - Hybrid retrieval: BM25 + Vector                            │
│    - Embedding reranker: nomic-embed-text                       │
│    - LLM synthesis: qwen3.5:9b                                 │
│    (Used only for FA Handbook queries — see Consumer below)     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. CONSUMER (elt_llm_consumer)                                  │
│    fa_consolidated_catalog.py — TARGET OUTPUT                   │
│                                                                   │
│    LeanIX Data (direct JSON lookup — no RAG, no LLM):           │
│    - Entities from _model.json                                  │
│    - Inventory descriptions via fact_sheet_id lookup            │
│    - Relationships from _model.json                             │
│                                                                   │
│    Handbook Data (RAG+LLM required — unstructured PDF):         │
│    - Defined terms from docstore scan                           │
│    - Handbook context per entity (formal definition, rules)     │
│                                                                   │
│    Output: fa_consolidated_catalog.json                          │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Decision**: LeanIX data uses **direct JSON sidecars** (not RAG) because:
- Data is already structured during ingestion
- Deterministic joins via `fact_sheet_id`
- Fast: O(1) lookup vs. ~15s per RAG query

RAG+LLM is used **only for the FA Handbook** (unstructured PDF text).

### 2.2 Technology Stack

| Component | Technology | Configuration |
|-----------|------------|---------------|
| **Vector Store** | ChromaDB | Persistent, tenant/database isolation |
| **DocStore** | LlamaIndex | Metadata index for structured extraction |
| **Embeddings** | Ollama | `nomic-embed-text` (768 dimensions) |
| **LLM** | Ollama | `qwen3.5:9b` (8K context) |
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
      → LLM Synthesis (qwen3.5:9b) → Structured JSON output
```

---

## 3. What Was Built

### 3.1 Ingestion Layer (`elt_llm_ingest`)

**Collections Created:**

| Collection | Source | Content | Vectors |
|------------|--------|---------|---------|
| `fa_handbook` | FA Handbook PDF | Governance rules, definitions, obligations | 3,375 |
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

| Step | Source | Method | Output |
|------|--------|--------|--------|
| 1. Load entities | `_model.json` (LeanIX XML sidecar) | Direct JSON read | 175 entities with domain, subtype, fact_sheet_id |
| 2. Inventory descriptions | `_inventory.json` (LeanIX Excel sidecar) | O(1) dict lookup by fact_sheet_id | Descriptions for each entity |
| 3. Extract Handbook terms | `fa_handbook` docstore | Docstore scan (definition markers) | ~149 defined terms |
| 4. Map terms to entities | Handbook terms + model entities | Normalised name matching | BOTH/LEANIX_ONLY/HANDBOOK_ONLY classification |
| 5. Handbook context | `fa_handbook` collection | RAG+LLM per entity | Formal definition, domain context, governance rules |
| 6. Relationships | `_model.json` | Direct JSON read | Domain-level relationships |
| 7. Consolidate | All above | Merge and classify | `fa_consolidated_catalog.json` |

**Key Design Decision**: Steps 1–2 and 6 use **direct JSON lookup** (no RAG, no LLM) because:
- LeanIX data is already structured in JSON sidecars written during ingestion
- Deterministic: exact matches, no retrieval ambiguity
- Fast: O(1) dictionary lookup vs. ~15s per RAG query

Only Step 5 (Handbook context) uses RAG+LLM because the Handbook is unstructured PDF text.

**Commands:**
```bash
# Full consolidation (with relationships)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog

# Faster run (skip relationships)
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --skip-relationships
```

**Runtime**: ~5-10 minutes (Handbook RAG is the bottleneck)

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
| **1. Conceptual model as frame** | Direct JSON read from `_model.json` | `entity_name`, `domain`, `fact_sheet_id` |
| **2. FA Handbook SME context** | RAG+LLM extraction per entity | `formal_definition`, `domain_context`, `governance_rules` |
| **3. LeanIX Inventory descriptions** | Direct `fact_sheet_id` lookup in `_inventory.json` | `leanix_description` |
| **4. Glossary terms mapped** | Handbook → Model name matching | `handbook_term`, `mapping_confidence`, `mapping_rationale` |
| **5. Export format** | Structured JSON | Complete JSON file |
| **6. Gap analysis** | Source classification | `source: HANDBOOK_ONLY` |
| **7. Governance rules** | Handbook ToR extraction | `governance_rules` |

**Note**: Requirements 1 and 3 use **direct JSON lookup** (no RAG, no LLM) for speed and accuracy.

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
uv run --package elt-llm-consumer elt-llm-consumer-consolidated-catalog --model qwen3.5:9b
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
