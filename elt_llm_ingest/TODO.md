# elt_llm_ingest — Improvement Backlog

Items identified during agentic RAG comparison work (2026-03-15).

---

## Medium Priority

### LLM metadata extraction (enrichment pass, not agentic)
Chunks currently carry structural metadata (collection, page, chunk_type). Adding entity mentions, rule references (`Rule E1`, `Section 40`), and topic tags at ingest time would improve BM25 routing precision at retrieval time without changing the retrieval architecture.
- **Fix**: add an optional post-processing step after chunking that runs a lightweight LLM over each chunk to extract and store metadata tags into the docstore/ChromaDB metadata dict.
- **Note**: this is a one-pass enrichment — no loop or iteration; not agentic.
- **Scope**: FA Handbook pipeline only to start (`ingest_fa_handbook.yaml`).

---

## Low Priority / Nice-to-have

### Parent-child chunking
Current chunking is flat (512-token prose/table nodes). A parent-child structure — small chunks for retrieval, larger parent windows passed to LLM synthesis — could improve precision without sacrificing recall.
- **Consideration**: requires LlamaIndex `ParentChildNodeParser` or equivalent; storage overhead in docstore.

### Re-ingestion detection
No mechanism to detect whether a source document has changed since last ingestion. Currently requires a full re-ingest manually.
- **Fix**: store a content hash (e.g. SHA256 of source file) in collection metadata at ingest time; compare on subsequent runs to skip unchanged sources.
