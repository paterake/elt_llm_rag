# RAG Pipeline Deep Dive

**Module**: `elt_llm_query` + `elt_llm_consumer`
**Purpose**: Implementation-level detail of the RAG retrieval and synthesis pipeline
**Audience**: Engineers debugging, optimizing, or extending the RAG system

---

## Overview: The 7-Stage Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: RETRIEVAL PLANNING (3 parallel paths)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                          │
│  │ Stage 1a    │  │ Stage 1b    │  │ Stage 1c    │                          │
│  │ BM25        │  │ LLM Alias   │  │ Keyword     │                          │
│  │ Section     │  │ Expansion   │  │ Scan        │                          │
│  │ Routing     │  │ (Fallback)  │  │ (Verbatim)  │                          │
│  └─────────────┘  └─────────────┘  └─────────────┘                          │
│         │                │                │                                  │
│         └────────────────┴────────────────┘                                  │
│                      │                                                       │
│                      ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ STAGE 2: MERGE — unified_collections = BM25 ∪ Keyword sections          ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                      │                                                       │
│                      ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ STAGE 3: EXACT DEFINITION CHECK — term_definitions dict lookup          ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                      │                                                       │
│                      ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ STAGE 4: PROMPT ASSEMBLY — template + context + keyword_suffix        ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                      │                                                       │
│                      ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ STAGE 5: HYBRID RETRIEVAL — Vector + BM25 → candidate_pool             ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                      │                                                       │
│                      ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ STAGE 6: RERANKING — Cross-encoder or Embedding cosine similarity       ││
│  └──────────────────────────────────────────────────────────────────────────┘│
│                      │                                                       │
│                      ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ STAGE 7: LLM SYNTHESIS — Ollama + prompt → structured response          ││
│  └──────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────┘
```

**Typical latencies** (per entity, qwen3.5:9b):
- Stage 1a (BM25 section routing): ~1-2s
- Stage 1b (LLM alias expansion): ~3-5s (only if 1a finds 0 sections)
- Stage 1c (Keyword scan): ~0.5-1s
- Stage 5 (Hybrid retrieval): ~0.3-0.5s
- Stage 6 (Reranking): ~0.1-0.2s
- Stage 7 (LLM synthesis): ~60-90s

**Total**: ~65-100s per entity (dominated by LLM)

---

## Stage 1a: BM25 Section Routing

**File**: `elt_llm_query/src/elt_llm_query/query.py:126-210`

### Purpose
Fast (~1-2s) identification of which handbook sections (`fa_handbook_s00`...`fa_handbook_s44`) are relevant to the query entity.

### Algorithm
```python
def discover_relevant_sections(
    entity_name: str,
    aliases: list[str],  # From entity_aliases.yaml
    section_prefix: str = "fa_handbook",
    bm25_top_k: int = 3,
    threshold: float = 0.0,
) -> list[str]:
    """BM25 section routing — no LLM, no embedding."""
    
    # 1. Resolve all collections matching prefix
    all_collections = resolve_collection_prefixes([section_prefix], rag_config)
    section_collections = [c for c in all_collections if re.match(r's\d{2}$', c)]
    
    # 2. For each section, load docstore and run BM25
    for collection_name in section_collections:
        docstore_path = get_docstore_path(rag_config.chroma, collection_name)
        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = list(storage.docstore.docs.values())  # ← Full text from JSON
        
        # 3. BM25 retriever (in-memory, no Chroma vector store)
        bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=bm25_top_k)
        
        # 4. Query with entity name + all aliases, keep best score
        query_variants = [entity_name] + aliases
        max_score = max(bm25.retrieve(variant) for variant in query_variants)
        
        if max_score >= threshold:
            scored.append((collection_name, max_score))
    
    return sorted(scored, key=lambda x: x[1], reverse=True)
