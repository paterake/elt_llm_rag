# Solution Overview: How RAG + LLM Works

**Audience**: Stakeholders, data architects, new team members  
**Purpose**: Understand how the RAG+LLM system works — from ingestion to query  
**Last Updated**: March 2026

---

## Executive Summary

This document explains **how RAG (Retrieval-Augmented Generation) works** in the FA Data Governance platform.

**The challenge**: The FA Handbook (PDF) contains governance rules and definitions. The LeanIX conceptual model (XML) contains entity structures. We need to combine both to produce a consolidated catalog.

**The solution**: Use RAG to retrieve relevant handbook content, then use an LLM to synthesize it into structured output.

**Key insight**: RAG grounds the LLM in YOUR data — it can only answer based on retrieved evidence, reducing hallucinations.

> **Key Design Decision: Not Everything Uses RAG**
>
> **Structured data** (LeanIX XML, Excel) is read **directly from JSON files** — no RAG needed. This is fast (O(1) lookup), deterministic (exact matches), and accurate (canonical IDs preserved).
>
> **Only the FA Handbook** (unstructured PDF) uses RAG+LLM, because it requires semantic search to find relevant governance rules and definitions.
>
> See Part 4 for the detailed rationale and when-to-use guide.

---

## Part 1: What is RAG?

### The Problem RAG Solves

