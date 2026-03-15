# elt_llm_agentic — Improvement Backlog

---

## High Priority

### Create `elt_llm_retriever` — unified single codebase
Replace both `elt_llm_consumer` and `elt_llm_agentic` with a single `elt_llm_retriever` package.

**What moves in:**
- From `elt_llm_agentic`: `AgenticRetriever`, `RetrieverConfig`, `quality_gate`, `memory`, `graph_traversal`, `chat`
- From `elt_llm_consumer`: `fa_coverage_validator`, `fa_handbook_model_builder`, `fa_leanix_model_validate`, all shared utils (`_normalize`, `_get_alias_variants`, `_has_real_definition`, `load_entities_from_json`, etc.)
- New: unified `fa_catalog.py` — quality-gated Step 5 replacing both `fa_consolidated_catalog.py` and `fa_agentic_catalog.py`

**The unified catalog Step 5** — instead of choosing naive or agentic upfront:
1. Run `quality_gated_query()` per entity (fast naive RAG first)
2. If quality passes → use fast result (Tier 1 easy entities, Tier 3 genuinely absent)
3. If quality fails → `AgenticRetriever` fallback (Tier 2 sparse/alias-heavy entities)
4. Output includes `retrieval_path: "fast" | "agentic"` field so you can see which entities needed deep retrieval

**Sequence:**
1. Validate full PARTY run from `elt_llm_agentic` first
2. Create `elt_llm_retriever` as a new workspace package
3. Move code progressively, keeping consumer and agentic alive until retriever is verified
4. Drop `elt_llm_consumer` and `elt_llm_agentic` once full run from retriever matches or beats agentic catalog output

---

## Medium Priority

### Wire quality gate into `fa_agentic_catalog.py` Step 5 (interim)
Currently Step 5 calls `AgenticRetriever` for every entity. `quality_gate.py` exists but isn't used
in the batch catalog. Wiring it in would make the full run faster while keeping quality high.
- **Note:** Only worth doing as an interim fix if `elt_llm_retriever` creation is delayed.

### Section routing cache across iterations
`_route_sections` runs BM25 routing fresh each iteration. Caching the section list from iter 1
and reusing for subsequent RETRIEVE actions (when the LLM doesn't specify explicit sections)
would save 1–2s per iteration without changing retrieval quality.

---

## Already Fixed (reference)

- Household source classification bug: `_NO_HANDBOOK_COVERAGE` entities now force `LEANIX_ONLY` in Step 7
- Iter 1 query: changed from bare entity name to structured governance question for better semantic recall
- KEYWORD guard: premature DONE now intercepted when iter 1 returns only boilerplate — forces KEYWORD scan before allowing DONE
- `_is_boilerplate()`: detects generic negative responses so the KEYWORD guard fires correctly even when `has_content=True`
- All `__file__`-relative path fixes: `rag_config_path` resolved correctly regardless of working directory
