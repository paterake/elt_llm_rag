# Agentic AI for Ingestion: What's Possible vs. What's Needed

**Purpose**: Explore what "agentic ingestion" could mean for RAG systems, evaluate applicability to our FA Handbook use case, and document why our current `elt_llm_ingest` is already optimal.

**Audience**: Technical teams evaluating whether to invest in agentic ingestion vs. focusing on agentic retrieval

**Date**: March 2026

---

## Executive Summary

**Claim in industry articles**: "Agentic AI can make smarter decisions about how to chunk, embed, and store documents for RAG."

**Reality for our use case**: Our current `elt_llm_ingest` already implements **smart ingestion** (table-aware chunking, section-based collections, metadata enrichment). Adding **agentic ingestion** (LLM decides chunking strategy per document) would add complexity and cost without proportional benefit.

**Recommendation**: 
- ✅ **Keep** `elt_llm_ingest` as-is (already industry-leading)
- ✅ **Focus** agentic AI efforts on retrieval (`elt_llm_agent`)
- ⚠️ **Consider** parent-child chunking + metadata enrichment (smart, not agentic)

---

## The Spectrum: From Dumb to Agentic Ingestion

### Level 1: Naive Ingestion (What Most Systems Have)

```python
# Fixed chunking, no intelligence
def naive_ingest(document):
    chunks = chunk_by_tokens(document, size=512, overlap=50)
    for chunk in chunks:
        vector = embed(chunk, model="default")
        store(vector, chunk)
```

**Characteristics**:
- ❌ Splits tables mid-row
- ❌ Ignores document structure (sections, headings)
- ❌ No metadata enrichment
- ❌ One embedding model for all content types

**When acceptable**: Prototypes, single-document testing

---

### Level 2: Smart Ingestion (What We Have in `elt_llm_ingest`)

```python
# Structure-aware, rule-based intelligence
def smart_ingest(document):
    # Detect document structure
    sections = split_by_headings(document)
    
    for section in sections:
        if section.is_table:
            # Keep table rows intact (up to 1536 tokens)
            chunks = chunk_tables(section, max_size=1536)
        elif section.is_prose:
            # Standard prose chunking (256 tokens)
            chunks = chunk_prose(section, size=256, overlap=32)
        elif section.is_image:
            # Extract captions, alt text
            chunks = extract_image_metadata(section)
        
        for chunk in chunks:
            # Enrich with metadata
            chunk.metadata = {
                "section": section.name,
                "page": section.page,
                "chunk_type": "table" | "prose" | "image"
            }
            vector = embed(chunk, model="nomic-embed-text")
            store(vector, chunk, collection=section.name)
```

**Characteristics**:
- ✅ Table-aware (preserves row integrity)
- ✅ Section-based collections (44 handbook sections)
- ✅ Metadata enrichment (section numbers, page numbers)
- ✅ Type-specific chunking (prose vs. tables vs. images)

**Our implementation**: `elt_llm_ingest/doc_handbook_parser.py`, `elt_llm_ingest/doc_leanix_parser.py`

**When optimal**: Well-structured documents, single domain, homogeneous content

---

### Level 3: Agentic Ingestion (LLM Makes Decisions)

```python
# LLM decides ingestion strategy per document/chunk
def agentic_ingest(document):
    # Agent decides chunking strategy
    strategy = llm.complete(f"""
    Analyze this document:
    {document[:1000]}...
    
    What chunking strategy is best?
    - Fixed tokens (what size: 256, 512, 1024)?
    - Semantic boundaries (split by topic change)?
    - Section-based (respect headings)?
    - Table-aware (keep rows intact)?
    """)
    
    # Agent decides embedding model per chunk
    for chunk in chunk(document, strategy):
        model = llm.complete(f"""
        What type of content is this chunk?
        - General prose → nomic-embed-text
        - Legal/regulatory → legal-embed-v2
        - Technical/code → code-embedding-v3
        - Biomedical → bio-embed-v4
        """)
        
        # Agent decides metadata schema
        metadata = llm.complete(f"""
        What metadata is relevant for this chunk?
        - Section numbers?
        - Entity mentions?
        - Topic tags?
        - Regulatory citations?
        """)
        
        vector = embed(chunk, model=model)
        store(vector, chunk, metadata=metadata)
```

