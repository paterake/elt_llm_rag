# Gap Analysis: LeanIX + FA Handbook vs. The Ask

**Date**: 27 February 2026  
**Sources Available**:
- ✅ LeanIX Conceptual Model (draw.io XML) — ingested into RAG
- ✅ LeanIX Full Inventory Export (Excel) — exported to CSV
- ✅ FA Handbook (PDF) — ingested into RAG
- ❌ FDM (Functional Data Model) — **NOT YET PROVIDED**
- ❌ Integrations documentation — **PARTIAL** (only Interface descriptions)

---

## The Ask — Line by Line Analysis

### ✅ Ask 1: *"we need to do something around the FDM and glossary / cataloguing on the meta"*

**What you need**:
| Component | Status | Source | Gap |
|-----------|--------|--------|-----|
| **Glossary** | 🟡 Partial | LeanIX (130 definitions) + FA Handbook (ingested) | Need to LINK them together |
| **Catalogue** | 🔴 Missing | — | Need to BUILD (Purview or custom) |
| **FDM** | ❌ Not provided | — | **You don't have the FDM yet** |

**Verdict**: 
- ✅ Glossary: **80% achievable** (need FAGlossaryPreprocessor to link FA Handbook → LeanIX)
- 🔴 FDM: **BLOCKED** — you need the FDM file (Excel/PDF)
- 🔴 Catalogue: **BLOCKED** — need Purview integration or manual catalogue build

**What to ask**:
> "Where is the FDM stored? Can you share the Excel/PDF file?"

---

### ✅ Ask 2: *"both on what is held/owned and what is transmitted to and from"*

**What you need**:
| Question | Source | Status | Gap |
|----------|--------|--------|-----|
| **What is HELD?** (entities) | LeanIX DataObjects | ✅ 229 entities | Need attribute-level detail |
| **What is HELD?** (systems) | LeanIX Applications | ✅ 215 systems | — |
| **What is OWNED?** (stewards) | LeanIX Organizations | ⚠️ 115 orgs | ❌ No mapping DataObject → Owner |
| **What is TRANSMITTED?** | LeanIX Interfaces | ✅ 271 interfaces | ❌ No mapping: which DataObject flows where |

**Verdict**: 
- ✅ **HELD**: You have 229 DataObjects + 215 Applications
- 🔴 **OWNED**: Missing DataObject → Organization mapping
- 🟡 **TRANSMITTED**: You have 271 interfaces but don't know WHICH entities flow

**What to ask**:
```
□ "Which DataObject does each Interface transmit?"
  (e.g., Interface "Workday → Purview" transmits PARTY, AGREEMENTS, etc.)

□ "Who owns each DataObject?"
  (Data Owner, Data Steward assignments)

□ "Which applications hold/use each DataObject?"
  (DataObject → Application relationships)
```

---

### ✅ Ask 3: *"I need to generate the glossary from the FA Handbook, integrations, and conceptual data model as a frame"*

**What you need**:
| Source | Role | Status | Gap |
|--------|------|--------|-----|
| **Conceptual Model** | The FRAME | ✅ LeanIX (10 domains, 229 entities) | — |
| **FA Handbook** | SME definitions | ✅ Ingested (9,673 chunks) | ❌ Need to EXTRACT glossary terms |
| **Integrations** | Data flows | ⚠️ Partial (271 Interface descriptions) | ❌ Need DataObject → Interface mapping |

**Verdict**: 
- ✅ **Frame**: LeanIX conceptual model is ready
- 🔴 **FA Handbook glossary**: Need to BUILD `FAGlossaryPreprocessor`
- 🟡 **Integrations**: Have descriptions, missing entity-level mapping

**What to build**:
```python
# 1. FAGlossaryPreprocessor (not built yet)
#    Extract glossary terms from FA Handbook PDF

# 2. Glossary Linker (not built yet)
#    Match FA Handbook terms → LeanIX DataObjects
#    Output: Unified glossary CSV

# 3. Interface → DataObject Mapper (not built yet)
#    Map which entities flow through each interface
```

**What to ask**:
> "Is there a separate FA Handbook glossary document, or is it embedded in the PDF?"

---

### ✅ Ask 4: *"There's something that we can do at the start to align the FDM and conceptual model"*

**What you need**:
| Component | Status | Gap |
|-----------|--------|-----|
| **FDM entities** | ❌ Not provided | **Need FDM file** |
| **Conceptual model entities** | ✅ LeanIX (229 entities) | — |
| **Alignment logic** | 🔴 Not built | Need to BUILD FDM→LeanIX matcher |

**Verdict**: 
- 🔴 **BLOCKED** — You don't have the FDM

**What to ask**:
> "Can you share the FDM file? What format is it in (Excel, PDF, Visio)?"

**What to build** (once you have FDM):
```python
# 1. FDM Preprocessor (not built yet)
#    Extract FDM entities, attributes, relationships

# 2. FDM→LeanIX Aligner (not built yet)
#    Match FDM entities → LeanIX DataObjects
#    Identify gaps: FDM-only vs LeanIX-only entities
#    Output: Alignment report
```

