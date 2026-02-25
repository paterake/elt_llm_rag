# LeanIX Preprocessor Output Review

## Summary

The LeanIX preprocessor successfully transforms XML diagram exports into **structured Markdown** suitable for RAG embedding.

---

## Test Results

### Input File
- **File**: `DAT_V00.01_FA Enterprise Conceptual Data Model.xml`
- **Size**: 120,994 bytes
- **Format**: LeanIX draw.io XML export

### Output Files Generated

| File | Size | Format | Purpose |
|------|------|--------|---------|
| `leanix_test_output.md` | 17,272 bytes | Markdown | **Primary output for embedding** |
| `leanix_test_output.json` | 179,552 bytes | JSON | Programmatic access |

---

## Extraction Statistics

```
Total Assets: 217
Total Relationships: 16
Asset Types: DataObject (217 items)
```

### Asset Categories (Groupings)

The preprocessor identified **13 conceptual groupings**:

1. **AGREEMENTS** (45 items) - Contracts, licenses, policies
2. **CAMPAIGN** (10 items) - Marketing campaigns, promotions
3. **LOCATION** (7 items) - Countries, venues, grounds
4. **PRODUCT** (47 items) - Services, tickets, merchandise
5. **REFERENCE DATA** (2 items) - Configuration data
6. **Static Data** (4 items) - Currency, ethnicity, etc.
7. **TRANSACTION AND EVENTS** (46 items) - Events, incidents, transactions
8. **Time Bounded Groupings** (3 items) - Seasons, phases
9. **PARTY** (68 items) - People, organizations, roles
10. **ACCOUNTS** (8 items) - User accounts, financial accounts
11. **ASSETS** (6 items) - Physical, digital, IP assets
12. **CHANNEL** (4 items) - Communication channels

---

## Output Structure

### Markdown Format (for RAG embedding)

```markdown
# LeanIX Enterprise Architecture Inventory
**Source:** DAT_V00.01_FA Enterprise Conceptual Data Model.xml
**Total Assets:** 217
**Total Relationships:** 16

## Assets by Type

### DataObject
*Count: 217*

#### AGREEMENTS
- **AGREEMENTS**
  - ID: `a74319ea-27d7-46b0-8791-305333f20498`
- **Advertising Agreements**
  - ID: `6713aaa2-264d-44f2-aa29-52339c141e1c`
- **Agent Agreements**
  - ID: `86947848-29bf-4eaf-a852-03dc8d611585`
...

## Relationships

### PARTY
- → **ACCOUNTS** [0..*-0..*]
  - Type: Entity Relationship
- → **AGREEMENTS** [0..*-0..*]
  - Type: Entity Relationship
...
```

### JSON Format (for programmatic access)

```json
{
  "metadata": {
    "source_file": "model.xml",
    "total_assets": 217,
    "total_relationships": 16,
    "asset_types": ["DataObject"]
  },
  "assets": [
    {
      "id": "asset-id",
      "label": "Asset Label",
      "fact_sheet_type": "DataObject",
      "fact_sheet_id": "leanix-id",
      "parent_group": "AGREEMENTS",
      ...
    }
  ],
  "relationships": [
    {
      "id": "rel-id",
      "source_id": "source-asset-id",
      "target_id": "target-asset-id",
      "source_label": "Source Label",
      "target_label": "Target Label",
      "relationship_type": "Entity Relationship",
      "cardinality": "0..*-0..*"
    }
  ]
}
```

---

## Why This Output is Suitable for RAG

### ✅ **Advantages**

1. **Structured Hierarchy**
   - Assets grouped by type and parent containers
   - Clear Markdown headings (`##`, `###`, `####`) create natural chunk boundaries
   - Embedding model can understand context from structure

2. **Semantic Richness**
   - Each asset includes: label, type, unique ID, parent grouping
   - Relationships explicitly documented with cardinality
   - Business context preserved (e.g., "Player Registration" under "AGREEMENTS")

3. **Clean Formatting**
   - HTML tags stripped from labels
   - Consistent bullet-point structure
   - Code-formatted IDs (`` `id` ``) for clarity