```

### Input
- `entity_name`: "Sports Governing Body"
- `aliases`: ["national governing body", "governing body", "ngb", ...] (from YAML)

### Output
```python
["fa_handbook_s05", "fa_handbook_s01", "fa_handbook_s12", ...]
```

### Why Docstore (Not Vector Store)?
BM25 requires **term frequency** calculations on full text — embeddings can't compute TF-IDF. The docstore JSON contains the raw chunk text needed for BM25 scoring.

### Performance
- 44 sections × ~20-50ms per BM25 query = ~1-2s total
- No LLM, no embeddings — pure in-memory text scoring

---

## Stage 1b: LLM Alias Expansion (Fallback)

**File**: `elt_llm_query/src/elt_llm_query/query.py:281-315`

### Purpose
Generate domain-aware synonyms when Stage 1a finds **zero** sections (rare — only for entities not in `entity_aliases.yaml`).

### Algorithm
```python
def expand_entity_aliases(
    entity_name: str,
    rag_config: RagConfig,
) -> list[str]:
    """LLM generates synonyms — fallback when BM25 + YAML aliases fail."""
    
    prompt = (
        f"In FA football governance, list 2-4 alternative names or related official "
        f"terms that the FA Handbook might use for the concept '{entity_name}'. "
        f"Return only a comma-separated list of terms with no explanations."
    )
    
    llm = create_llm_model(rag_config.ollama)
    response = str(llm.complete(prompt)).strip()  # ← LLM CALL (~3-5s)
    
    terms = [t.strip().lower() for t in response.split(",") if t.strip()]
    return terms[:4]
```

### When It Runs
```python
# In fa_consolidated_catalog.py:1240
relevant_sections = discover_relevant_sections(name, aliases=aliases)

if not relevant_sections:  # ← Stage 1a found nothing
    llm_aliases = expand_entity_aliases(name, rag_config)
    if llm_aliases:
        relevant_sections = discover_relevant_sections(
            name, aliases=llm_aliases  # ← Retry with LLM-generated aliases
        )
```

### Example
**Input**: "Local Authority" (not in YAML aliases)
**LLM Output**: "local council, planning authority, municipal authority, local government"
**Result**: BM25 retry finds `fa_handbook_s22` (ground fitness rules)

### Performance Impact
- Only runs if Stage 1a returns 0 sections (~5% of entities)
- Adds ~3-5s + another ~1-2s BM25 retry = ~5-7s total
- **Design principle**: Static YAML aliases are preferred (faster, deterministic)

---

## Stage 1c: Keyword Scan (Verbatim Match)

**File**: `elt_llm_query/src/elt_llm_query/query.py:214-278`

### Purpose
Guarantee that sections/chunks containing the **exact entity name** are found, regardless of BM25 scoring or vector similarity gaps.

### Algorithm
```python
def find_sections_by_keyword(
    term: str,  # "Sports Governing Body"
    section_prefix: str,
    rag_config: RagConfig,
) -> tuple[list[str], list[str]]:
    """Verbatim substring scan — guarantees exact matches are found."""
    
    all_collections = resolve_collection_prefixes([section_prefix], rag_config)
    section_collections = [c for c in all_collections if re.match(r's\d{2}$', c)]
    
    term_lower = term.lower()
    matched_sections: list[str] = []
    matched_chunks: list[str] = []
    seen_texts: set[str] = set()
    
    for collection_name in section_collections:
        docstore_path = get_docstore_path(rag_config.chroma, collection_name)
        storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        
        for node in storage.docstore.docs.values():  # ← Full text from JSON
            text = getattr(node, "text", "") or ""
            
            if term_lower in text.lower():  # ← Verbatim substring match
                if not section_hit:
                    matched_sections.append(collection_name)
                    section_hit = True
                
                # Deduplicate near-identical chunks
                stripped = " ".join(text.split())
                if stripped not in seen_texts:
                    seen_texts.add(stripped)
                    matched_chunks.append(text.strip())
    
    return matched_sections, matched_chunks
