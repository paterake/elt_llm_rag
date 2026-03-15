# elt_llm_consumer — Improvement Backlog

Items identified during agentic RAG comparison work (2026-03-15).

---

## High Priority

### Step 4: Name-matching gap — short vs qualified entity names
Conceptual model uses short names ("Team", "Club"); FA Handbook uses qualified names ("Football team", "County FA Club"). The normalised string match in Step 4 misses these.
- **Fix**: add a curated alias map or fuzzy-match fallback in Step 4 to bridge short/qualified name gaps before Step 5 RAG runs.

---

## Medium Priority

### Step 3: Docling over-extraction of defined terms
`_DEF_PAT` / `_TABLE_DEF_PAT` matches ~433 terms vs expected ~141 — false positives dilute Step 4 match rate and inject noise into `term_definitions`.
- **Fix**: tighten regex patterns or add a post-filter (e.g. minimum word count, exclude page-header artefacts) to reduce false positives.

---

## Low Priority / Nice-to-have

### Parent-child chunking
Current chunking is flat (512-token prose/table nodes). A parent-child structure (small retrieval chunks referencing larger parent context windows) could improve precision without sacrificing recall.

### Quality gate integration
`elt_llm_agentic.quality_gate.quality_gated_query` implements fast-path naive RAG + agentic fallback. Consider whether consumer Step 5 should optionally use this gate for entities where the naive query returns a low-quality response, rather than always running the full RAG call.

---

## Already Fixed (reference)

- `no_handbook_coverage` was too aggressive — removed 5 entities (Supplier, Customer, Prospect, Event Attendee, Casual & Contingent Labourers) that alias-based retrieval CAN find content for. Only Household, Business Unit, Managed Service Workers remain excluded.
- Stage 1c keyword scan now iterates over all alias variants (not just entity name).
