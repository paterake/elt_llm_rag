# Complete Data Flow: Ingestion → Retrieval → LLM Prompt

**Purpose**: Explain exactly how chunks flow from PDF → ChromaDB → LLM prompt

**Last Updated**: March 2026

---

## Part 1: Ingestion (elt_llm_ingest)

### FA Handbook Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: PDF Input                                               │
│ File: FA_Handbook_2025-26.pdf (2.2M chars, ~550K tokens)       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Pre-parser Splits by Section                            │
│ Input: Full PDF                                                 │
│ Output: 44 separate section files (s01.md, s02.md, ... s44.md) │
│                                                                 │
│ Example:                                                        │
│   - s01.md: Articles of Association (50 pages)                 │
│   - s02.md: Definitions (20 pages)                             │
│   - s05.md: Governance Rules (80 pages)                        │
│   - ...                                                         │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Markdown Conversion (Docling)                           │
│ Input: section PDF                                              │
│ Output: section.md (text extracted, tables preserved)          │
│                                                                 │
│ Example output (s02.md):                                        │
│ ```markdown                                                     │
│ # Definitions                                                   │
│                                                                 │
│ ## Club                                                         │
│ Club means any club which plays the game of football...        │
│                                                                 │
│ ## Player                                                       │
│ | Type | Description |                                          │
│ |------|-------------|                                          │
│ | Contract Player | A player who... |                          │
│ ```                                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Chunking                                                │
│ Input: section.md                                               │
│ Output: List of chunks (256 tokens prose, 512-1536 tokens tables)│
│                                                                 │
│ Example chunks from s02.md:                                     │
│   Chunk 1: "Club means any club which plays the game of..."    │
│            (256 tokens)                                         │
│   Chunk 2: "Player means any Contract Player, Non Contract..." │
│            (256 tokens)                                         │
│   Chunk 3: [Table row preserved intact]                        │
│            (512 tokens - table row kept together)               │
│                                                                 │
│ Overlap: 32 tokens (12.5%) - prevents split-boundary loss      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Embedding                                               │
│ Input: List of chunks                                           │
│ Output: List of (chunk_text, chunk_embedding)                  │
│                                                                 │
│ For each chunk:                                                 │
│   embedding = nomic-embed-text.encode(chunk_text)              │
│   # Returns 768-dimensional vector                             │
│                                                                 │
│ Example:                                                        │
│   Chunk 1 → [0.023, -0.145, 0.089, ..., 0.234] (768 dims)     │
│   Chunk 2 → [-0.012, 0.234, -0.067, ..., 0.189] (768 dims)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: Store in ChromaDB (TWO STORES)                          │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐│
│ │ Store 1: Vector Store (chroma.sqlite3)                      ││
│ │ - Stores: chunk_id, embedding (768-dim vector), metadata    ││
│ │ - Purpose: Semantic similarity search (cosine similarity)   ││
│ │ - Example query: "Find chunks similar to 'Club Official'"   ││
│ └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│ ┌─────────────────────────────────────────────────────────────┐│
│ │ Store 2: Docstore (docstore.json)                           ││
│ │ - Stores: chunk_id, chunk_text (full text), metadata        ││
│ │ - Purpose: BM25 keyword search + full text retrieval        ││
│ │ - Example query: "Find chunks containing 'Club Official'"   ││
│ └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│ Metadata for each chunk:                                        │
│   {                                                             │
│     "collection": "fa_handbook_s02",                           │
│     "section": "Definitions",                                  │
│     "page": 45,                                                │
│     "chunk_type": "prose" | "table",                           │
│     "chunk_id": 123                                            │
│   }                                                             │
└─────────────────────────────────────────────────────────────────┘
```

**Result**: 44 collections in ChromaDB
- `fa_handbook_s01` (Articles of Association)
- `fa_handbook_s02` (Definitions)
- `fa_handbook_s05` (Governance Rules)
- ... (44 total)

Each collection has:
- **Vector Store**: Embeddings for semantic search
- **Docstore**: Full text for BM25 keyword search

---

### LeanIX Asset Inventory Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: Excel Input                                             │
│ File: LeanIX_inventory.xlsx (1424 fact sheets)                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Parse Excel (openpyxl)                                  │
│ Input: Excel file                                               │
│ Output: List of fact sheets                                     │
│                                                                 │
│ Example fact sheet:                                             │
│   {                                                             │
│     "fact_sheet_id": "12345",                                  │
│     "name": "Club",                                            │
│     "description": "A football club affiliated with the FA",   │
│     "level": "L2",                                             │
│     "status": "Active"                                         │
│   }                                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Create JSON Sidecar                                     │
│ Input: List of fact sheets                                      │
│ Output: _inventory.json (keyed by fact_sheet_id)               │
│                                                                 │
│ Structure:                                                      │
│   {                                                             │
│     "fact_sheets": {                                            │
│       "12345": {                                                │
│         "name": "Club",                                        │
│         "description": "A football club...",                   │
│         "level": "L2",                                         │
│         "status": "Active"                                     │
│       },                                                       │
│       "67890": { ... }                                         │
│     }                                                           │
│   }                                                             │
│                                                                 │
│ Location: Next to source Excel file                            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Create Markdown (for RAG)                               │
│ Input: List of fact sheets                                      │
│ Output: inventory.md (structured text for RAG queries)         │
│                                                                 │
│ Example:                                                        │
│ ```markdown                                                     │
│ # LeanIX Asset Inventory                                        │
│                                                                 │
│ ## Club (fact_sheet_id: 12345)                                 │
│ Description: A football club affiliated with the FA            │
│ Level: L2                                                       │
│ Status: Active                                                  │
│                                                                 │
│ ## Player (fact_sheet_id: 67890)                               │
│ Description: A registered football player                      │
│ Level: L3                                                       │
│ Status: Active                                                  │
│ ```                                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Store in ChromaDB (Optional)                            │
│                                                                 │
│ Vector Store: Embeddings for semantic search                   │
│ Docstore: Full text for BM25 search                            │
│                                                                 │
│ NOTE: This is BACKUP - primary access is direct JSON lookup    │
│                                                                 │
│ Why? JSON lookup is O(1) - faster than RAG query               │
│ RAG is only used if you don't know the fact_sheet_id           │
└─────────────────────────────────────────────────────────────────┘
```

