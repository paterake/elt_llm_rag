# ELT LLM Consumer Architecture

**Purpose**: Technical architecture documentation for `elt_llm_consumer`

**Last Updated**: March 2026

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ INGESTION (elt_llm_ingest) — UNCHANGED                          │
│ - PDF → Markdown + ChromaDB vector/docstore                     │
│ - XML → JSON sidecar (_model.json) + Markdown                   │
│ - Excel → JSON sidecar (_inventory.json) + Markdown             │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (outputs consumed by consumer)
┌─────────────────────────────────────────────────────────────────┐
│ CONSUMER (elt_llm_consumer) — BATCH PROCESSING                  │
│ - Reads JSON sidecars (direct lookup)                           │
│ - Queries vector stores (via elt_llm_query)                     │
│ - Systematic processing (all entities)                          │
│ - Structured output (8-field schema)                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓ (writes to)
┌─────────────────────────────────────────────────────────────────┐
│ OUTPUT: fa_consolidated_catalog.json                            │
│ - Structured JSON (review-ready)                                │
│ - 8-field schema per entity                                     │
│ - Source attribution (BOTH/LEANIX_ONLY/HANDBOOK_ONLY)           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Module Structure

```
elt_llm_consumer/
├── README.md                        # Quick commands (start here)
├── ARCHITECTURE.md                  # This document
├── pyproject.toml                   # Package configuration
├── config/
│   ├── fa_consolidated_catalog.yaml # Entity aliases, static context
│   └── prompts/
│       └── handbook_context.yaml    # Structured prompt template
└── src/elt_llm_consumer/
    ├── fa_consolidated_catalog.py   # Primary: batch catalog generation
    ├── fa_handbook_model_builder.py # Extract entities from Handbook
    ├── fa_coverage_validator.py     # Validate coverage (no LLM)
    └── rag_retriever/               # Diagnostic tool
        ├── __init__.py
        ├── retriever.py
        └── ranking/
            ├── embedding.py
            ├── bm25.py
            └── boosted.py
```

---

## 7-Step Pipeline

### Step 1: Load Conceptual Model Entities
```python
all_entities = load_entities_from_json(model_json)
# Output: ~175 entities with entity_name, domain, subtype, fact_sheet_id
```

---

### Step 2: Load Inventory Descriptions
```python
inventory_lookup = load_inventory_from_json(inventory_json)
# O(1) dict lookup by fact_sheet_id
# Output: dict: normalised entity_name → {description, level, status, type}
```

---

### Step 3: Extract Handbook Defined Terms
```python
handbook_terms = extract_handbook_terms_from_docstore(rag_config)
# Regex scan: "X means Y" or "X is defined as Y"
# Output: ~149 dicts: {term, definition}
```

---

### Step 4: Match Handbook Terms to Model Entities
```python
# String matching + alias map
handbook_mappings[term.lower()] = {
    "mapped_entity": matched_entity["entity_name"],
    "domain": matched_entity["domain"],
    "mapping_confidence": "high" | "medium" | "low",
}
# Match rate: 2-5% (model uses short names, handbook uses qualified names)
```

---

### Step 5: Extract Handbook Context (RAG+LLM)
```python
for entity in conceptual_entities:
    # Stage 1a: BM25 section routing (entity + aliases)
    relevant_sections = discover_relevant_sections(...)
    
    # Stage 1c: Keyword scan (verbatim mentions)
    keyword_sections, keyword_chunks = find_sections_by_keyword(...)
    
    # Merge sections
    unified_collections = [*DEFINITION_SECTIONS, *relevant_sections]
    
    # RAG query with structured prompt
    context = get_handbook_context_for_entity(
        name, domain,
        all_collections=unified_collections,
        rag_config=rag_config,
        term_definitions=term_definitions,
        leanix_description=inv_desc,
        keyword_chunks=keyword_chunks,
    )
    
    # Output: dict: entity_name → {formal_definition, domain_context, governance_rules, ...}
```

**Runtime**: ~60-90s per entity (dominated by LLM synthesis)

---

### Step 6: Load Relationships
```python
relationships = load_relationships_from_json(model_json)
# Direct JSON read (no RAG)
# Output: dict: entity → entity relationships
```

---