```

### Input
- `term`: "Sports Governing Body"

### Output
```python
(
    ["fa_handbook_s05", "fa_handbook_s01", ...],  # section_names
    [  # chunk_texts (injected directly into LLM prompt)
        "The Sports Governing Body must ensure compliance with Rule C1.2...",
        "Any recognised Sports Governing Body may apply for affiliation...",
        "The Board delegates regulatory authority to the Sports Governing Body...",
    ]
)
```

### Why This Matters: The `[:500]` Bug

**Before (broken):**
```python
# In fa_consolidated_catalog.py:520 (OLD CODE)
if keyword_chunks:
    passages = "\n".join(f"- {c[:500]}" for c in keyword_chunks[:5])
    keyword_suffix = f"...{passages}"
```

**Problem**: Takes first 500 characters, which often discards the entity mention:
```
Chunk: "...intro text about FA structure... The Sports Governing Body must comply..."
       ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ First 500 chars (entity mention at char 600)

Passage sent to LLM: "...intro text about FA structure..."
Result: LLM sees unrelated intro text, not the rule about Sports Governing Body
```

**After (fixed):**
```python
# In fa_consolidated_catalog.py:520 (NEW CODE)
if keyword_chunks:
    passages = "\n".join(
        f"- {_extract_around_mention(c, entity_name)}" for c in keyword_chunks[:5]
    )
    keyword_suffix = f"...{passages}"
```

```python
# In fa_consolidated_catalog.py:128
def _extract_around_mention(chunk: str, entity_name: str, window: int = 600) -> str:
    """Extract 600-char window centered on entity name mention."""
    idx = chunk.lower().find(entity_name.lower())
    if idx == -1:
        return chunk[:window]
    half = window // 2
    start = max(0, idx - half)
    end = min(len(chunk), idx + half)
    # Snap to word boundaries
    if start > 0:
        space = chunk.rfind(" ", 0, start + 1)
        if space != -1:
            start = space + 1
    if end < len(chunk):
        space = chunk.find(" ", end - 1)
        if space != -1:
            end = space
    return chunk[start:end].strip()
```

**Result**:
```
Chunk: "...intro text... The Sports Governing Body must comply with Rule C1.2..."
       Entity mention at position 450

_extract_around_mention finds position 450, extracts [150:750]:

Passage sent to LLM: "...intro text... The Sports Governing Body must comply 
                      with Rule C1.2... [full context]"
Result: LLM sees the actual rule, extracts governance correctly
```

### Performance
- 44 sections × ~10-20ms per substring scan = ~0.5-1s total
- No LLM, no embeddings — pure string matching

---

## Stage 2: Merge Sections

**File**: `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py:1285-1293`

### Algorithm
```python
seen_unified: set[str] = set()
unified_collections: list[str] = []

# Merge: definition sections + BM25 sections + keyword sections
for s in [*DEFINITION_SECTIONS, *bm25_sections, *keyword_sections]:
    if s not in seen_unified:
        unified_collections.append(s)
        seen_unified.add(s)
```

### Input
- `bm25_sections`: ["fa_handbook_s05", "fa_handbook_s01", ...] (Stage 1a)
- `keyword_sections`: ["fa_handbook_s05", "fa_handbook_s22", ...] (Stage 1c)

### Output
```python
unified_collections = [
    "fa_handbook_s00",  # Definition section (always included)
    "fa_handbook_s05",  # Governance (BM25 + keyword match)
    "fa_handbook_s01",  # Rules (BM25 match)
    "fa_handbook_s12",  # Competitions (BM25 match)
    "fa_handbook_s22",  # Grounds (keyword match only)
    ...
]
```

### Why Merge?
- BM25 finds **relevant** sections (semantic + lexical scoring)
- Keyword finds **verbatim** mentions (guarantees no false negatives)
- Merge ensures both are passed to hybrid retrieval

---

## Stage 3: Exact Definition Check

**File**: `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py:543-553`

### Purpose
If the handbook has an explicit "X means Y" definition, use it verbatim and skip FORMAL_DEFINITION generation (saves LLM tokens).

### Algorithm
```python
step3_def: str | None = None
if term_definitions:  # From Step 3 handbook term extraction
    lookup_keys = [entity_name.lower()]
    lookup_keys.extend(_ENTITY_ALIASES.get(entity_name.lower(), []))
    for v in _get_alias_variants(entity_name):
        if v not in lookup_keys:
            lookup_keys.append(v)
    
    # Find exact match
    step3_def = next(
        (term_definitions[k] for k in lookup_keys if k in term_definitions), 
        None
    )