**LLMs have limitations**:
- ❌ Knowledge cutoff (don't know your private documents)
- ❌ Can’t access the FA Handbook or LeanIX models
- ❌ Prone to hallucinations (make things up confidently)

**RAG fixes this**:
- ✅ Retrieves relevant chunks from YOUR documents
- ✅ Passes them to the LLM as context
- ✅ LLM answers based on retrieved evidence only
- ✅ Enables citation of sources (section numbers, rule numbers)

### RAG in One Sentence

> **RAG fetches relevant document chunks, then the LLM synthesizes an answer based on those chunks.**

---

## Part 2: Ingestion Phase — Preparing Documents for RAG

### Overview

```
┌──────────────────────────────────────────────────────────────┐
│ SOURCE DATASETS                                              │
│                                                              │
│ ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│ │ FA Handbook PDF │  │ LeanIX XML   │  │ LeanIX Excel    │  │
│ │ (Governance)    │  │ (Model)      │  │ (Inventory)     │  │
│ └────────┬────────┘  └──────┬───────┘  └────────┬────────┘  │
└──────────┼──────────────────┼───────────────────┼───────────┘
           │                  │                   │
           ▼                  ▼                   ▼
┌──────────────────────────────────────────────────────────────┐
│ PREPROCESSING                                                │
│                                                              │
│ ┌─────────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│ │ Docling         │  │ Custom XML   │  │ openpyxl        │  │
│ │ → per-section   │  │ → _model.json│  │ → _inventory.json│ │
│ │   Markdown      │  │ → entities.md│  │ → per-type.md   │  │
│ └────────┬────────┘  └──────┬───────┘  └────────┬────────┘  │
└──────────┼──────────────────┼───────────────────┼───────────┘
           │                  │                   │
           ▼                  ▼                   ▼
┌──────────────────────────────────────────────────────────────┐
│ CHUNKING (Table-aware)                                       │
│                                                              │
│ Prose: 256 tokens  │  Tables: 512-1536 tokens (keep intact) │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ EMBEDDING                                                    │
│                                                              │
│ Each chunk → nomic-embed-text → 768-dim vector              │
└──────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ ChromaDB (Vectors)      │     │ BM25 DocStore (Text)    │
│ - ~3,400 chunks         │     │ - Same chunks           │
│ - 768 dimensions        │     │ - Keyword index         │
│ - Cosine similarity     │     │ - BM25 scoring          │
└─────────────────────────┘     └─────────────────────────┘
```

### Step-by-Step

#### 1. Source Datasets

| Source | Format | Content | Size |
|--------|--------|---------|------|
| **FA Handbook** | PDF | Governance rules, definitions, obligations | 2.5M chars, 44 sections |
| **LeanIX Conceptual Model** | XML (draw.io) | 175 entities with domains, relationships | 175 fact sheets |
| **LeanIX Inventory** | Excel | 1,424 fact sheets (applications, data objects, etc.) | 8 fact sheet types |

---

#### 2. Preprocessing

**FA Handbook (PDF) → Markdown**:
- Tool: IBM Docling (deep learning layout analysis)
- Process: PDF → per-section Markdown (44 sections: s01–s44)
- Tables preserved as markdown pipe-delimited rows
- First run downloads models (~200MB), then fully offline
- Performance: ~250 seconds for full handbook

**LeanIX XML → JSON + Markdown**:
- Tool: Custom Python parser
- Process: Parse draw.io XML → extract entities + relationships
- Outputs:
  - `_model.json` (175 entities, structured, for direct lookup)
  - `_entities.md`, `_relationships.md` (for semantic search)
- Performance: ~5 seconds

**LeanIX Excel → JSON + Markdown**:
- Tool: `openpyxl` library
- Process: Read Excel → group by fact sheet type
- Outputs:
  - `_inventory.json` (1,424 fact sheets, keyed by `fact_sheet_id`)
  - Per-type Markdown files (8 files)
- Performance: ~10 seconds

---

#### 3. Chunking

**Why chunk?** LLMs have limited context windows (16K tokens). We can't pass entire documents.

**Our strategy**: Table-aware chunking

| Content Type | Chunk Size | Rationale |
|--------------|------------|-----------|
| **Prose** | 256 tokens | Sentence-aware boundaries |
| **Tables** | 512-1536 tokens | Keep table rows intact (definitions must not be split) |

**Example**:
```
FA Handbook Definitions Table (Rules §8):
| Term        | Means                                          |
|-------------|------------------------------------------------|
| Club        | Any club which plays the game of football...   |
| Player      | Any person who plays football...               |

These rows stay intact — never split across chunks.
```

**Result**: ~3,400 chunks for FA Handbook

---

#### 4. Embedding

**What is an embedding?**
- Convert text → vector (list of numbers)
- Similar text → similar vectors (close in vector space)
- Enables semantic search: "Club" ≈ "Organisation"

**Our model**: `nomic-embed-text`
- 768-dimensional vectors
- Local (Ollama), no API calls
- Batch size: 1 chunk at a time

**Example**:
```
Chunk: "Club means any club which plays the game of football..."
↓ nomic-embed-text
Embedding: [0.123, -0.456, 0.789, ..., -0.234]  # 768 numbers
```

---

#### 5. Storage: Dual Store Architecture

**Why two stores?**
- **Vector search** (ChromaDB): Semantic similarity ("Club" ≈ "Organisation")
- **Keyword search** (BM25): Exact matches ("Rule A1", "Club")
- **Combined**: Hybrid retrieval captures both

| Store | Content | Search Type | Use Case |
|-------|---------|-------------|----------|
| **ChromaDB** | Vectors + metadata | Cosine similarity | Semantic search |
| **BM25 DocStore** | Text + metadata | Keyword matching | Exact term matching |

**Metadata stored with each chunk**:
```python
{
  "text": "Club means any club which plays...",
  "embedding": [0.123, -0.456, ...],  # 768 dimensions
  "metadata": {
    "domain": "PARTY",
    "section": "A1",
    "source": "fa_handbook",
    "source_file": "FA_Handbook_2025-26.pdf"
  }
}
```

---

## Part 3: Query Phase — Using RAG to Answer Questions

### Overview

```
┌──────────────────────────────────────────────────────────────┐
│ USER PROMPT: "What is a Club and what governance rules apply?"│
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 1. MULTI-QUERY EXPANSION (optional, num_queries=3)           │
│                                                              │
│ LLM generates 2 more variants:                               │
│ - "Club definition FA Handbook governance"                   │
│ - "Club rules obligations affiliation"                       │
└──────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ 2a. BM25 Retrieval      │     │ 2b. Vector Retrieval    │
│ - Keyword matching       │     │ - Semantic similarity   │
│ - Finds "Club", "Rule"  │     │ - Finds "organisation"  │
│ - Top 15 matches        │     │ - Top 15 matches        │
└─────────────────────────┘     └─────────────────────────┘
              │                               │
              └───────────────┬───────────────┘
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 3. FUSION (QueryFusionRetriever)                             │
│                                                              │
│ - Merge both result sets (30 candidates)                     │
│ - Reciprocal reranking (BM25 rank + Vector rank)             │
│ - Remove duplicates                                          │
│ → 24 unique candidates                                       │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 4. RERANKING (Embedding or Cross-Encoder)                    │
│                                                              │
│ - Compute cosine similarity: query ↔ each candidate          │
│ - MMR diversity: penalize near-duplicates                    │
│ - Select top 10                                              │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 5. LOST-IN-MIDDLE REORDER                                    │
│                                                              │
│ Before: [chunk7, chunk3, chunk9, chunk1, chunk5, ...]        │
│ After:  [chunk1, chunk9, chunk7, chunk5, chunk3, ...]        │
│ (Best at start/end, worst in middle)                         │
└──────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────┐
│ 6. LLM SYNTHESIS                                             │
│                                                              │
│ Prompt to LLM:                                               │
│ ┌────────────────────────────────────────────────────────┐   │
│ │ SYSTEM: You are a helpful assistant...                 │   │
│ │ CONTEXT:                                               │   │
│ │ [Chunk 1] Club means any club which...                 │   │
│ │ [Chunk 2] Rule A1: Club must be affiliated...          │   │
│ │ ... (10 chunks total)                                  │   │
│ │ USER: What is a Club and what governance rules apply?  │   │
│ └────────────────────────────────────────────────────────┘   │
│                                                              │
│ LLM: qwen3.5:9b (16K context window)                        │
│                                                              │
│ Response:                                                    │
│ {                                                            │
│   "formal_definition": "Club means any club which...",       │
│   "domain_context": "Central entity in PARTY domain...",     │
│   "governance_rules": "Rule A1: Club must be affiliated..."  │
│ }                                                            │
└──────────────────────────────────────────────────────────────┘
```

### Step-by-Step

#### 1. Multi-Query Expansion (Optional)

**Why?** Users ask compound questions. Generate variants for broader recall.

```
User query: "What is a Club?"
↓ LLM generates 2 more variants
Queries:
  1. "What is a Club?"
  2. "Define Club in football context"
  3. "Club meaning FA rules"
```

**Cost**: Each variant adds one LLM call  
**Benefit**: Better recall for complex queries

**Configuration**: `num_queries: 3` (or `1` to disable for batch jobs)

---

#### 2. Hybrid Retrieval (BM25 + Vector)

**Why hybrid?** Each retriever has strengths:

| Retriever | Strength | Weakness Alone |
|-----------|----------|----------------|
| **BM25 (Keyword)** | Exact matches ("Rule A1", "Club") | Misses semantic similarity |
| **Vector (Dense)** | Semantic similarity ("Club" ≈ "Organisation") | Misses exact terms, IDs |
| **Hybrid (Both)** | Captures both | — |

**Process**:
```
Query: "Club governance rules"
↓
BM25: Finds chunks with "Club", "governance", "rules" (exact keywords)
Vector: Finds chunks semantically similar (even if different wording)
↓
Merge both result sets → 30 candidates
```

---

#### 3. Fusion (Merging Results)

**Problem**: BM25 and Vector return separate result sets with different scoring.

**Solution**: Reciprocal reranking
```
For each chunk:
  final_score = 1 / (rank_bm25 + rank_vector)

Example:
  Chunk A: rank_bm25=1, rank_vector=5 → score = 1/6 = 0.167
  Chunk B: rank_bm25=3, rank_vector=2 → score = 1/5 = 0.200
  → Chunk B ranks higher
```

**Result**: 24 unique candidates (duplicates removed)

---

#### 4. Reranking

**Why rerank?** Initial retrieval optimizes for speed (approximate nearest neighbors). Reranking optimizes for relevance.

**Our strategy**: Embedding reranker (cosine similarity)
```
For each of 24 candidates:
  similarity = cosine_similarity(query_embedding, candidate_embedding)

Sort by similarity → Select top 10
```

**MMR (Maximal Marginal Relevance)**:
- Problem: Top-10 might be 10 near-identical chunks
- Solution: Penalize chunks too similar to already-selected ones
- Result: Diverse evidence (not 10 copies of the same paragraph)

**Alternative**: Cross-encoder reranker (higher quality, slower)
- Model: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- Sees query + document together (not independently)
- Latency: 200-800ms vs. 100-500ms for embedding reranker

---

#### 5. Lost-in-Middle Reorder

**Problem**: LLMs pay more attention to content at the **start** and **end** of context, less to the middle.

**Solution**: Reorder chunks so highest-scoring appear at both ends.

```
Before: [chunk7, chunk3, chunk9, chunk1, chunk5, chunk2, ...]
After:  [chunk1, chunk9, chunk7, chunk5, chunk3, chunk2, ...]
        ↑ best                        ↑ best
```

**Benefit**: LLM attends better to the most relevant chunks.

---

#### 6. LLM Synthesis

**Final step**: Pass retrieved chunks + user query to LLM.

**Prompt structure**:
```
┌────────────────────────────────────────────────────────┐
│ SYSTEM: You are a helpful assistant that answers       │
│ based on the provided documents.                       │
│ Always ground your answers in the retrieved content.   │
│ Cite section and rule numbers where possible.          │
│                                                        │
│ CONTEXT:                                               │
│ [Chunk 1] Club means any club which plays the game...  │
│ [Chunk 2] Rule A1: Club must be affiliated to The...   │
│ [Chunk 3] Club must appoint a secretary within...      │
│ ... (10 chunks total)                                  │
│                                                        │
│ USER: What is a Club and what governance rules apply?  │
└────────────────────────────────────────────────────────┘
```

**LLM**: `qwen3.5:9b` (or `phi4:14b`)
- Context window: 16,384 tokens
- 10 chunks × ~256 tokens = ~2.6K tokens for context
- Leaves ~13K tokens for LLM output

**Output**:
```json
{
  "formal_definition": "Club means any club which plays the game of football...",
  "domain_context": "Central entity in PARTY domain, relates to Player, Competition...",
  "governance_rules": "Rule A1: Club must be affiliated. Rule C2: Club must appoint..."
}
```

---

## Part 4: Consumer Layer — Batch Processing for Catalog Generation

### The Consolidated Catalog Pipeline

**Goal**: Generate a catalog for all 175 conceptual model entities.

**Conceptual View** (simplified):

```
1. Load structured data      → LeanIX model + inventory (direct JSON read)
2. Extract handbook context  → RAG+LLM per entity (~60-90s each)
3. Merge and classify        → Combine sources, identify gaps (BOTH/LEANIX_ONLY/HANDBOOK_ONLY)
```

**Output**: `fa_consolidated_catalog.json` — hierarchical catalog with governance context for each entity.

**Detailed 7-Step Pipeline**: See [ARCHITECTURE.md](ARCHITECTURE.md) §7.1 for the complete technical pipeline with file names, data structures, and implementation details.

**Runtime**: ~45-60 minutes for full catalog (175 entities × ~15s RAG + LLM each)

**Key Optimization**: Structured data (LeanIX) uses direct JSON lookup — no RAG, no LLM. This saves ~40 minutes vs. using RAG for everything.

> See the "Key Design Decision" callout in the Executive Summary for the full rationale.

---

## Part 5: Performance Characteristics

> **Note**: Performance numbers are indicative (M3 MacBook Pro, Ollama local inference).
> Actual times vary based on hardware, model versions, and data volume.
>
> | Hardware | Expected Speed |
> |----------|----------------|
> | M3/M2 Mac (16GB+) | Baseline (numbers below) |
> | M1 Mac | ~20-30% slower |
> | Intel Mac | ~2-3x slower |
> | NVIDIA GPU (RTX 3090+) | ~2-4x faster |

### Ingestion Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| **FA Handbook PDF → Markdown** | ~250s | 2.5M chars, Docling StandardPipeline |
| **LeanIX XML → JSON + Markdown** | ~5s | 175 entities, custom parser |
| **LeanIX Excel → JSON + Markdown** | ~10s | 1,424 fact sheets, openpyxl |
| **Chunking** | ~5s | ~3,400 nodes for FA Handbook |
| **Embedding** | ~94s | Ollama, nomic-embed-text |
| **Total FA Handbook ingestion** | ~3 min | First run includes model download |

### Query Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| **Vector retrieval** | 10–50ms | ChromaDB ANN search |
| **BM25 retrieval** | 5–20ms | In-memory index |
| **Embedding reranker** | 100–500ms | Ollama embedding (20 candidates) |
| **LLM synthesis** | 10–90s | Depends on model and context size |
| **Total typical query** | 2–6s | Single question, no batch |
| **Per-entity consolidation** | ~60–90s | RAG + LLM synthesis |

### Consumer Runtime

| Consumer | Runtime (full run) | Bottleneck |
|----------|-------------------|------------|
| **fa_consolidated_catalog** | ~45–60 min | Handbook RAG (175 entities × ~15s each) |
| **fa_handbook_model_builder** | ~5-7 min | LLM synthesis (14 seed topics) |
| **fa_coverage_validator** | ~3-7 min | Retrieval only (no LLM) |

---

## Part 6: Example Walkthrough — "What is a Club?"

### The Full Flow

**User query**: "What is a Club, and what governance rules apply?"

**Step 1**: Consumer loads `Club` entity from `_model.json`
- domain: `PARTY`, fact_sheet_id: `12345`

**Step 2**: Inventory lookup
- `_inventory.json["12345"]` → "An organisation affiliated with The Association..."

**Step 3**: RAG Query
- Query: `"Club PARTY rules governance obligations"`
- **BM25** finds chunks with "Club", "organisation", "affiliated"
- **Vector** finds chunks semantically similar (even if different wording)
- **Fusion** merges both result sets
- **Reranker** scores all 20 candidates by cosine similarity
- **Top-8 chunks** selected

**Step 4**: LLM Synthesis
- Prompt + 8 chunks → `qwen3.5:9b` →
```json
{
  "formal_definition": "Club means any club which plays the game of football...",
  "domain_context": "Central entity in PARTY domain, relates to Player, Competition...",
  "governance_rules": "Rule A1: Club must be affiliated. Rule C2: Club must appoint..."
}
```

**Step 5**: Consolidation
- All sources merged → `fa_consolidated_catalog.json`

**Total latency**: ~15s retrieval + ~60s LLM = ~75s per entity

---

## Part 7: Limitations & Considerations

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| **LLM can still hallucinate** | Rare, but possible — may invent rule numbers or misquote definitions | Citations required in prompts, human SME review mandatory, gap analysis validates coverage |
| **Batch processing is slow** | ~45-60 min for full catalog (175 entities) | Run overnight, cache results, use `--skip-relationships` for faster iteration |
| **New handbook editions require re-ingestion** | ~3 min downtime for full re-ingestion | Schedule during maintenance window, incremental updates supported |
| **Domain-specific jargon** | May reduce retrieval accuracy for obscure terms | Custom prompts with few-shot examples, entity alias mappings, domain metadata filtering |
| **Local LLM quality vs. cloud** | `qwen3.5:9b` good but not GPT-4 level | Use larger local models (`phi4:14b`) for critical tasks, cloud fallback if needed |
| **No real-time updates** | Changes to source files require manual re-ingestion | Automated ingestion pipeline (planned), change detection already implemented |

**What This Means for Stakeholders**:
- ✅ **Human review is mandatory** — this is an automation tool, not a replacement for SME expertise
- ✅ **Plan for batch windows** — full catalog generation takes ~1 hour, schedule accordingly
- ✅ **Version control matters** — track handbook editions, model versions, and catalog outputs together

---

## Part 8: What Makes This Implementation Different

### Key Features

| Feature | What It Does | Why It Matters |
|---------|--------------|----------------|
| **Hybrid retrieval** | BM25 (keyword) + Vector (semantic) | Captures both exact matches and conceptual similarity |
| **Reranking** | Re-scores retrieved chunks by relevance | Ensures LLM receives most pertinent chunks |
| **MMR diversity** | Penalizes near-duplicate chunks | Prevents top-8 being 8 copies of same paragraph |
| **Lost-in-middle** | Reorders chunks for better LLM attention | LLM attends better to start/end of context |
| **Multi-query expansion** | Generates query variants via LLM | Better recall for compound questions |
| **Table-aware chunking** | Keeps table rows intact | FA Handbook definitions table preserved |
| **JSON sidecar pattern** | Structured data read directly (not via RAG) | Fast, deterministic, exact matches |
| **Local-first** | All embeddings + LLM via Ollama | No external API dependencies, data stays on-premises |

---

## Glossary

| Term | Definition |
|------|------------|
| **Chunk** | A segment of text (256-1536 tokens) |
| **Embedding** | Vector representation of text (768 dimensions) |
| **Vector Store** | Database for embeddings (ChromaDB) |
| **BM25** | Keyword-based search algorithm |
| **Hybrid Retrieval** | Combining BM25 + Vector search |
| **Reranking** | Re-scoring retrieved results by relevance |
| **MMR** | Maximal Marginal Relevance (diversity) |
| **Lost-in-Middle** | LLM attention bias toward start/end of context |
| **Context Window** | LLM's maximum input size (16K tokens for qwen3.5:9b) |

---

## See Also

| Document | Purpose |
|----------|---------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Complete technical architecture |
| [RAG_STRATEGY.md](RAG_STRATEGY.md) | Retrieval strategy details, tuning |
| [ORCHESTRATION.md](ORCHESTRATION.md) | Runbooks, commands, phase status |
| [README.md](README.md) | Quick start commands |

---

**Document Status**: Living Document  
**Next Review**: After stakeholder feedback