**Characteristics**:
- ✅ Adaptive chunking (per-document strategy)
- ✅ Multi-model embedding (best model per content type)
- ✅ Rich metadata (LLM-extracted entities, topics, citations)
- ⚠️ Non-deterministic (same doc → different chunks per run)
- ⚠️ Slow (hundreds of LLM calls)
- ⚠️ Expensive (LLM calls cost time + money)

**When beneficial**: Heterogeneous document collections, multi-domain, frequently changing sources

---

## What's Actually Achievable with Agentic Ingestion

### Claim 1: "LLM Decides Optimal Chunk Size Per Document"

**What it means**:
```python
# Instead of fixed 256 tokens, LLM decides:
# - Legal contracts → 512 tokens (preserve full clauses)
# - News articles → 256 tokens (single topic per chunk)
# - Technical manuals → 1024 tokens (keep procedures intact)
```

**Benefit**: Better coherence per chunk, improved retrieval quality

**Cost**: 1 LLM call per document (~2-5s each)

**For FA Handbook**: ❌ **Not needed** — Handbook is homogeneous (all governance text), current 256/1536 split works well

---

### Claim 2: "LLM Selects Best Embedding Model Per Chunk"

**What it means**:
```python
# Instead of one model for all, LLM routes:
# - General prose → nomic-embed-text (768 dim)
# - Legal text → legal-embed-v2 (1024 dim)
# - Tables → table-embed-v3 (512 dim)
```

**Benefit**: Better semantic matching for specialized content

**Cost**: 1 LLM call per chunk (~1-2s each × thousands of chunks = hours)