if step3_def:
    sections["formal_definition"] = step3_def
    query = _HANDBOOK_CONTEXT_GOV_ONLY_PROMPT.format(...)  # ← Shorter prompt
    call_config = dataclasses.replace(
        rag_config,
        ollama=dataclasses.replace(rag_config.ollama, num_predict=1200),  # ← Fewer tokens
    )
else:
    query = _HANDBOOK_CONTEXT_PROMPT.format(...)  # ← Full prompt
    call_config = rag_config
```

### Input
- `term_definitions`: Dict from Step 3 regex extraction
  ```python
  {
      "sports governing body": "The national governing body for football...",
      "club": "Club means any club which plays the game of football...",
      ...
  }
  ```

### Output
- `step3_def`: "The national governing body for football..." (if found)
- Prompt choice: `prompt_gov_only` (shorter) vs `prompt` (full)

### Performance Impact
- Saves ~60-90s LLM time per entity with exact definition (~30% of entities)
- Reduces token budget from ~1500 to ~700 tokens

---

## Stage 4: Prompt Assembly

**File**: `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py:508-525`

### Components
```python
# 1. Base prompt (from handbook_context.yaml)
query = _HANDBOOK_CONTEXT_PROMPT.format(
    entity_name=entity_name,
    domain=domain
)

# 2. LeanIX context suffix (optional)
context_suffix = ""
if leanix_description and leanix_description != "Not documented in LeanIX inventory":
    context_suffix = f"\n\nContext from data model: {leanix_description[:500]}"

# 3. Keyword suffix (THE FIX — bypasses reranker)
keyword_suffix = ""
if keyword_chunks:
    passages = "\n".join(
        f"- {_extract_around_mention(c, entity_name)}" for c in keyword_chunks[:5]
    )
    keyword_suffix = (
        f"\n\nThe following passages from the FA Handbook explicitly mention "
        f"'{entity_name}' — they must be considered in your response:\n{passages}"
    )

# 4. Final assembled prompt
final_prompt = query + context_suffix + keyword_suffix
```

### Example Final Prompt
```
Provide a complete terms of reference entry for the FA entity 'Sports Governing Body' 
in the GOVERNANCE domain, using only the FA Handbook text provided.

Important: The FA Handbook uses multiple names for the same entities. When searching for
'Sports Governing Body', also treat the following as equivalent:
- "The Association" or "The FA" may refer to the national governing body
- "Affiliated Association" or "County FA" refers to FA County entities
...

