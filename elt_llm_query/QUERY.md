# RAG Query Examples

All example queries are run from the **repository root**.

Pattern: `uv run python -m elt_llm_query.runner --cfg <profile> -q "question"`

For an interactive session drop the `-q` flag. See [README.md](README.md) for command reference and profile configuration.

---

## LeanIX — Validating Partitioned Retrieval

The LeanIX conceptual model is ingested as **11 separate ChromaDB collections** (one per domain, plus a dedicated relationships collection). The queries below confirm that the partition routing is working correctly — check the Sources section of each response to verify chunks are coming from the expected collection.

### 1. Relationships (`leanix_relationships`)

Profile targets `fa_leanix_relationships` + `fa_leanix_overview` only. The relationships collection holds 4 self-contained chunks covering all 16 domain-level relationships. A pre-partitioning bug caused chunking to split the relationship list, so some were missed; these queries confirm that is fixed.

```bash
# Full list — should return all 16 relationships with cardinalities
uv run python -m elt_llm_query.runner --cfg leanix_relationships \
  -q "What are all the relationships in the FA Enterprise Conceptual Data Model? List each one with its cardinality."

# Point query — specific relationship between two domains
uv run python -m elt_llm_query.runner --cfg leanix_relationships \
  -q "How does PARTY relate to AGREEMENTS? What is the cardinality?"

# Fan-out query — all domains connecting to a given domain
uv run python -m elt_llm_query.runner --cfg leanix_relationships \
  -q "Which domains have a relationship with TRANSACTION AND EVENTS?"

# Self-referential — PARTY → PARTY
uv run python -m elt_llm_query.runner --cfg leanix_relationships \
  -q "Is there a relationship between PARTY and itself?"
```

**Expected:** Sources come from `fa_leanix_relationships`. Full-list query returns all 16.

---

### 2. Domain Entities (`leanix_only`)

Profile uses `collection_prefixes: fa_leanix` to expand to all `fa_leanix_*` collections at runtime. Domain-specific questions should retrieve from the matching per-domain collection, not from the relationships collection.

```bash
# AGREEMENTS domain (42 entities) → fa_leanix_agreements
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "What entities are in the AGREEMENTS domain of the FA conceptual model?"

# PRODUCT domain (42 entities) → fa_leanix_product
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "List all entities in the PRODUCT domain."

# Party types, channel types, accounts, assets → fa_leanix_additional_entities
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "What party types are defined in the FA conceptual model? List them all."

# Model summary (217 entities, 8 domain groups) → fa_leanix_overview
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "How many entities and domains are in the FA Enterprise Conceptual Data Model?"

# TRANSACTION AND EVENTS domain → fa_leanix_transaction_and_events
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "What events and transactions does the model track?"

# CAMPAIGN domain → fa_leanix_campaign
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "What campaign-related entities are in the model?"

# LOCATION domain → fa_leanix_location
uv run python -m elt_llm_query.runner --cfg leanix_only \
  -q "What location entities are defined in the FA conceptual model?"
```

**Expected:** Each query sources from the matching domain collection. Entity lists are complete (pre-partitioning these were often truncated mid-chunk).

---

### 3. Handbook Enrichment (`leanix_fa_combined`)

Profile combines all `fa_leanix_*` with `fa_handbook`. Responses should draw from both sources — check the Sources section for at least one `fa_handbook` chunk alongside LeanIX chunks.

```bash
# Agreements domain + Handbook legal definitions for player agreements
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined \
  -q "The conceptual model has an AGREEMENTS domain. What rules does the FA Handbook define around player registration or transfer agreements that would map to those entities?"

# Party types in the model vs Handbook description of clubs and members
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined \
  -q "What does the FA Handbook say about clubs and member organisations, and how do those map to the PARTY entities in the conceptual model?"

# Gap analysis — Handbook concepts not in the model
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined \
  -q "Are there governance structures or roles described in the FA Handbook that don't appear as entities in the conceptual model?"

# Competition structures in Handbook vs Transaction/Events domain
uv run python -m elt_llm_query.runner --cfg leanix_fa_combined \
  -q "How do the competition structures described in the FA Handbook relate to the TRANSACTION AND EVENTS domain in the conceptual model?"
```

**Expected:** Sources include at least one `fa_handbook` chunk. LLM response attributes claims to the correct source.

---

## FA Handbook

### FA Handbook Only (`fa_handbook_only`)