**Key Point**: Inventory is primarily accessed via **direct JSON lookup** (O(1) by fact_sheet_id), NOT RAG.

---

### LeanIX Conceptual Model Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: draw.io XML Input                                       │
│ File: DAT_V00.01_FA Enterprise Conceptual Data Model.xml       │
│ (175 entities, 9 domains, hierarchical structure)              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Parse XML + Spatial Analysis                            │
│ Input: draw.io XML                                              │
│ Output: Hierarchical entity structure                           │
│                                                                 │
│ Extraction:                                                     │
│   1. Detect group containers (domain boxes)                    │
│   2. Detect subgroup containers (subgroup boxes)               │
│   3. Detect leaf entities (entity boxes)                       │
│   4. Spatial containment → hierarchy assignment                │
│                                                                 │
│ Example output:                                                 │
│   {                                                             │
│     "domain": "PARTY",                                         │
│     "subgroup": "Individual",                                  │
│     "entities": [                                              │
│       {"name": "Player", "fact_sheet_id": "12345"},           │
│       {"name": "Club Official", "fact_sheet_id": "67890"}     │
│     ]                                                           │
│   }                                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Create JSON Sidecar                                     │
│ Input: Hierarchical structure                                   │
│ Output: _model.json                                             │
│                                                                 │
│ Structure:                                                      │
│   {                                                             │
│     "entities": [                                              │
│       {                                                         │
│         "entity_name": "Club",                                 │
│         "domain": "PARTY",                                     │
│         "subgroup": "Organisation",                            │
│         "fact_sheet_id": "11111"                               │
│       },                                                       │
│       ... (175 total)                                          │
│     ],                                                         │
│     "relationships": [                                         │
│       {                                                         │
│         "source_entity": "PARTY",                              │
│         "target_entity": "AGREEMENTS",                         │
│         "relationship_type": "relates to",                     │
│         "cardinality": "many-to-many"                          │
│       },                                                       │
│       ... (9 domain-level relationships)                       │
│     ]                                                           │
│   }                                                             │
│                                                                 │
│ Location: Next to source XML file                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Create Markdown (for RAG)                               │
│ Input: Hierarchical structure                                   │
│ Output: entities.md (structured text for RAG queries)          │
│                                                                 │
│ Example:                                                        │
│ ```markdown                                                     │
│ # LeanIX Conceptual Model                                       │
│                                                                 │
│ ## PARTY Domain                                                 │
│                                                                 │
│ ### Individual Subgroup                                        │
│ - Player (fact_sheet_id: 12345)                                │
│ - Club Official (fact_sheet_id: 67890)                         │
│                                                                 │
│ ### Organisation Subgroup                                      │
│ - Club (fact_sheet_id: 11111)                                  │
│ - Supplier (fact_sheet_id: 22222)                              │
│ ```                                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Store in ChromaDB (Optional)                            │
│                                                                 │
│ Vector Store: Embeddings for semantic search                   │
│ Docstore: Full text for BM25 search                            │
│                                                                 │
│ NOTE: This is BACKUP - primary access is direct JSON lookup    │
└─────────────────────────────────────────────────────────────────┘
```

**Key Point**: Conceptual model is primarily accessed via **direct JSON lookup**, NOT RAG.

---

## Part 2: Retrieval (elt_llm_consumer / elt_llm_agent)

### The Critical Flow: How Chunks Reach the LLM Prompt

```
┌─────────────────────────────────────────────────────────────────┐
│ QUERY: "Get governance context for 'Club Official'"            │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 1: BM25 Section Routing (elt_llm_query/query.py)          │
│ Purpose: Decide WHICH sections to query (not all 44)           │
│                                                                 │
│ Process:                                                        │
│   1. Get entity aliases: ["Club Official", "Director",         │
│                           "Officer", "Club Officer"]           │
│   2. For each alias, run BM25 on ALL 44 sections:              │
│      - Load docstore.json for section s01                      │
│      - BM25.retrieve("Club Official") → top-3 chunks          │
│      - Score = BM25 score (TF-IDF based)                       │
│      - Repeat for all 44 sections                              │
│   3. Keep sections with score > threshold (e.g., > 0.0)        │
│                                                                 │
│ Output: relevant_sections = ["fa_handbook_s05",                │
│                              "fa_handbook_s10",                │
│                              "fa_handbook_s02"]                │
│                                                                 │
│ Why? Querying 3 sections is faster than all 44                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 2: Keyword Scan (Safety Net)                              │
│ Purpose: Find verbatim mentions BM25 might miss                │
│                                                                 │
│ Process:                                                        │
│   1. For each section docstore:                                │
│      - Scan every chunk text                                   │
│      - if "Club Official" in chunk_text.lower():               │
│          add to keyword_chunks                                 │
│   2. Deduplicate chunks                                        │
│                                                                 │
│ Output: keyword_chunks = [                                     │
│   "Club Official means any Director of any Club...",           │
│   "Every Club Official must comply with the Code...",          │
│   ... (5-10 chunks)                                            │
│ ]                                                               │
│                                                                 │
│ Why? BM25 might miss operational mentions in rules sections    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 3: Hybrid Retrieval (elt_llm_query/query.py)              │
│ Purpose: Get candidate chunks from selected sections           │
│                                                                 │
│ Process:                                                        │
│   For each section in relevant_sections:                       │
│     1. Load vector index (fa_handbook_s05)                     │
│     2. Build hybrid retriever:                                 │
│        - Vector retriever: cosine similarity on embeddings     │
│        - BM25 retriever: TF-IDF on full text                   │
│        - QueryFusionRetriever merges both results              │
│     3. Retrieve top-k chunks per section:                      │
│        query = "Club Official governance rules PARTY"          │
│        chunks = retriever.retrieve(query)                      │
│        # Returns NodeWithScore objects                         │
│                                                                 │
│ Output: candidate_pool = [                                     │
│   NodeWithScore(chunk_1, score=0.92),                          │
│   NodeWithScore(chunk_2, score=0.87),                          │
│   ... (20-50 chunks total)                                     │
│ ]                                                               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 4: Reranking (elt_llm_query/query.py)                     │
│ Purpose: Re-score chunks by query relevance                    │
│                                                                 │
│ Process:                                                        │
│   1. Compute query embedding:                                  │
│      query_embedding = nomic-embed-text.encode(query)          │
│   2. For each chunk in candidate_pool:                         │
│      chunk.score = cosine_similarity(                          │
│         query_embedding,                                       │
│         chunk.embedding                                        │
│      )                                                         │
│   3. Sort by score descending                                  │
│   4. Keep top-k (e.g., top-10)                                 │
│                                                                 │
│ Output: reranked_chunks = [                                    │
│   NodeWithScore(chunk_5, score=0.95),  # Re-scored!            │
│   NodeWithScore(chunk_2, score=0.91),                          │
│   ... (10 chunks)                                              │
│ ]                                                               │
│                                                                 │
│ Why? Initial retrieval optimizes for speed (approximate NN),   │
│ reranking optimizes for relevance (exact cosine similarity)    │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 5: Build LLM Prompt                                       │
│ Purpose: Combine retrieved chunks + structured prompt          │
│                                                                 │
│ Process:                                                        │
│   1. Load prompt template (handbook_context.yaml):             │
│      prompt = """Provide a complete terms of reference...      │
│                FORMAL_DEFINITION:...                           │
│                DOMAIN_CONTEXT:...                              │
│                GOVERNANCE:...                                  │
│                ..."""                                          │
│                                                                 │
│   2. Format with entity details:                               │
│      prompt = prompt.format(                                   │
│         entity_name="Club Official",                           │
│         domain="PARTY"                                         │
│      )                                                         │
│                                                                 │
│   3. Add retrieved chunks as context:                          │
│      prompt += "\n\nContext information:\n"                    │
│      for chunk in reranked_chunks:                             │
│          prompt += f"- {chunk.text}\n"                         │
│                                                                 │
│   4. Add keyword chunks (verbatim mentions):                   │
│      if keyword_chunks:                                        │
│          prompt += "\n\nThe following passages explicitly..."  │
│          for chunk in keyword_chunks[:5]:                      │
│              prompt += f"- {_extract_around_mention(           │
│                  chunk, "Club Official")}\n"                   │
│                                                                 │
│ Final Prompt Structure:                                         │
│ ┌─────────────────────────────────────────────────────────────┐│
│ │ SYSTEM: You are a legal/governance domain expert...         ││
│ │                                                               ││
│ │ USER: Provide a complete terms of reference for             ││
│ │       'Club Official' in the PARTY domain...                ││
│ │                                                               ││
│ │ Context information:                                          ││
│ │ - Club Officials are bound by The Association's Code...     ││
│ │ - Section 10(A)(1): Advertising on clothing is permitted... ││
│ │ - A Club Official holds office or acts as a representative..││
│ │ ... (10 reranked chunks)                                    ││
│ │                                                               ││
│ │ The following passages explicitly mention 'Club Official':  ││
│ │ - Club Official means any Director of any Club...           ││
│ │ - Every Club Official must comply with the Code...          ││
│ │ ... (5 keyword chunks)                                      ││
│ │                                                               ││
│ │ Using both the context information and your training data,  ││
│ │ provide a clear answer.                                     ││
│ └─────────────────────────────────────────────────────────────┘│
│                                                                 │
│ Total prompt size: ~3000-5000 tokens                           │
│ - Prompt template: ~500 tokens                                 │
│ - Retrieved chunks: ~2000-3000 tokens (10 × 200-300 tokens)   │
│ - Keyword chunks: ~500-1000 tokens (5 × 100-200 tokens)       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ STEP 6: LLM Synthesis (Ollama)                                 │
│ Purpose: Generate structured output from prompt                │
│                                                                 │
│ Process:                                                        │
│   1. Send prompt to Ollama:                                    │
│      response = ollama.generate(                               │
│         model="qwen3.5:9b",                                    │
│         prompt=prompt                                          │
│      )                                                         │
│   2. LLM reads prompt + context                                │
│   3. LLM generates structured response:                        │
│      FORMAL_DEFINITION: any Director of any Club...            │
│      DOMAIN_CONTEXT: Club Officials are bound by...            │
│      GOVERNANCE: Section 10(A)(1)...                           │
│      ...                                                       │
│   4. Parse response by field labels                            │
│                                                                 │
│ Output:                                                         │
│   {                                                             │
│     "formal_definition": "any Director of any Club...",        │
│     "domain_context": "Club Officials are bound by...",        │
│     "governance_rules": "Section 10(A)(1)...",                 │
│     ...                                                         │
│   }                                                             │
│                                                                 │
│ Runtime: ~60-90s (dominated by LLM generation)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Insights

