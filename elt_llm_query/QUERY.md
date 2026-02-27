# RAG Query Examples

All example queries are run from the **repository root**.

Pattern: `uv run python -m elt_llm_query.runner --cfg <profile> -q "question"`

For an interactive session drop the `-q` flag. See [README.md](README.md) for command reference and profile configuration.

---

## FA Enterprise Architecture (`fa_enterprise_architecture`)

All `fa_leanix_*` collections + `fa_handbook` + `fa_data_architecture`. The primary profile for FA architecture questions — combines the LeanIX conceptual model, global inventory, handbook governance content, and data architecture documentation.

```bash
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture

# Conceptual model structure
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture \
  -q "What are the 10 enterprise domains in the FA conceptual model?"

# Entity lookup + handbook cross-reference
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture \
  -q "What does the FA Handbook say about clubs and member organisations, and how do those map to the PARTY entities in the conceptual model?"

# Inventory — what applications and interfaces exist
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture \
  -q "What data interfaces does Workday have in the LeanIX inventory?"

# Gap analysis
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture \
  -q "Are there governance structures or roles described in the FA Handbook that don't appear as entities in the conceptual model?"

# Data flows
uv run python -m elt_llm_query.runner --cfg fa_enterprise_architecture \
  -q "How does data flow from Workday to Purview?"
```

**Expected:** Sources drawn from `fa_leanix_dat_enterprise_conceptual_model_*`, `fa_leanix_global_inventory_*`, `fa_handbook`, and `fa_data_architecture` collections.

---

## FA Handbook

### FA Handbook Only (`fa_handbook_only`)

```bash
uv run python -m elt_llm_query.runner --cfg fa_handbook_only

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

### DAMA + FA Handbook (`dama_fa_handbook`)

```bash
uv run python -m elt_llm_query.runner --cfg dama_fa_handbook

uv run python -m elt_llm_query.runner --cfg dama_fa_handbook \
  -q "How do the FA's governance committees map to the data governance roles described in DAMA-DMBOK?"

uv run python -m elt_llm_query.runner --cfg dama_fa_handbook \
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

- **Start with `fa_enterprise_architecture`** — covers LeanIX conceptual model + inventory + FA Handbook + data architecture in one profile
- **Check Sources** — the collection name in each source tells you which knowledge base the chunk came from
- **Increase `similarity_top_k`** in the profile YAML if you think relevant chunks are being cut off
- **Frame combined queries explicitly** — e.g. *"...and what does the FA Handbook say about..."* helps the retriever surface both sources
- **Interactive mode** for exploration, `-q` flag for reproducible validation runs