---

### ✅ Ask 5: *"its important that the conceptual model is the frame (adjusted with FDM inputs too)"*

**What you have**:
- ✅ LeanIX conceptual model (10 domains, 229 entities) — **THE FRAME**
- 🔴 FDM inputs — **MISSING**

**Verdict**: 
- ✅ Frame is ready
- 🔴 Can't adjust with FDM until you get the FDM file

---

### ✅ Ask 6: *"The handbook providing the SME content"*

**What you need**:
| Task | Status | Gap |
|------|--------|-----|
| Extract glossary from FA Handbook | 🔴 Not built | Need `FAGlossaryPreprocessor` |
| Link to LeanIX entities | 🔴 Not built | Need semantic matching logic |
| Output unified glossary | 🔴 Not built | Need CSV/Markdown generator |

**Verdict**: 
- 🔴 **Not achievable yet** — need to build extraction + linking logic

**What to build**:
```python
class FAGlossaryPreprocessor(BasePreprocessor):
    """Extract glossary terms from FA Handbook PDF/HTML.
    
    Output:
    - term_name
    - definition
    - source (FA Handbook chapter/section)
    - related_terms
    - matched_leanix_entity (by name/semantic similarity)
    """
```

**What to ask**:
> "Where exactly is the glossary in the FA Handbook? Is there a dedicated glossary section, or are terms scattered throughout?"

---

### ✅ Ask 7: *"There are glossary terms to Conceptual Data Model Data Objects in LeanIX I need to figure out how I can extract those out to a CSV"*

**What you have**:
- ✅ **DONE** — See `.tmp/leanix_exports/*_data_objects_glossary.csv`
  - 229 DataObjects
  - 130 with definitions
  - Domain groupings (Level 1-4)
  - Export script: `scripts/export_leanix_glossary_csv.py`

**Verdict**: 
- ✅ **ACHIEVABLE** — Already done!

**Sample output**:
```csv
fact_sheet_id,entity_name,definition,domain_group,hierarchy_level
3a0936a7-887c-44a8-83cd-f9ad2b25df74,PARTY,"A Party is any individual person...","ENTERPRISE_DOMAIN",1
b3a7722e-820c-440f-8da8-f740266d6c8a,ACCOUNTS,"Account is a uniquely identified...","ENTERPRISE_DOMAIN",1
```

**What's MISSING from the CSV**:
- ❌ FA Handbook glossary terms (not yet linked)
- ❌ FDM entities (not yet provided)
- ❌ Data Owner/Steward assignments
- ❌ Attribute-level detail

---

### ✅ Ask 8: *"we basically haven't been doing it and its been on my list. We need to stand up/replace/update our reference data management"*

**What you need**:
| Component | Status | Gap |
|-----------|--------|-----|
| **Reference data inventory** | 🔴 Not built | Need to ingest ISO/ONS/FA codes |
| **Conformance checker** | 🔴 Not built | Need to check systems vs. standards |
| **Reference data catalogue** | 🔴 Not built | Need Purview integration or custom build |

**Verdict**: 
- 🔴 **Not achievable yet** — need to build reference data ingestion + conformance logic

**What to ask**:
> "What reference data standards do we use? (ISO 3166 countries, ISO 4217 currencies, ONS codes, FA-specific codes?)"

**What to build**:
```python
# 1. Reference Data Ingestor (not built yet)
#    Ingest ISO 3166, ISO 4217, ONS, FA codes

# 2. Conformance Checker (not built yet)
#    Check if system data conforms to reference standards
#    Output: Non-conformance report

# 3. Reference Data Catalogue (not built yet)
#    Export to Purview or custom catalogue
```

---

## Summary: What's Achievable NOW vs. What's BLOCKED

### ✅ ACHIEVABLE NOW (Quick Wins)

| Deliverable | Status | Effort | Output |
|-------------|--------|--------|--------|
| **LeanIX DataObjects CSV** | ✅ DONE | 0 days | 229 entities, 130 definitions |
| **LeanIX Interfaces CSV** | ✅ DONE | 0 days | 271 data flows |
| **LeanIX Applications CSV** | ✅ DONE | 0 days | 215 systems |
| **RAG query over LeanIX + FA Handbook** | ✅ DONE | 0 days | Query-based lookup |

**You can deliver these THIS WEEK** — files are in `.tmp/leanix_exports/`

---

### 🟡 ACHIEVABLE WITH 1-2 WEEKS BUILD

| Deliverable | Status | Effort | Dependencies |
|-------------|--------|--------|--------------|
| **FAGlossaryPreprocessor** | 🔴 Not built | 2-3 days | FA Handbook source location |
| **Unified Glossary (FA + LeanIX)** | 🔴 Not built | 1-2 days | FAGlossaryPreprocessor |
| **FDM Preprocessor** | 🔴 Not built | 2-3 days | **FDM file** |
| **FDM→LeanIX Aligner** | 🔴 Not built | 2-3 days | FDM Preprocessor |
| **Reference Data Ingestion** | 🔴 Not built | 2-3 days | ISO/ONS code sources |