### Step 7: Consolidate
```python
consolidated_entities, consolidated_relationships = consolidate_catalog(
    conceptual_entities,
    handbook_terms,
    handbook_mappings,
    inventory_descriptions,
    handbook_context,
    relationships,
)

# Classify each entity as:
# - BOTH: entity in model AND handbook
# - LEANIX_ONLY: in model only
# - HANDBOOK_ONLY: handbook term with no matching model entity

# Write output
with open(output_dir / "fa_consolidated_catalog.json", "w") as f:
    json.dump(hierarchical_output, f, indent=2)
```

---

## Output Schema

### Per Entity
```json
{
  "fact_sheet_id": "12345",
  "entity_name": "Club",
  "domain": "PARTY",
  "subgroup": "Organisation",
  "source": "BOTH",
  "leanix_description": "A football club affiliated with the FA",
  "formal_definition": "Club means any club which plays the game of football...",
  "domain_context": "Central entity in PARTY domain, relates to Player, Competition...",
  "governance_rules": "Section A, Rule 12: Clubs must be members of the FA...",
  "business_rules": "",
  "lifecycle_states": "",
  "data_classification": "",
  "regulatory_context": "",
  "associated_agreements": "",
  "handbook_term": "Club",
  "mapping_confidence": "high",
  "mapping_rationale": "Direct name match",
  "review_status": "PENDING",
  "review_notes": "",
  "relationships": []
}
```

---

## Source Classification

| Source | Description | Action |
|--------|-------------|--------|
| **BOTH** | Entity exists in LeanIX and Handbook | Review definition alignment |
| **LEANIX_ONLY** | Entity in LeanIX but not Handbook | May need Handbook update or model review |
| **HANDBOOK_ONLY** | Entity in Handbook but not LeanIX | Candidate for conceptual model addition |

---

## Review Status Tracking

| Status | Description |
|--------|-------------|
| `PENDING` | Awaiting stakeholder review (default) |
| `APPROVED` | Reviewed and approved for Purview import |
| `REJECTED` | Reviewed and rejected (with reason in `review_notes`) |
| `NEEDS_CLARIFICATION` | Requires SME input before approval |

---

## Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **LLM** | Ollama (qwen3.5:9b) | Governance context synthesis |
| **Embeddings** | Ollama (nomic-embed-text) | Vector retrieval |
| **Vector Store** | ChromaDB | Semantic search |
| **Docstore** | LlamaIndex JSON | BM25 retrieval |
| **Prompt** | handbook_context.yaml | Structured 8-field extraction |

---

## Performance Characteristics

| Domain | Entities | Runtime | LLM Calls |
|--------|----------|---------|-----------|
| PARTY | 28 | ~45-60 min | 28-56 |
| All domains | 175 | ~3-4 hours | 175-350 |

**Breakdown per entity**:
- Steps 1-4: ~2 min (JSON loading, string matching)
- Step 5: ~45-55 min (RAG+LLM per entity, ~60-90s each)
- Steps 6-7: ~3 min (relationship loading, consolidation)

---

## Design Principles

1. **Structured data → direct JSON** — LeanIX XML/Excel read directly (fast, deterministic)
2. **Unstructured data → RAG+LLM** — FA Handbook requires semantic search
3. **Systematic processing** — All entities processed identically
4. **8-field schema** — Enforced output structure for review
5. **Checkpointing** — Resume from interruption

---

## Comparison with Agent

| Aspect | Consumer | Agent |
|--------|----------|-------|
| **Purpose** | Structured batch output | Interactive Q&A + fast batch |
| **Control flow** | Pre-defined pipeline (7 steps) | Dynamic reasoning (ReAct loop) |
| **Section selection** | All 44 sections | BM25 selects 3-10 relevant |
| **Runtime** | ~60-90s/entity | ~10-30s/entity |
| **Output schema** | Strict 8-field | 8-field (extracted) |
| **Best for** | Stakeholder review, Purview import | Quick scans, debugging |

See [elt_llm_agentic/README.md](../elt_llm_agentic/README.md) for detailed comparison.

---

## References

- [README.md](README.md) — Quick commands
- [RAG_PIPELINE_DEEP_DIVE.md](../RAG_PIPELINE_DEEP_DIVE.md) — Retrieval stage details
- [elt_llm_agentic/README.md](../elt_llm_agentic/README.md) — Agentic vs consumer comparison