FORMAL_DEFINITION:
[Apply these rules in order:
1. FORMAL DEFINITION EXISTS — If there is an explicit 'X means Y' statement...
...

GOVERNANCE:
[Describe the governance relationship between 'Sports Governing Body' and the FA Handbook...]

...

Context from data model: A national or international body that governs football, 
such as The FA, UEFA, or FIFA, and which holds regulatory authority over the sport.

The following passages from the FA Handbook explicitly mention 'Sports Governing Body' — 
they must be considered in your response:

- The Sports Governing Body must ensure compliance with Rule C1.2 regarding participant 
  conduct. All recognised governing bodies shall submit annual reports to The Association.

- Any recognised Sports Governing Body may apply for affiliation subject to meeting the 
  eligibility criteria set out in Section 5.

- The Board delegates regulatory authority to the Sports Governing Body for matters 
  relating to competition rules and disciplinary procedures.
```

### Why Keyword Suffix Bypasses Reranker
The keyword chunks are **injected directly into the prompt** — they don't go through Stage 5-6 retrieval/reranking. This is by design:
- Reranker might deprioritize chunks with exact entity mentions (low cosine similarity to query)
- Keyword scan guarantees the entity is mentioned — that's more important than semantic similarity
- Bypassing reranker saves ~0.1-0.2s per entity

---

## Stage 5: Hybrid Retrieval (Candidate Pool)

**File**: `elt_llm_query/src/elt_llm_query/query.py:756-783`

### Purpose
Retrieve candidate chunks from unified sections using both vector similarity and BM25 lexical matching.

### Algorithm
```python
def _get_nodes(index, name):
    """Full-context if small; hybrid/vector retrieval otherwise."""
    docstore_path = get_docstore_path(rag_config.chroma, name)
    
    # Check if full-context mode (small sections ≤ threshold)
    if full_ctx_threshold > 0 and docstore_path.exists():
        try:
            ds = StorageContext.from_defaults(persist_dir=str(docstore_path))
            doc_nodes = list(ds.docstore.docs.values())
            if 0 < len(doc_nodes) <= full_ctx_threshold:
                # Small section — return ALL chunks (no retrieval needed)
                return [NodeWithScore(node=n, score=1.0) for n in doc_nodes]
        except Exception:
            pass
    
    # Hybrid retrieval (vector + BM25)
    if rag_config.query.use_hybrid_search:
        retriever = _build_hybrid_retriever(index, name, rag_config, per_collection_k)
    else:
        retriever = index.as_retriever(similarity_top_k=per_collection_k)
    
    nodes = retriever.retrieve(query)
    return nodes

# In query_collections():
all_nodes = []
for index, name in zip(indices, collection_names):
    all_nodes.extend(_get_nodes(index, name))
```

### Hybrid Retriever Construction
```python
# In _build_hybrid_retriever()
def _build_hybrid_retriever(
    index: VectorStoreIndex,
    collection_name: str,
    rag_config: RagConfig,
    top_k: int,
):
    # Load docstore for BM25
    docstore_path = get_docstore_path(rag_config.chroma, collection_name)
    storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
    doc_nodes = list(storage.docstore.docs.values())
    
    # Build both retrievers
    vector_retriever = index.as_retriever(similarity_top_k=top_k)  # ← Vector store
    bm25_retriever = BM25Retriever.from_defaults(nodes=doc_nodes, similarity_top_k=top_k)  # ← Docstore
    
    # Fusion retriever merges both result sets
    retriever = QueryFusionRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        similarity_top_k=top_k,
        num_fusion=top_k * 2,
    )
    
    return retriever
```

### Input
- `unified_collections`: ["fa_handbook_s00", "fa_handbook_s05", ...] (Stage 2)
- `query`: "Entity: Sports Governing Body\nProvide the formal definition..."

### Output
```python
all_nodes = [
    NodeWithScore(node=chunk_1, score=0.92),
    NodeWithScore(node=chunk_2, score=0.87),
    ...
]
```

### Full-Context Mode
For small sections (≤ `full_context_max_chunks`, default 50):
- Skip retrieval entirely
- Return **all** chunks from docstore
- Saves ~0.3s retrieval time per small section

### Performance
- 10 sections × ~30-50ms per hybrid retrieval = ~0.3-0.5s total
- Full-context mode: ~10-20ms (just JSON load)

---

## Stage 6: Reranking

**File**: `elt_llm_query/src/elt_llm_query/query.py:873`

### Purpose
Re-score retrieved chunks by relevance to query (improves over raw retrieval scores).

### Algorithm
```python
# In query_collections()
all_nodes.sort(key=lambda x: x.score or 0.0, reverse=True)