**You can build these in 1-2 weeks IF you get the FDM file**

---

### 🔴 BLOCKED (Need External Input)

| Deliverable | Blocked By | Who to Ask |
|-------------|------------|------------|
| **FDM ingestion + alignment** | ❌ No FDM file | "Where is the FDM stored?" |
| **DataObject → Owner mapping** | ❌ No stewardship data | LeanIX admin |
| **DataObject → Application mapping** | ❌ No relationship export | LeanIX admin |
| **DataObject → Interface mapping** | ❌ No entity-level flow data | LeanIX admin / Integration team |
| **Attribute-level detail** | ❌ No attribute export | LeanIX admin |
| **Purview catalogue integration** | ❌ No Purview access | Data Platform team |

---

## The REAL Gap Analysis

### What You HAVE ✅

| Source | What It Gives You |
|--------|-------------------|
| **LeanIX Conceptual Model (draw.io)** | Domain structure, entity relationships, cardinality |
| **LeanIX Inventory (Excel)** | 229 entities, 215 apps, 271 interfaces, 130 definitions |
| **FA Handbook (PDF)** | SME definitions, policies, governance rules |

### What's MISSING ❌

| Missing | Why It Matters | Impact |
|---------|----------------|--------|
| **FDM file** | Can't align FDM with conceptual model | **HIGH** — blocks Ask 4, 5 |
| **FA Handbook glossary location** | Can't extract SME terms efficiently | **MEDIUM** — slows Ask 3, 6 |
| **DataObject → Application relationships** | Don't know which systems hold which entities | **HIGH** — blocks Ask 2 ("what is held") |
| **DataObject → Owner assignments** | Don't know who owns what | **MEDIUM** — blocks Ask 2 ("what is owned") |
| **DataObject → Interface mappings** | Don't know which entities flow where | **HIGH** — blocks Ask 2 ("what is transmitted") |
| **Attribute-level detail** | Don't know entity structure | **MEDIUM** — limits glossary usefulness |
| **Reference data sources** | Can't build conformance checker | **MEDIUM** — blocks Ask 8 |

---

## What to Do Next

### **THIS WEEK** (Quick Wins)

```bash
# 1. Review exported CSVs
cd .tmp/leanix_exports/
open 20260227_085903_data_objects_glossary.csv

# 2. Send to Data Working Group
# Subject: LeanIX Conceptual Model Glossary — Review Request

# 3. Ask for missing info (email template below)
```

### **Email Template: Request Missing Data**

```
Subject: LeanIX Data Export — Additional Metadata Needed

Hi [LeanIX Admin / Data Team],

I've exported the LeanIX inventory and have 229 DataObjects, 215 Applications, 
and 271 Interfaces. This is great for the Data Working Group glossary deliverable.

However, I need additional metadata to complete the ask:

1. **Relationships**: Which applications hold/use each DataObject?
   (e.g., "Workday holds PARTY entities for employees")

2. **Stewardship**: Who owns each DataObject?
   (Data Owner, Data Steward assignments)

3. **Data Flows**: Which DataObjects flow through each Interface?
   (e.g., "Workday → Purview transmits PARTY, AGREEMENTS")

4. **Attributes**: What fields does each DataObject have?
   (e.g., PARTY.party_id, PARTY.party_type, PARTY.name)

Can you export this from LeanIX? Or grant API access so I can query it?

Thanks,
Robin
```

### **NEXT 2 WEEKS** (Build)

- [ ] Build `FAGlossaryPreprocessor`
- [ ] Build unified glossary linker (FA Handbook → LeanIX)
- [ ] Request FDM file from team
- [ ] Build reference data ingestion (ISO/ONS)

### **NEXT MONTH** (Integrate)

- [ ] Ingest FDM and align with LeanIX
- [ ] Build conformance checker
- [ ] Export to Purview (or build custom catalogue)

---

## Verdict

**Can you solve the ask?**

| Ask | Achievable? | When |
|-----|-------------|------|
| Glossary from FA Handbook + LeanIX | 🟡 Partial | This week (LeanIX only), 2 weeks (FA + LeanIX) |
| What is held/owned | 🟡 Partial | This week (held), Blocked (owned) |
| What is transmitted | 🟡 Partial | Have interfaces, missing entity-level mapping |
| FDM alignment | 🔴 Blocked | Need FDM file |
| Reference data management | 🔴 Blocked | Need to build ingestion + conformance |

**Overall**: You can deliver **60% now** (LeanIX glossary + data flows), **80% in 2 weeks** (FA Handbook linkage), but **FDM + ownership + detailed lineage require external input**.

---

## The ONE Thing You're Missing Most

**FDM file** — without it, you can't do "FDM and conceptual model alignment" (Ask 4, 5).

**Ask this first**:
> "Where is the FDM? Can you share it?"

Everything else you can build or work around.
