# RAG Query Runners - Quick Reference

## List Available Configs

```bash
uv run python -m elt_llm_query.runner --list
```

---

## Query Single Collection

### DAMA-DMBOK2R Only

```bash
# Interactive mode
uv run python -m elt_llm_query.runner --cfg dama_only

# Single query
uv run python -m elt_llm_query.runner --cfg dama_only -q "What is data governance?"

# Verbose output
uv run python -m elt_llm_query.runner --cfg dama_only -v
```

### FA Handbook Only

```bash
# Interactive mode
uv run python -m elt_llm_query.runner --cfg fa_handbook_only

# Single query
uv run python -m elt_llm_query.runner --cfg fa_handbook_only -q "What are the key financial controls?"
```

---

## Query Multiple Collections

### DAMA + FA Handbook

```bash
# Interactive mode
uv run python -m elt_llm_query.runner --cfg dama_fa_combined

# Single query
uv run python -m elt_llm_query.runner --cfg dama_fa_combined -q "How does data governance relate to financial controls?"
```

### All Collections

```bash
# Interactive mode
uv run python -m elt_llm_query.runner --cfg all_collections

# Single query
uv run python -m elt_llm_query.runner --cfg all_collections -q "What are the best practices for governance?"
```

### Architecture Focus (SAD + LeanIX)

```bash
# Interactive mode
uv run python -m elt_llm_query.runner --cfg architecture_focus

# Single query
uv run python -m elt_llm_query.runner --cfg architecture_focus -q "What is the role of enterprise architecture?"
```

### Vendor Assessment (LeanIX + Supplier)

```bash
# Interactive mode
uv run python -m elt_llm_query.runner --cfg vendor_assessment

# Single query
uv run python -m elt_llm_query.runner --cfg vendor_assessment -q "How do we assess vendor risk?"
```

---

## Common Workflows

### Cross-Domain Question

```bash
# Question spanning data management and architecture
uv run python -m elt_llm_query.runner --cfg dama_fa_combined -q "How does data quality impact financial reporting?"
```

### Comprehensive Search

```bash
# Search across all available documentation
uv run python -m elt_llm_query.runner --cfg all_collections -q "What are the key governance frameworks?"
```

### Focused Investigation

```bash
# Architecture-specific question
uv run python -m elt_llm_query.runner --cfg architecture_focus -q "What is the TOGAF ADM?"
```

---

## Query Config Reference

| Config | Collections | Use Case |
|--------|-------------|----------|
| `dama_only` | DAMA-DMBOK | Data management questions |
| `fa_handbook_only` | FA Handbook | Financial accounting questions |
| `dama_fa_combined` | DAMA + FA | Cross-domain questions |
| `all_collections` | All | General queries |
| `architecture_focus` | SAD + LeanIX | Architecture questions |
| `vendor_assessment` | LeanIX + Supplier | Vendor evaluation |

---

## Tips

1. **Start with focused configs** for specific questions
2. **Use combined configs** for cross-domain questions
3. **Use `all_collections`** when you're not sure which doc has the answer
4. **Check sources** to verify which document the answer came from