if not rag_config.query.use_reranker:
    all_nodes = all_nodes[:top_k]
else:
    all_nodes = _rerank_nodes(query, all_nodes, rag_config)
```

```python
# In _rerank_nodes()
def _rerank_nodes(
    query: str,
    nodes: list[NodeWithScore],
    rag_config: RagConfig,
) -> list[NodeWithScore]:
    if rag_config.query.reranker_strategy == "cross-encoder":
        # Load cross-encoder model (e.g. bge-reranker-v2-m3)
        reranker = CrossEncoderReranker(model_name="...")
        return reranker.rerank(query, nodes, top_k=rag_config.query.reranker_top_k)
    
    else:  # embedding
        # Compute query embedding, then cosine similarity
        query_embedding = embed_model.get_query_embedding(query)
        for node in nodes:
            node.score = cosine_similarity(query_embedding, node.embedding)
        return sorted(nodes, key=lambda x: x.score, reverse=True)[:rag_config.query.reranker_top_k]
```

### Input
- `query`: "Entity: Sports Governing Body\nProvide the formal definition..."
- `all_nodes`: [NodeWithScore, ...] (Stage 5 retrieval results)

### Output
```python
reranked_nodes = [
    NodeWithScore(node=chunk_5, score=0.95),  # ← Re-scored
    NodeWithScore(node=chunk_2, score=0.91),
    ...
]
```

### Reranker Strategies
| Strategy | Model | Latency | Quality |
|----------|-------|---------|---------|
| **embedding** | nomic-embed-text (Ollama) | ~0.1s | Good |
| **cross-encoder** | bge-reranker-v2-m3 (HuggingFace) | ~0.5-1s | Better |

Default: `embedding` (fast, good enough for handbook queries)

---

## Stage 7: LLM Synthesis

**File**: `elt_llm_query/src/elt_llm_query/query.py:784-787`

### Algorithm
```python
def _synthesize(q, nodes):
    synthesizer = get_response_synthesizer(llm=llm)
    return str(synthesizer.synthesize(q, nodes=nodes)).strip()

# In query_collections():
response = _synthesize(query, all_nodes)
```

### LlamaIndex Response Synthesis
Under the hood, LlamaIndex's `get_response_synthesizer()`:
1. Builds prompt with retrieved chunks as context
2. Sends to Ollama (qwen3.5:9b or configured model)
3. Parses streaming response
4. Returns synthesized text

### Prompt Structure (Internal)
```
<|begin_of_system|>
{system_prompt}
<|end_of_system|>

<|begin_of_user|>
{query}

Context information is below.
---------------------
{chunk_1.text}
{chunk_2.text}
...
---------------------

Using both the context information and your training data, provide a clear answer.
<|end_of_user|>
```

### Output Parsing
```python
# In fa_consolidated_catalog.py:567-579
def _parse(label: str) -> str:
    m = re.search(rf"{label}:\s*(.*?)(?=\n+[A-Z_]+:|\Z)", response, re.DOTALL)
    return m.group(1).strip() if m else ""