### 1. Two Stores, Two Purposes

| Store | What It Stores | How It's Used |
|-------|---------------|---------------|
| **Vector Store** | Embeddings (768-dim vectors) | Semantic similarity search |
| **Docstore** | Full chunk text | BM25 keyword search + verbatim scan |

**Both are queried** — vector for semantic meaning, docstore for exact keywords.

---

### 2. Chunk Selection Funnel

```
All 44 sections
    ↓ (BM25 section routing)
3-10 relevant sections
    ↓ (Hybrid retrieval)
20-50 candidate chunks
    ↓ (Reranking)
10 best chunks
    ↓ (Keyword injection)
+ 5 verbatim chunks
    ↓
15 chunks total → LLM prompt
```

**Each stage narrows down** to the most relevant content.

---

### 3. Why Keyword Injection Matters

**Without keyword injection**:
- Reranker might deprioritize chunks with exact entity mentions
- Example: "Club Official" chunk scores 0.75, generic "governance" chunk scores 0.85
- LLM never sees the exact definition

**With keyword injection**:
- Verbatim chunks bypass reranker
- LLM ALWAYS sees exact mentions
- Result: Better definitions, more accurate extraction

---

### 4. Prompt Size Breakdown

| Component | Tokens | % of Total |
|-----------|--------|------------|
| System prompt | ~100 | 2-3% |
| User instructions | ~400 | 8-10% |
| Retrieved chunks (10 × 250) | ~2500 | 50-60% |
| Keyword chunks (5 × 150) | ~750 | 15-20% |
| Formatting/spacing | ~500 | 10-15% |
| **Total** | **~4250** | **100%** |

**Well within qwen3.5:9b's 16K context window** — plenty of room.

---

## Summary: Complete Flow

```
PDF → Sections → Markdown → Chunks → Embeddings → ChromaDB
                                                    ↓
Query → BM25 Routing → Keyword Scan → Hybrid Retrieval → Rerank
                                                              ↓
                                                      LLM Prompt
                                                      (chunks + template)
                                                              ↓
                                                        LLM Response
                                                        (structured JSON)
```

**The magic**: Chunks flow from ChromaDB → reranked list → prompt context → LLM synthesis → structured output.