4. **Relationship Context**
   - Entity relationships explicitly listed
   - Cardinality notation (0..*-0..*) preserved
   - Source → Target directionality clear

5. **Chunking-Friendly**
   - 515 lines → will chunk into ~50-100 meaningful chunks
   - Each section self-contained
   - Headers provide natural split points

### 🎯 **RAG Use Cases Enabled**

With this embedded content, users can ask:

- "What types of agreements are in the data model?"
- "Show me all assets in the PARTY grouping"
- "What is the relationship between PARTY and AGREEMENTS?"
- "List all transaction and event types"
- "What assets are related to PLAYER?"

---

## Comparison: Raw XML vs Preprocessed Markdown

| Aspect | Raw XML | Preprocessed Markdown |
|--------|---------|----------------------|
| **Size** | 120,994 bytes | 17,272 bytes (86% smaller) |
| **Human Readable** | ❌ Complex XML structure | ✅ Clean Markdown |
| **Semantic Structure** | ❌ Hidden in XML attributes | ✅ Explicit headings & lists |
| **Relationships** | ❌ Encoded in edge references | ✅ Explicit source→target |
| **Embedding Quality** | ❌ Noisy with XML tags | ✅ Clean semantic text |
| **Chunking** | ❌ Arbitrary XML splits | ✅ Natural section boundaries |

---

## Recommended Embedding Strategy

### Chunking Configuration

```yaml
chunking:
  strategy: "sentence"
  chunk_size: 512
  chunk_overlap: 64
  sentence_split_threshold: 0.5
```

**Expected Results:**
- ~50-100 chunks (depending on chunk_size)
- Each chunk contains coherent business concepts
- Headers preserved in chunks for context

### Metadata to Preserve

```yaml
metadata:
  domain: "architecture"
  type: "enterprise_architecture"
  source: "LeanIX"
  asset_count: 217
  relationship_count: 16
```

---

## Sample Chunks (Expected)

### Chunk 1: Header + AGREEMENTS section
```
# LeanIX Enterprise Architecture Inventory
**Source:** DAT_V00.01_FA Enterprise Conceptual Data Model.xml
**Total Assets:** 217

## Assets by Type
### DataObject
#### AGREEMENTS
- **AGREEMENTS**
  - ID: `a74319ea-27d7-46b0-8791-305333f20498`
- **Advertising Agreements**
  - ID: `6713aaa2-264d-44f2-aa29-52339c141e1c`
...
```

### Chunk 2: PARTY section
```
#### PARTY
- **PARTY**
  - ID: `3a0936a7-887c-44a8-83cd-f9ad2b25df74`
- **Individual**
  - ID: `8327eab5-c6ba-4d8e-a4da-66bd8e22d500`
- **Organisation**
  - ID: `2d6c14ce-0e99-4645-a49c-2fee0bce556d`
...
```

### Chunk 3: Relationships
```
## Relationships

### PARTY
- → **ACCOUNTS** [0..*-0..*]
  - Type: Entity Relationship
- → **AGREEMENTS** [0..*-0..*]
  - Type: Entity Relationship
...
```

---

## Conclusion

**✅ RECOMMENDED FOR EMBEDDING**

The preprocessed Markdown output is **highly suitable** for RAG embedding because:

1. **Semantic clarity**: Business concepts clearly organized
2. **Structure**: Natural chunk boundaries from Markdown hierarchy
3. **Completeness**: All 217 assets + 16 relationships captured
4. **Searchability**: Labels, IDs, and relationships all text-searchable
5. **Context**: Parent groupings provide domain context

**Next Steps:**
1. Update `leanix.yaml` config with correct file path
2. Run ingestion: `uv run python -m elt_llm_ingest.runner --cfg leanix`
3. Test queries against embedded content
4. Validate retrieval quality with sample questions

---

## Files for Review

| File | Location |
|------|----------|
| Sample Markdown Output | `elt_llm_ingest/leanix_output_sample.md` |
| Test Script | `elt_llm_ingest/test_leanix_preprocessor.py` |
| Preprocessor Code | `elt_llm_ingest/src/elt_llm_ingest/preprocessor.py` |
| Parser Code | `elt_llm_ingest/src/elt_llm_ingest/doc_leanix_parser.py` |