sections["formal_definition"] = _parse("FORMAL_DEFINITION")
sections["domain_context"] = _parse("DOMAIN_CONTEXT")
sections["governance_rules"] = _parse("GOVERNANCE")
sections["business_rules"] = _parse("BUSINESS_RULES")
sections["lifecycle_states"] = _parse("LIFECYCLE_STATES")
sections["data_classification"] = _parse("DATA_CLASSIFICATION")
sections["regulatory_context"] = _parse("REGULATORY_CONTEXT")
sections["associated_agreements"] = _parse("ASSOCIATED_AGREEMENTS")
```

### Performance
- ~60-90s per entity (qwen3.5:9b, ~1200-1500 tokens output)
- Dominates total latency (>90% of time)

---

## Physical Storage Layout

```
.chroma_db/
├── fa_handbook_s00/
│   ├── chroma.sqlite3          ← Vector Store (embeddings for s00)
│   ├── 1752e8d4-....parquet    ← Embedding vectors (binary)
│   ├── 1752e8d4-....pkl        ← Metadata pickle
│   └── ...
│
├── fa_handbook_s01/
│   ├── chroma.sqlite3          ← Vector Store (embeddings for s01)
│   └── ...
│
├── ...
│
├── fa_handbook_s44/
│   ├── chroma.sqlite3          ← Vector Store (embeddings for s44)
│   └── ...
│
└── docstores/
    ├── fa_handbook_s00/
    │   └── docstore.json       ← Full text chunks for s00
    ├── fa_handbook_s01/
    │   └── docstore.json       ← Full text chunks for s01
    └── ...
```

### Vector Store Schema (ChromaDB SQLite)
```sql
-- chroma.sqlite3
CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,
    embedding FLOAT[],      -- 768-dim vector (nomic-embed-text)
    metadata JSON,          -- {section: "C1.2", page: 45, ...}
    document TEXT           -- Optional, often omitted for space
);

CREATE TABLE collections (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE,       -- "fa_handbook_s00"
    metadata JSON
);
```

### Docstore JSON Schema
```json
{
  "node_id_1": {
    "text": "The Sports Governing Body must ensure compliance with Rule C1.2...",
    "metadata": {"section": "C1.2", "page": 45, "chunk_id": 123},
    "embedding": [0.123, -0.456, ...]  -- Optional, often omitted
  },
  "node_id_2": {
    "text": "Any recognised governing body may apply for affiliation...",
    "metadata": {"section": "C2.1", "page": 47, "chunk_id": 124}
  }
}
```

### Storage Sizes (Typical)
| Component | Size per Section | Total (44 sections) |
|-----------|-----------------|---------------------|
| Vector Store (chroma.sqlite3 + parquet) | ~10-50MB | ~440MB-2.2GB |
| Docstore (docstore.json) | ~1-5MB | ~44-220MB |

---

## Component Usage Summary

| Stage | Vector Store | Docstore | LLM | Why |
|-------|-------------|----------|-----|-----|
| **1a: BM25 section routing** | ❌ No | ✅ Yes | ❌ No | BM25 needs full text for TF-IDF |
| **1b: LLM alias expansion** | ❌ No | ❌ No | ✅ Yes | Pure LLM generation (fallback only) |
| **1c: Keyword scan** | ❌ No | ✅ Yes | ❌ No | Substring match needs exact text |
| **2: Merge** | ❌ No | ❌ No | ❌ No | Set union (in-memory) |
| **3: Exact definition check** | ❌ No | ❌ No | ❌ No | Dict lookup (in-memory) |
| **4: Prompt assembly** | ❌ No | ❌ No | ❌ No | String concatenation |
| **5: Hybrid retrieval** | ✅ Yes | ✅ Yes | ❌ No | Vector for similarity, docstore for BM25 |
| **6: Reranking** | ❌ No | ❌ No | ❌ No | Re-scores already-retrieved nodes |
| **7: LLM synthesis** | ❌ No | ❌ No | ✅ Yes | Generates response from context |

---

## Performance Breakdown (Per Entity)

| Stage | Latency | Dominant Factor |
|-------|---------|-----------------|
| 1a: BM25 section routing | ~1-2s | 44 sections × BM25 scoring |
| 1b: LLM alias expansion | ~5-7s (only if 1a fails) | LLM generation + BM25 retry |
| 1c: Keyword scan | ~0.5-1s | 44 sections × substring scan |
| 2: Merge | <10ms | Set union |
| 3: Exact definition check | <10ms | Dict lookup |
| 4: Prompt assembly | <10ms | String concatenation |
| 5: Hybrid retrieval | ~0.3-0.5s | 10 sections × hybrid retrieval |
| 6: Reranking | ~0.1-0.2s | Cosine similarity computation |
| 7: LLM synthesis | ~60-90s | Ollama generation (qwen3.5:9b) |
| **Total** | **~65-100s** | **LLM dominates (>90%)** |

### Optimization Opportunities
| Stage | Current | Potential | Savings |
|-------|---------|-----------|---------|
| 1a: BM25 | ~1-2s | Cache section scores | ~0.5-1s |
| 5: Hybrid | ~0.3-0.5s | Reduce `per_collection_k` | ~0.1-0.2s |
| 7: LLM | ~60-90s | Use `prompt_gov_only` (30% of entities) | ~20-30s |

---

## Debugging Guide

### Run Diagnostic Tool
```bash
uv run python -m elt_llm_consumer.rag_retriever \
    --entity "Sports Governing Body" \
    --stage all \
    --ranker all