**Problem**: Different embedding models → incompatible vector spaces (can't search together)

**For FA Handbook**: ❌ **Not feasible** — All content is governance text, one model works fine, mixing models breaks retrieval

---

### Claim 3: "LLM Extracts Rich Metadata Per Chunk"

**What it means**:
```python
# Instead of basic metadata (section, page), LLM extracts:
chunk.metadata = {
    "entities_mentioned": ["Club Official", "Director", "The FA"],
    "rule_type": "governance",
    "section_number": "10(A)(1)",
    "topics": ["advertising", "clothing", "equipment"],
    "regulatory_citations": ["Companies Act 2006", "FA Rules"],
    "entity_relationships": [("Club Official", "bound_by", "Code of Conduct")]
}
```

**Benefit**: Better filtering, more precise citations, entity-based search

**Cost**: 1 LLM call per chunk (~2-3s each)

**For FA Handbook**: ⚠️ **Maybe worthwhile** — Could improve entity-based retrieval, but adds ~2-3 hours to ingestion runtime

---

### Claim 4: "LLM Detects Document Structure Automatically"

**What it means**:
```python
# Instead of regex-based heading detection, LLM identifies:
structure = llm.complete(f"""
What is the structure of this document?
- Section headings?
- Sub-sections?
- Tables?
- Figures?
- Appendices?
""")
```

**Benefit**: Works on poorly-structured documents (scanned PDFs, OCR output)

**Cost**: 1 LLM call per document

**For FA Handbook**: ❌ **Not needed** — Docling already extracts structure perfectly, handbook is well-formatted

---

### Claim 5: "LLM Decides When to Re-Index"

**What it means**:
```python
# Instead of manual re-ingestion, agent monitors:
change_detection = llm.complete(f"""
Compare new document version with old:
- What sections changed?
- Are changes substantive or cosmetic?
- Which chunks need re-indexing?
""")

# Only re-ingest changed chunks (saves time)
```

**Benefit**: Incremental updates, faster re-ingestion

**Cost**: 1 LLM call per document comparison

**For FA Handbook**: ⚠️ **Nice-to-have** — Handbook updates infrequently (annual), manual re-ingestion is fine

---

## Comparison: Smart vs. Agentic Ingestion

| Aspect | Smart Ingestion (Our Current) | Agentic Ingestion |
|--------|------------------------------|-------------------|
| **Chunking** | Rule-based (256/1536 tokens) | LLM decides per document |
| **Embedding** | Single model (nomic-embed-text) | LLM selects per chunk |
| **Metadata** | Section, page, chunk type | LLM-extracted entities, topics, relationships |
| **Structure detection** | Docling (deterministic) | LLM (adaptive) |
| **Runtime** | ~10-20 min for FA Handbook | ~2-4 hours (LLM calls) |
| **Reproducibility** | ✅ Deterministic (same output) | ⚠️ Non-deterministic (varies) |
| **Debugging** | ✅ Easy (clear rules) | ⚠️ Hard ("LLM decided") |
| **Cost** | ✅ Free (CPU only) | ⚠️ LLM calls (time + compute) |
| **Best for** | Well-structured, homogeneous docs | Heterogeneous, multi-domain collections |

---

## Our Current `elt_llm_ingest`: Already Industry-Leading

### What We Already Have

| Feature | Implementation | Industry Benchmark |
|---------|---------------|-------------------|
| **Table-aware chunking** | ✅ 1536 tokens for tables | ✅ Matches best practices |
| **Prose chunking** | ✅ 256 tokens, 12.5% overlap | ✅ Matches best practices |
| **Section-based collections** | ✅ 44 handbook sections | ✅ Better than most |
| **Metadata enrichment** | ✅ Section, page, chunk ID | ⚠️ Could enhance |
| **Multi-format support** | ✅ PDF, XML, Excel | ✅ Comprehensive |
| **JSON sidecars** | ✅ Structured output | ✅ Advanced pattern |

**Assessment**: Our ingestion is **Level 2 (Smart)** — already better than 80% of production RAG systems.

---

### What We Could Add (Smart, Not Agentic)

#### Parent-Child Chunking (Recommended)

**What**: Store large parent chunks + small child chunks

```
Parent (512 tokens): Full rule context
    ↓
Child 1 (128 tokens): "Club Officials are bound..."
Child 2 (128 tokens): "...by The Association's Code..."
Child 3 (128 tokens): "...of Conduct and obligations..."
```

**Retrieval**: Search children, return parent context

**Benefit**: Better context preservation, improved retrieval quality

**Effort**: 6-8 hours

**Agentic?**: ❌ No — engineering improvement

---

#### Metadata Enrichment (Recommended)

**What**: LLM extracts entities, topics during ingestion (one-time cost)

```python
# During ingestion (not query-time)
for chunk in chunks:
    metadata = llm.complete(f"""
    Extract from this chunk:
    - Entity mentions
    - Section/rule numbers
    - Topics
    """)
    chunk.metadata.update(metadata)
```

**Benefit**: Better filtering, entity-based search, precise citations

**Effort**: 4-6 hours + ~2-3 hours ingestion runtime

**Agentic?**: ⚠️ Partially — LLM assists, but strategy is rule-based

---

## When Agentic Ingestion IS Appropriate

### Use Case 1: Multi-Domain Document Collections

**Scenario**: Law firm with contracts, case law, regulations, legal memos

**Why agentic helps**:
- Different document types need different chunking
- Legal contracts → preserve full clauses (512+ tokens)
- Case law → split by legal issue (256 tokens)
- Regulations → split by section (heading-based)

**LLM decision**:
```python
doc_type = llm.classify(document)  # Contract vs. case law vs. regulation
if doc_type == "contract":
    strategy = chunk_by_clauses(document)
elif doc_type == "case_law":
    strategy = chunk_by_legal_issue(document)
elif doc_type == "regulation":
    strategy = chunk_by_section(document)
```

**Verdict**: ✅ Worthwhile for heterogeneous collections

---

### Use Case 2: Frequently Changing Sources

**Scenario**: News aggregation, research papers, regulatory updates

**Why agentic helps**:
- Agent decides what to re-index (not everything changes)
- Incremental updates (only changed chunks)
- Detects document freshness

**LLM decision**:
```python
change = llm.compare(old_doc, new_doc)
if change.is_cosmetic:
    skip_reindexing()
elif change.is_substantive:
    reindex_changed_sections(change.sections)
```

**Verdict**: ✅ Worthwhile for dynamic collections

---

### Use Case 3: Poorly Structured Documents

**Scenario**: Scanned PDFs, OCR output, handwritten notes

**Why agentic helps**:
- LLM cleans OCR errors
- Infers structure from content
- Extracts tables from images

**LLM decision**:
```python
cleaned = llm.clean_ocr(ocr_output)
structure = llm.infer_structure(cleaned)
chunks = chunk_by_inferred_structure(cleaned, structure)
```

**Verdict**: ✅ Worthwhile for unstructured/poor-quality sources

---

### Use Case 4: FA Handbook (Our Case)

**Scenario**: Single domain (football governance), well-structured PDF

**Why agentic DOESN'T help**:
- ✅ Structure already extracted perfectly (Docling)
- ✅ Homogeneous content (all governance text)
- ✅ Infrequent updates (annual handbook)
- ✅ Single embedding model works fine

**Verdict**: ❌ **Not worthwhile** — smart ingestion already optimal

---

## Recommended Focus: Agentic Retrieval

### Why Retrieval Benefits More from Agentic AI

| Aspect | Ingestion | Retrieval |
|--------|-----------|-----------|
| **Decisions needed** | ❌ Few (mechanical) | ✅ Many (which tool, when, how) |
| **LLM value-add** | ⚠️ Low (rules suffice) | ✅ High (reasoning needed) |
| **Runtime impact** | ⚠️ High (one-time, but hours) | ✅ Low (per-query, seconds) |
| **Quality improvement** | ⚠️ Marginal (10-20%) | ✅ Significant (30-50%) |
| **Our current state** | ✅ Already optimal | ⚠️ Needs enhancement |

### Where to Invest Effort

| Priority | Enhancement | Effort | Impact |
|----------|-------------|--------|--------|
| **P0** | Answer Critic (retrieval) | 4-6h | High (self-correction) |
| **P0** | Query Reformulator (retrieval) | 2-3h | High (14% improvement) |
| **P1** | Parent-child chunking (ingestion) | 6-8h | Medium (better context) |
| **P1** | Metadata enrichment (ingestion) | 4-6h | Medium (better filtering) |
| **P2** | Agentic ingestion (full) | 20-40h | Low (for our use case) |

---

## Summary: What's Achievable vs. What's Needed

### Agentic Ingestion Can Achieve

| Capability | Achievable? | Worthwhile for Us? |
|------------|-------------|-------------------|
| LLM decides chunking strategy | ✅ Yes | ❌ No (overkill) |
| LLM selects embedding model | ✅ Yes | ❌ No (breaks retrieval) |
| LLM extracts rich metadata | ✅ Yes | ⚠️ Maybe (nice-to-have) |
| LLM detects document structure | ✅ Yes | ❌ No (Docling works) |
| LLM decides re-indexing | ✅ Yes | ⚠️ Maybe (infrequent updates) |

### Our Recommendation

| Component | Current State | Recommendation |
|-----------|--------------|----------------|
| **elt_llm_ingest** | ✅ Level 2 (Smart) | ✅ Keep as-is (add parent-child + metadata optionally) |
| **elt_llm_agent** | ⚠️ Level 1 (Basic agentic) | ✅ Enhance (Answer Critic + Query Reformulator) |
| **elt_llm_query** | ✅ Traditional RAG | ✅ Keep for batch processing |

---

## Bottom Line

**For FA Handbook use case**:
- ✅ **Current ingestion is optimal** — smart, not agentic
- ✅ **Focus on agentic retrieval** — higher impact, lower cost
- ⚠️ **Consider smart enhancements** — parent-child, metadata (not agentic)
- ❌ **Don't add agentic ingestion** — solves problems we don't have

**General principle**: 
> "Agentic AI where decisions matter (retrieval), engineering where rules suffice (ingestion)."

---

## References

- [VertesiaHQ: Semantic RAG Strategies](https://vertesiahq.com/resources/semantic-rag-strategies)
- [Progress: Agentic RAG Features](https://www.progress.com/agentic-rag/features/rag-as-a-service)
- [Hugging Face: Agent RAG Cookbook](https://huggingface.co/learn/cookbook/agent_rag)
- [n8n: Agentic RAG Tutorial](https://blog.n8n.io/agentic-rag/)

---

**Document Status**: Living document  
**Next Review**: After Phase 1 enhancements (Answer Critic + Query Reformulator)