```bash
uv run python -m elt_llm_query.runner --cfg fa_handbook_only

# Example queries
uv run python -m elt_llm_query.runner --cfg fa_handbook_only \
  -q "What are the FA's rules around player eligibility?"

uv run python -m elt_llm_query.runner --cfg fa_handbook_only \
  -q "What committees does the FA have and what are their responsibilities?"

uv run python -m elt_llm_query.runner --cfg fa_handbook_only \
  -q "What are the registration rules for clubs?"
```

---

## DAMA-DMBOK

### DAMA Only (`dama_only`)

```bash
uv run python -m elt_llm_query.runner --cfg dama_only

# Example queries
uv run python -m elt_llm_query.runner --cfg dama_only \
  -q "What is data governance and what are its key components?"

uv run python -m elt_llm_query.runner --cfg dama_only \
  -q "What are the DAMA-DMBOK knowledge areas?"

uv run python -m elt_llm_query.runner --cfg dama_only \
  -q "How does DAMA define master data management?"

uv run python -m elt_llm_query.runner --cfg dama_only \
  -q "What data quality dimensions does DAMA-DMBOK define?"
```

---

## Combined Sources

### DAMA + FA Handbook (`dama_fa_combined`)

```bash
uv run python -m elt_llm_query.runner --cfg dama_fa_combined

uv run python -m elt_llm_query.runner --cfg dama_fa_combined \
  -q "How do the FA's governance committees map to the data governance roles described in DAMA-DMBOK?"

uv run python -m elt_llm_query.runner --cfg dama_fa_combined \
  -q "How does data quality impact the FA's player registration process?"
```

### Full Data Management Programme (`fa_data_management`)

All `fa_leanix_*` + `fa_handbook` + `fa_data_architecture` + `dama_dmbok`. Use for programme-level questions spanning all four sources.

```bash
uv run python -m elt_llm_query.runner --cfg fa_data_management

# Governance mapping
uv run python -m elt_llm_query.runner --cfg fa_data_management \
  -q "How do the FA governance committees described in the Handbook map to the data governance roles defined in DAMA-DMBOK?"

# MDM strategy grounded in the conceptual model
uv run python -m elt_llm_query.runner --cfg fa_data_management \
  -q "Which entities in the FA conceptual model are the strongest candidates for a Master Data Management programme, and why?"

# Data quality framing per domain
uv run python -m elt_llm_query.runner --cfg fa_data_management \
  -q "For the PARTY domain entities, what data quality dimensions from DAMA-DMBOK should we apply, and what FA Handbook rules would drive those quality rules?"

# Business glossary
uv run python -m elt_llm_query.runner --cfg fa_data_management \
  -q "Define 'Club' as a data entity — draw on the LeanIX model, the FA Handbook definition, and any DAMA master data guidance."

# Metadata management
uv run python -m elt_llm_query.runner --cfg fa_data_management \
  -q "What metadata should we capture for the AGREEMENTS domain entities, grounded in DAMA-DMBOK metadata management guidance?"
```

### DAMA + Handbook + Data Architecture + Key LeanIX (`dama_fa_full`)

```bash
uv run python -m elt_llm_query.runner --cfg dama_fa_full

uv run python -m elt_llm_query.runner --cfg dama_fa_full \
  -q "How does the FA reference data architecture align with DAMA-DMBOK data architecture best practices?"

uv run python -m elt_llm_query.runner --cfg dama_fa_full \
  -q "What are the key data integration patterns recommended by DAMA, and how do they apply to the FA's conceptual model?"
```

### All Collections (`all_collections`)

Broadest search across everything ingested.

```bash
uv run python -m elt_llm_query.runner --cfg all_collections

uv run python -m elt_llm_query.runner --cfg all_collections \
  -q "What are the key governance frameworks across all sources?"

uv run python -m elt_llm_query.runner --cfg all_collections \
  -q "Summarise what each source says about data quality."
```

---

## Tips

- **Start narrow** — use `leanix_relationships` or a single-collection profile before going broad
- **Check Sources** — the collection name in each source tells you whether the partition routing worked correctly
- **Increase `similarity_top_k`** in the profile YAML if you think relevant chunks are being cut off
- **Frame combined queries explicitly** — e.g. *"...and what does the FA Handbook say about..."* helps the retriever surface both sources when using `leanix_fa_combined`
- **Interactive mode** for exploration, `-q` flag for reproducible validation runs