```

### Output Files
- `.tmp/rag_retriever_retrieval_{entity}.txt` — Stage 1-2 results
- `.tmp/rag_retriever_ranking_{ranker}_{entity}.txt` — Stage 6 ranked results
- `.tmp/rag_retriever_summary_{entity}.txt` — Keyword chunk summary

### Common Issues

#### Issue: No sections found in Stage 1a
**Symptom**: `Sections found: 0`
**Cause**: Entity not in `entity_aliases.yaml`, BM25 can't find matches
**Fix**: Add aliases to YAML or wait for Stage 1b LLM expansion

#### Issue: Keyword chunks empty
**Symptom**: `Chunks: 0`
**Cause**: Entity name not verbatim in handbook (uses alias instead)
**Fix**: Check `entity_aliases.yaml` — add canonical handbook term

#### Issue: LLM response empty or hallucinated
**Symptom**: `formal_definition: ""` or generic text
**Cause**: Retrieved chunks don't contain entity (Stage 1/5 failure)
**Fix**: Check `.tmp/rag_retriever_summary_{entity}.txt` — are keyword chunks present? Is `_extract_around_mention` working?

#### Issue: Slow performance (>120s per entity)
**Symptom**: Each entity takes 2+ minutes
**Cause**: LLM model too slow, or too many sections in unified_collections
**Fix**: 
- Use faster model (qwen3.5:9b → qwen3.5:3b for draft runs)
- Reduce `reranker_retrieve_k` in rag_config.yaml
- Check if `full_context_max_chunks` is too high (loading entire sections)

---

## Testing Checklist

- [ ] Stage 1a finds expected sections (check BM25 scores)
- [ ] Stage 1c finds keyword chunks (check verbatim matches)
- [ ] Stage 2 merge includes both BM25 + keyword sections
- [ ] Stage 3 exact definition found (if applicable)
- [ ] Stage 4 prompt includes keyword_suffix (check logs)
- [ ] Stage 5 retrieval returns candidate pool (check node count)
- [ ] Stage 6 reranking improves scores (check score distribution)
- [ ] Stage 7 LLM response is structured (check regex parse)

---

## Related Documents
- [ARCHITECTURE.md](ARCHITECTURE.md) — High-level system overview
- [RAG_STRATEGY.md](RAG_STRATEGY.md) — Retrieval strategy details
- [RAG_TUNING.md](RAG_TUNING.md) — Parameter tuning guide
- [elt_llm_consumer/ARCHITECTURE.md](elt_llm_consumer/ARCHITECTURE.md) — Consumer layer pipeline
- [CHROMADB_VECTORSTORE_VS_DOCSTORE.md](.tmp/CHROMADB_VECTORSTORE_VS_DOCSTORE.md) — Storage system deep dive
- [RAG_FLOW_EXPLAINED.md](.tmp/RAG_FLOW_EXPLAINED.md) — Entity query flow walkthrough
