# Enhancement Backlog

Enhancements identified after the initial FA consolidated catalog run.
Baseline verified 2026-03-03: 208 LeanIX entities, 86 HANDBOOK_ONLY, 294 total. BOTH: 18 | LEANIX_ONLY: 190.
PARTY: 27 entities (0 with fact_sheet_id — paragraph format). Ready to begin Enhancement 1a.

---

## Context for Implementors

### Project Structure

Five packages under `elt_llm_rag/`:

| Package | Role |
|---------|------|
| `elt_llm_ingest` | Parses source files → ChromaDB + DocStore |
| `elt_llm_query` | RAG retrieval + LLM synthesis; exposes `query_collections()` |
| `elt_llm_consumer` | Domain-specific consumers; calls `query_collections()` |
| `elt_llm_core` | Shared config, vector store utilities |
| `elt_llm_api` | HTTP / Gradio UI layer |

### Key Files

| File | Role |
|------|------|
| `elt_llm_ingest/src/elt_llm_ingest/doc_leanix_parser.py` | Parses draw.io XML → Markdown sections |
| `elt_llm_ingest/config/ingest_fa_leanix_dat_enterprise_conceptual_model.yaml` | Ingest config; source XML path |
| `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py` | Main consumer; all Steps 1–7 |

### Source XML

```
~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model.xml
```

Ingest config: `elt_llm_ingest/config/ingest_fa_leanix_dat_enterprise_conceptual_model.yaml`

### Collections Produced by Ingest

Prefix: `fa_leanix_dat_enterprise_conceptual_model`

| Collection suffix | Content |
|---|---|
| `_overview` | Model summary |
| `_agreements` | AGREEMENTS domain entities (bullet list) |
| `_campaign` | CAMPAIGN domain entities |
| `_location` | LOCATION domain entities |
| `_product` | PRODUCT domain entities |
| `_reference_data` | REFERENCE DATA domain |
| `_static_data` | Static Data sub-domain |
| `_time_bounded_groupings` | Time Bounded Groupings sub-domain |
| `_transaction_and_events` | TRANSACTION AND EVENTS domain |
| `_additional_entities` | CHANNEL, ACCOUNTS, ASSETS, PARTY entities (paragraph format) |
| `_relationships` | 17 domain-level relationships |

After Enhancement 1a a new `_party` collection will be added and
`_additional_entities` will shrink to CHANNEL, ACCOUNTS, ASSETS only.

Handbook collections: `["fa_handbook"]`

### Current `LeanIXAsset` Dataclass (`doc_leanix_parser.py` lines 22–36)

```python
@dataclass
class LeanIXAsset:
    id: str
    label: str
    fact_sheet_type: str
    fact_sheet_id: str
    parent_group: Optional[str] = None   # domain or subgroup name; None = uncategorized
    parent_id: Optional[str] = None      # raw parent mxCell id
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    style: Optional[str] = None
    raw_attributes: Dict = None
```

### Current `extract_groups()` (`doc_leanix_parser.py` lines 93–110)

```python
def extract_groups(self):
    for mxcell in self.root.iter('mxCell'):
        style = mxcell.get('style', '')
        if 'group' in style and mxcell.get('vertex') == '1':
            group_id = mxcell.get('id')
            for obj in self.root.iter('object'):
                obj_cell = obj.find('mxCell')
                if obj_cell is not None and obj_cell.get('parent') == group_id:
                    label = obj.get('label', '')
                    if label and obj.get('type') == 'factSheet':
                        self.groups[group_id] = self.clean_label(label)
                        break
```

### Current Regex Patterns in Consumer

```python
# Matches bullet-list lines from domain sections:
#   - **Player** *(LeanIX ID: `abc123`)*
_ENTITY_LINE_PAT = re.compile(
    r"^- \*\*([^*]+)\*\*(?:\s+\*\(LeanIX ID: `([^`]*)`\)\*)?$"
)

# Matches paragraph-format lines in additional_entities collection:
#   **Party Types (28 entities):** Club, Player, Individual, ...
_ENTITY_GROUP_PAT = re.compile(
    r"^\*\*([^(]+?)\s*\(\d+\s+entities\):\*\*\s+(.+)"
)
_CATEGORY_DOMAIN: dict[str, str] = {
    "Party Types": "PARTY",
    "Channel Types": "CHANNEL",
    "Account Types": "ACCOUNTS",
    "Asset Types": "ASSETS",
    "Other Entities": "ADDITIONAL",
}

# Matches relationship lines:
#   **PARTY** relates to (cardinality) **AGREEMENTS**.
_REL_LINE_PAT = re.compile(
    r"^(?:- )?\*\*([^*]+)\*\*\s+(.+?)\s+\*\*([^*]+)\*\*\.?$"
)
```

### Consumer Flow (`fa_consolidated_catalog.py`)

```
Step 1  extract_entities_from_conceptual_model()   — docstore scan → 208 entities
Step 2  get_inventory_description_for_entity()     — RAG per entity
Step 3  extract_handbook_terms_from_docstore()     — docstore scan → handbook terms
Step 4  map_handbook_term_to_entity()              — RAG + LLM per term → JSON mapping
Step 5  get_handbook_context_for_entity()          — RAG per entity
Step 6  extract_relationships_from_conceptual_model() — docstore scan → domain-level rels
Step 7  consolidate_catalog()                      — merge → JSON output
```

### Current Catalog JSON Shape (per entity)

```json
{
  "fact_sheet_id": "abc123-uuid",
  "entity_name": "Player",
  "domain": "PARTY",
  "hierarchy_level": "",
  "source": "BOTH | LEANIX_ONLY | HANDBOOK_ONLY",
  "leanix_description": "...",
  "formal_definition": "...",
  "domain_context": "...",
  "governance_rules": "...",
  "handbook_term": "Player",
  "mapping_confidence": "high",
  "mapping_rationale": "...",
  "review_status": "PENDING",
  "review_notes": "",
  "relationships": []
}
```

HANDBOOK_ONLY entities have `"domain": "HANDBOOK_DISCOVERED"` and empty `fact_sheet_id`.

### Draw.io XML Structure — Critical Finding

The draw.io XML contains **two types of group containers**:

**Type 1 — bare `mxCell` with group style** (currently detected):
```xml
<mxCell id="412" connectable="0" parent="1" style="group" vertex="1">
  <mxGeometry height="830" width="610" x="1320" y="289"/>
</mxCell>
<!-- Child entity references group by parent="412" -->
<object type="factSheet" label="Advertising Agreements" factSheetId="uuid" id="413">
  <mxCell parent="412" vertex="1" style="..."/>
</object>
```
These produce: AGREEMENTS (412), PRODUCT (290), TRANSACTION AND EVENTS (352),
LOCATION (257), REFERENCE DATA (258), CAMPAIGN (439),
Static Data (405, nested in 258), Time Bounded Groupings (406, nested in 258).

**Type 2 — `object`-wrapped group** (currently MISSED by parser):
```xml
<object type="factSheet" label="Mentor" factSheetType="DataObject"
        factSheetId="8014fe6b-32d7-4fb9-948e-fb01209eedb5" id="409">
  <mxCell connectable="0" parent="1" style="fillColor=#774fcc;...group;" vertex="1">
    <mxGeometry height="590" width="570" x="430" y="370"/>
  </mxCell>
</object>
<!-- All PARTY entities reference this container -->
<object type="factSheet" label="PARTY" factSheetType="DataObject" id="4">
  <mxCell parent="409" vertex="1" style="..."/>
</object>
<object type="factSheet" label="Player" factSheetType="DataObject" factSheetId="uuid" id="46">
  <mxCell parent="409" vertex="1" style="..."/>
</object>
```
Note: id=409 has the outer `<object>` label `"Mentor"` (a LeanIX export artefact), but the
first `factSheet` child (id=4, label=`"PARTY"`) is what `extract_groups()` will use as the
group label once it detects this container.

**Entities with no group container (parent=1, will remain uncategorized):**
CHANNEL (830×370), ACCOUNTS (580×220), ASSETS (550×265) and all their child entities
(38 total). No draw.io group container exists for these in the XML.

**Current entity count by group:**

| Group | Domain | Entities |
|-------|--------|----------|
| 412 | AGREEMENTS | 42 |
| 290 | PRODUCT | 42 |
| 352 | TRANSACTION AND EVENTS | 36 |
| 409 | PARTY *(Type 2 — currently missed)* | 30 leaf + domain/subgroup labels |
| 257 | LOCATION | 5 |
| 258 | REFERENCE DATA | 1 |
| 405 | Static Data (nested in 258) | 3 |
| 406 | Time Bounded Groupings (nested in 258) | 2 |
| 439 | CAMPAIGN | 9 |
| 1 (root) | Uncategorized — CHANNEL, ACCOUNTS, ASSETS | 38 |

---

## 1a. Parser Fix: Detect Object-Wrapped Group Containers

**File:** `elt_llm_ingest/src/elt_llm_ingest/doc_leanix_parser.py`
**Lines:** `extract_groups()` at lines 93–110
**Requires re-ingestion:** Yes

### Problem

`extract_groups()` iterates `<mxCell>` elements only. The PARTY domain container (id=409)
is an `<object type="factSheet">` whose inner `<mxCell>` carries the group style. This
object-wrapped group is invisible to the current iteration, so all 30 PARTY entities fall
through to "Uncategorized" and are written in paragraph format in `additional_entities`.

### Fix

Replace the current `extract_groups()` with the following implementation:

```python
def extract_groups(self):
    """Extract group containers (PARTY, AGREEMENTS, PRODUCT, etc.)

    Two types exist in the draw.io XML:
    - Type 1: bare <mxCell id="N" style="...group..." vertex="1"/>
    - Type 2: <object id="N"><mxCell style="...group..." vertex="1"/></object>
    Both types are now detected.
    """
    # ── Collect all group container IDs and their parent references ──────────
    group_parents: dict[str, str] = {}  # group_id -> parent_id

    # Type 1: bare mxCell with group style
    for mxcell in self.root.iter('mxCell'):
        style = mxcell.get('style', '')
        if 'group' in style and mxcell.get('vertex') == '1':
            gid = mxcell.get('id')
            if gid:
                group_parents[gid] = mxcell.get('parent', '1')

    # Type 2: object-wrapped mxCell with group style (e.g. PARTY container id=409)
    for obj in self.root.iter('object'):
        cell = obj.find('mxCell')
        if cell is not None:
            style = cell.get('style', '')
            if 'group' in style and cell.get('vertex') == '1':
                oid = obj.get('id')
                if oid and oid not in group_parents:
                    group_parents[oid] = cell.get('parent', '1')

    # ── Label each group from its first factSheet child ───────────────────────
    for group_id in group_parents:
        for obj in self.root.iter('object'):
            obj_cell = obj.find('mxCell')
            if obj_cell is not None and obj_cell.get('parent') == group_id:
                label = obj.get('label', '')
                if label and obj.get('type') == 'factSheet':
                    self.groups[group_id] = self.clean_label(label)
                    break

    # ── Store parent chain for hierarchy resolution ───────────────────────────
    # Used by parse_asset() to set domain vs subgroup correctly.
    self._group_parents = group_parents
```

### Corresponding change in `parse_asset()` (lines 122–162)

Add `domain` resolution after `parent_group` is set. When a group is nested inside another
group (e.g. Static Data inside REFERENCE DATA), `parent_group` will be the subgroup name
("Static Data") and `domain` will be the top-level group name ("REFERENCE DATA"):

```python
# After: parent_id = mxcell.get('parent')
#        parent_group = self.groups.get(parent_id)
# Add:
parent_of_parent = getattr(self, '_group_parents', {}).get(parent_id)
domain = self.groups.get(parent_of_parent) if parent_of_parent in self.groups else parent_group
```

Update `LeanIXAsset` dataclass to add a `domain` field:

```python
@dataclass
class LeanIXAsset:
    id: str
    label: str
    fact_sheet_type: str
    fact_sheet_id: str
    parent_group: Optional[str] = None   # immediate group (subgroup name if nested)
    parent_id: Optional[str] = None
    domain: Optional[str] = None         # NEW: top-level domain name
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    style: Optional[str] = None
    raw_attributes: Dict = None
```

### Effect on `to_section_files()`

PARTY entities (Club, Player, Match Official, etc.) will now have `parent_group = "PARTY"`
and appear in the `party` domain section as bullet lists:
```
- **Player** *(LeanIX ID: `uuid`)*
- **Club** *(LeanIX ID: `uuid`)*
```
They will no longer appear in `additional_entities`. The `additional_entities` section will
shrink to CHANNEL, ACCOUNTS, and ASSETS entities only (38 entities, still paragraph format).

Note: `Individual`, `Organisation`, `Team`, `Household`, `Business Unit` labels will also
appear as bullet entries in the PARTY section (they are children of group 409). These are
subgroup container labels, not leaf entities. The `to_section_files()` code that excludes
the root domain label (`if a.label.upper() != group_name.upper()`) will correctly exclude
`"PARTY"` but will include `"Individual"` and `"Organisation"` as listed entities. This is
acceptable for now; Enhancement 1b addresses the subgroup hierarchy separately.

### Re-ingest after fix

```bash
uv run python -m elt_llm_ingest.clean_slate --prefix fa_leanix_dat_enterprise_conceptual_model
uv run python -m elt_llm_ingest.runner --cfg ingest_fa_leanix_dat_enterprise_conceptual_model
```

---

## 1b. Parser Enhancement: Subgroup Hierarchy via Spatial Containment

**File:** `elt_llm_ingest/src/elt_llm_ingest/doc_leanix_parser.py`
**Depends on:** Enhancement 1a
**Requires re-ingestion:** Yes

### Problem

Within the PARTY group (id=409), `Individual`, `Organisation`, `Team`, `Household`, and
`Business Unit` are visual subgroup containers. Leaf entities like `Player`, `Match
Official`, `Club`, `Supplier` are positioned INSIDE these visual boxes, but in the XML they
all share the same `parent=409`. There is no XML parent-child relationship distinguishing
which leaf entity belongs to which subgroup.

**All domains use this same visual pattern** — inspection of the draw.io XML confirms that
every group uses large rectangles as visual subgroup containers and 100×40 boxes as leaf
entities. No hardcoding of coordinates is needed or appropriate: the geometry is read
directly from the parsed `LeanIXAsset` data.

Subgroup containers found per domain (from live XML inspection):

| Domain | Subgroups |
|---|---|
| PARTY | Individual, Organisation, Team, Household, Business Unit |
| AGREEMENTS | Classification Types, Commercial & Legal, Competition Governance, Game Regulation Agreements, Learning & Qualifications, Match Execution, Operational Infrastructure, Participant Eligibility, Marketing Incentives |
| PRODUCT | Commercial & Corporate Services, Events and Experiences, Food & Beverages, Football Services & Operations, Merchandise & Retail, Subscriptions & Media Access, Venue & Event Operations |
| TRANSACTION AND EVENTS | Attendance & Operational Events, Behavioural & Engagement Interactions, Customer Transactions, Football Admin & Governance Events, IT Maintenance Event, Incidents & Disciplinary Events, Performance & Game Events |
| CAMPAIGN | Campaign Type, Campaign channel, Market Plan, Market Segment, Offer, Opportunity, Promotion |
| REFERENCE DATA | Configuration Data |
| LOCATION, Static Data, Time Bounded Groupings | No visual subgroup containers |

**Discriminator rule** (verified against all domains):
- `width > 100 AND height > 40` → subgroup container
- `width ≤ 100 OR height ≤ 40` → leaf entity (all leaf entities are exactly 100×40)

This correctly handles edge cases: "Targeted Promotion" in CAMPAIGN is 102×40 (h=40, not
>40) so it is treated as a leaf entity, not a subgroup container.

### Fix

Add a `_assign_subgroups()` method that applies to **all groups** generically — no
hardcoded group IDs or coordinates:

```python
def _assign_subgroups(self):
    """Assign leaf entities to their visual subgroup using spatial containment.

    All domain groups in this model use large rectangles as subgroup containers
    and 100x40 boxes as leaf entities. This method detects both dynamically from
    parsed geometry — no hardcoded group IDs or coordinates.

    Discriminator:
        subgroup container: width > 100 AND height > 40
        leaf entity:        width <= 100 OR height <= 40
    """
    # Build group_id -> domain_name map (all groups, not just top-level)
    # For nested groups (Static Data inside REFERENCE DATA), domain is the
    # top-level ancestor; parent_group is the immediate group label.
    for group_id, domain_name in self.groups.items():
        if not domain_name:
            continue

        subgroup_boxes: list[tuple[str, float, float, float, float]] = []
        leaf_assets: list[LeanIXAsset] = []

        for asset in self.assets.values():
            if asset.parent_id != group_id:
                continue
            if asset.label.upper() == domain_name.upper():
                continue  # skip the root domain label node

            w = asset.width or 0
            h = asset.height or 0

            if w > 100 and h > 40:
                # Visual subgroup container
                subgroup_boxes.append(
                    (asset.label, asset.x or 0, asset.y or 0, w, h)
                )
            else:
                # Leaf entity
                leaf_assets.append(asset)

        if not subgroup_boxes:
            continue  # domain has no visual subgroups (e.g. LOCATION)

        # Assign each leaf to the subgroup whose bounding box contains its centre
        for asset in leaf_assets:
            cx = (asset.x or 0) + (asset.width or 0) / 2
            cy = (asset.y or 0) + (asset.height or 0) / 2
            for (sg_name, sg_x, sg_y, sg_w, sg_h) in subgroup_boxes:
                if sg_x <= cx <= sg_x + sg_w and sg_y <= cy <= sg_y + sg_h:
                    asset.domain = domain_name     # top-level domain
                    asset.parent_group = sg_name   # subgroup
                    break
```

Call `_assign_subgroups()` at the end of `extract_all()`:

```python
def extract_all(self):
    self.extract_groups()
    self.extract_assets()
    self.extract_relationships()
    self.enrich_relationships()
    self._assign_subgroups()   # NEW
```

### Effect on `to_section_files()`

After `_assign_subgroups()`, **every domain** that has visual subgroup containers will have
its entities grouped under subgroup headings. Update the domain section generation loop in
`to_section_files()` (around line 477) to detect when entities within a section have
different `parent_group` values and emit subgroup headings:

```markdown
## Individual Subgroup

- **Player** *(LeanIX ID: `uuid`)*
- **Match Official** *(LeanIX ID: `uuid`)*

## Organisation Subgroup

- **Club** *(LeanIX ID: `uuid`)*
- **Supplier** *(LeanIX ID: `uuid`)*
```

```markdown
## Commercial & Legal Subgroup

- **Advertising Agreements** *(LeanIX ID: `uuid`)*
- **Image Rights Agreement** *(LeanIX ID: `uuid`)*

## Competition Governance Subgroup

- **Competition Rules** *(LeanIX ID: `uuid`)*
```

The domain section loop should:
1. Group `domain_entities` by `asset.parent_group`
2. For each subgroup name (sorted), emit `## {subgroup} Subgroup\n\n` then bullet list
3. For any entity with `parent_group == domain_name` (unassigned to a subgroup), emit
   under an `## Other\n\n` heading or directly under the domain header

### Re-ingest after fix

Same commands as Enhancement 1a.

---

## 2. Consumer: Include Subgroup in Output JSON

**File:** `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py`
**Depends on:** Enhancement 1b (for PARTY subgroup data in section documents)

### Problem

The consumer entity dict from `extract_entities_from_conceptual_model()` contains:
```python
{
    "entity_name": "Player",
    "domain": "PARTY",
    "fact_sheet_id": "uuid",
    "hierarchy_level": "",
}
```
No `subgroup` field. After Enhancement 1b, section documents will contain subgroup headings
that can be parsed to populate this field.

### New bullet format after re-ingest (Enhancement 1b)

```
## Individual Subgroup
- **Player** *(LeanIX ID: `uuid`)*
```

### Updated `_ENTITY_LINE_PAT`

Add a subgroup heading pattern to capture the current section heading:

```python
# Matches subgroup heading lines in domain sections:
#   ## Individual Subgroup
_SUBGROUP_HEADING_PAT = re.compile(r"^## (.+?) Subgroup$")
```

Update the entity extraction loop to track current subgroup from headings:

```python
current_subgroup = ""
for line in text.splitlines():
    line = line.strip()
    if not line:
        continue

    # Track subgroup heading
    m = _SUBGROUP_HEADING_PAT.match(line)
    if m:
        current_subgroup = m.group(1).strip()
        continue

    # Bullet-list format
    m = _ENTITY_LINE_PAT.match(line)
    if m:
        name = m.group(1).strip()
        fsid = (m.group(2) or "").strip()
        # ... existing dedup check ...
        entities.append({
            "entity_name": name,
            "domain": domain,
            "subgroup": current_subgroup,   # NEW
            "fact_sheet_id": fsid,
            "hierarchy_level": "",
        })
        continue

    # Paragraph format (_ENTITY_GROUP_PAT) — still needed for CHANNEL/ACCOUNTS/ASSETS
    # (these have no group container in the XML and remain in additional_entities)
    m = _ENTITY_GROUP_PAT.match(line)
    if not m:
        continue
    # ... existing paragraph handling, subgroup="" for these ...
```

### Updated catalog JSON record shape

```json
{
  "fact_sheet_id": "uuid",
  "entity_name": "Player",
  "domain": "PARTY",
  "subgroup": "Individual",
  "hierarchy_level": "",
  "source": "BOTH",
  "leanix_description": "...",
  "formal_definition": "...",
  "domain_context": "...",
  "governance_rules": "...",
  "handbook_term": "Player",
  "mapping_confidence": "high",
  "mapping_rationale": "...",
  "review_status": "PENDING",
  "review_notes": "",
  "relationships": []
}
```

Update `consolidate_catalog()` to pass `entity.get("subgroup", "")` into the record.

### Note on `_ENTITY_GROUP_PAT`

Do NOT remove `_ENTITY_GROUP_PAT`. CHANNEL, ACCOUNTS, and ASSETS entities have no draw.io
group container in the XML and remain in `additional_entities` in paragraph format after
re-ingest. `_ENTITY_GROUP_PAT` continues to handle these 38 entities.

---

## 3. Entity-to-Entity Relationships from FA Handbook

**File:** `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py`
**Depends on:** Enhancement 1a (subgroup context improves prompt quality)
**Step placement:** New Step 6b, between current Steps 6 and 7 (consolidation)

### Problem

Step 6 (current) extracts only domain-level relationships from the LeanIX relationships
collection (e.g. `PARTY relates to AGREEMENTS`). No entity-to-entity relationships are
captured (e.g. `Player → Club`, `Agent → Player`). The FA Handbook contains the business
rules that define these relationships.

### Approach

For each domain-level relationship pair (e.g. PARTY ↔ AGREEMENTS), query the Handbook
collections to extract entity-to-entity relationships between entities of those domains.
This constrains the search to entity pairs whose domains are connected, avoiding O(n²)
queries across all 208 entities.

Both directions of each relationship must be returned as first-class records.

### New function: `extract_entity_relationships_from_handbook()`

Insert after `extract_relationships_from_conceptual_model()` in `generate_consolidated_catalog()`:

```python
def extract_entity_relationships_from_handbook(
    domain_relationships: dict[str, list[dict]],
    conceptual_entities: list[dict],
    handbook_collections: list[str],
    rag_config: RagConfig,
) -> list[dict]:
    """Extract entity-to-entity relationships from FA Handbook via RAG.

    Args:
        domain_relationships: Output of extract_relationships_from_conceptual_model()
                              keyed by source domain (lowercase).
        conceptual_entities:  Full entity list from Step 1.
        handbook_collections: ["fa_handbook"]
        rag_config:           RAG config (LLM model, num_queries etc.)

    Returns:
        List of bidirectional entity relationship dicts.
    """
    # Build domain → entity list lookup
    domain_entities: dict[str, list[str]] = {}
    for e in conceptual_entities:
        d = e.get("domain", "").upper()
        domain_entities.setdefault(d, []).append(e["entity_name"])

    entity_relationships: list[dict] = []
    seen_pairs: set[tuple[str, str]] = set()

    # Iterate over domain-level relationships to constrain entity pairs
    for source_domain_lower, rels in domain_relationships.items():
        source_domain = source_domain_lower.upper()
        source_entities = domain_entities.get(source_domain, [])
        if not source_entities:
            continue

        for rel in rels:
            target_domain = rel.get("target_entity", "").upper()
            target_entities = domain_entities.get(target_domain, [])
            if not target_entities:
                continue

            pair_key = tuple(sorted([source_domain, target_domain]))
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)

            query = _ENTITY_RELATIONSHIP_PROMPT.format(
                source_domain=source_domain,
                source_entities=", ".join(source_entities[:20]),
                target_domain=target_domain,
                target_entities=", ".join(target_entities[:20]),
                domain_cardinality=rel.get("cardinality", "relates to"),
            )

            try:
                result = query_collections(handbook_collections, query, rag_config)
                response = result.response.strip()
                json_match = re.search(r'\[.*\]', response, re.DOTALL)
                if json_match:
                    records = json.loads(json_match.group())
                    entity_relationships.extend(records)
            except Exception as e:
                print(f"  [warn] relationship query failed for {source_domain}↔{target_domain}: {e}")

    return entity_relationships
```

### Prompt template — add as module-level constant

```python
_ENTITY_RELATIONSHIP_PROMPT = """\
You are analysing the FA (The Football Association) Handbook to identify \
entity-to-entity relationships.

Source domain: {source_domain}
Source entities (sample): {source_entities}

Target domain: {target_domain}
Target entities (sample): {target_entities}

Domain-level relationship: {source_domain} {domain_cardinality} {target_domain}

Task: Identify all specific entity-to-entity relationships between the source \
and target entity lists as described in the FA Handbook. For every relationship \
found, return BOTH the forward and inverse directions as separate records.

Return a JSON array. Each item must have exactly these fields:
- source_entity:         name of the source entity (must be from source entities list)
- source_domain:         source domain name
- target_entity:         name of the target entity (must be from target entities list)
- target_domain:         target domain name
- relationship:          verb phrase for the forward direction (e.g. "is registered with")
- inverse_relationship:  verb phrase for the inverse direction (e.g. "has registered players")
- cardinality:           forward cardinality — one of: "1:1", "1:many", "many:1", "many:many"
- inverse_cardinality:   inverse cardinality — one of: "1:1", "1:many", "many:1", "many:many"
- inferred:              true if inferred from context, false if explicitly stated
- evidence:              brief quote or paraphrase from the Handbook (max 30 words)

Rules:
- Only include relationships supported by the FA Handbook content.
- Do not invent relationships. If none are found, return [].
- Both the forward and inverse record must reference each other via \
  inverse_relationship / relationship fields.

Return only the JSON array, no other text."""
```

### Target output shape (in `fa_entity_relationships.json`)

```json
[
  {
    "source_entity": "Player",
    "source_domain": "PARTY",
    "target_entity": "Club",
    "target_domain": "PARTY",
    "relationship": "is registered with",
    "inverse_relationship": "has registered players",
    "cardinality": "many:1",
    "inverse_cardinality": "1:many",
    "inferred": false,
    "evidence": "A player must be registered with an affiliated club — FA Handbook Rule C2.1"
  },
  {
    "source_entity": "Club",
    "source_domain": "PARTY",
    "target_entity": "Player",
    "target_domain": "PARTY",
    "relationship": "has registered players",
    "inverse_relationship": "is registered with",
    "cardinality": "1:many",
    "inverse_cardinality": "many:1",
    "inferred": false,
    "evidence": "A player must be registered with an affiliated club — FA Handbook Rule C2.1"
  }
]
```

### Wiring into `generate_consolidated_catalog()`

Add after Step 6 (relationship extraction), before Step 7 (consolidation):

```python
# Step 6b: Entity-to-entity relationships from Handbook
print("\n=== Step 6b: Extract Entity-to-Entity Relationships from Handbook ===")
entity_relationships: list[dict] = []
if not skip_relationships:
    entity_relationships = extract_entity_relationships_from_handbook(
        domain_relationships=relationships,
        conceptual_entities=conceptual_entities,
        handbook_collections=handbook_collections,
        rag_config=rag_config,
    )
    rel_path = output_dir / "fa_entity_relationships.json"
    with open(rel_path, "w", encoding="utf-8") as f:
        json.dump(entity_relationships, f, indent=2, ensure_ascii=False)
    print(f"  {len(entity_relationships)} entity relationships → {rel_path}")
```

### Notes
- Expected coverage: ~70–80% of meaningful entity pairs; ambiguous cases flagged `inferred: true`
- Query count: one per unique domain pair (not per entity pair) — bounded by number of domain relationships (~17)
- `--skip-relationships` flag skips both Step 6 and Step 6b

---

## 4. LLM-Inferred Domain and Subgroup for Handbook-Only Entities

**File:** `elt_llm_consumer/src/elt_llm_consumer/fa_consolidated_catalog.py`
**Depends on:** Enhancement 2 (subgroup examples must be available for inference context)
**Step placement:** Within `consolidate_catalog()`, when building HANDBOOK_ONLY records

### Problem

HANDBOOK_ONLY entities are currently written with `"domain": "HANDBOOK_DISCOVERED"` and no
subgroup. These are genuine LeanIX model gaps. The LLM can infer the correct domain and
subgroup from the existing taxonomy structure and the entity's Handbook definition.

### Approach — Three-Tier Inference

Build a taxonomy context string from the already-extracted `conceptual_entities` and pass it
with each HANDBOOK_ONLY entity to the LLM. The LLM follows a **three-tier decision process**
in priority order:

| Tier | Rule | `inference_tier` value | `review_status` |
|---|---|---|---|
| 1 — Existing | Entity clearly fits an existing domain/subgroup | `"existing"` | `"PENDING"` (high confidence) or `"NEEDS_CLARIFICATION"` (medium/low) |
| 2 — Proposed new | No existing match, but context allows proposing a new Domain/Subgroup | `"new_proposed"` | `"PROPOSED_NEW_TAXONOMY"` |
| 3 — Unknown | Genuinely no context available | `"unknown"` | `"NEEDS_CLARIFICATION"` |

Tier 3 should be rare in practice — the LLM should prefer Tier 2 (propose new taxonomy) over
Tier 3 whenever entity context provides enough signal to name a domain and subgroup.

### New function: `infer_domain_for_handbook_entity()`

```python
def infer_domain_for_handbook_entity(
    entity_name: str,
    handbook_definition: str,
    taxonomy_context: str,
    model_collections: list[str],
    rag_config: RagConfig,
) -> dict:
    """Use LLM to infer domain and subgroup for a HANDBOOK_ONLY entity.

    Args:
        entity_name:         The entity name from the Handbook.
        handbook_definition: The formal definition from the Handbook.
        taxonomy_context:    JSON string of known domains and subgroups with examples.
        model_collections:   fa_leanix_dat_enterprise_conceptual_model_* collections.
        rag_config:          RAG config.

    Returns:
        Dict with entity_domain, entity_subgroup, inference_tier, inference_confidence,
        inference_reasoning, alternative_domain.

        inference_tier values:
          "existing"      — mapped to known taxonomy (preferred)
          "new_proposed"  — no existing match; LLM proposed a new domain/subgroup
          "unknown"       — last resort; no usable context
    """
    query = _DOMAIN_INFERENCE_PROMPT.format(
        taxonomy_context=taxonomy_context,
        entity_name=entity_name,
        handbook_definition=handbook_definition,
    )
    try:
        result = query_collections(model_collections, query, rag_config)
        response = result.response.strip()
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            tier = parsed.get("inference_tier", "unknown")
            confidence = parsed.get("inference_confidence", "low")
            # Derive review_status from tier and confidence
            if tier == "existing" and confidence == "high":
                parsed["review_status"] = "PENDING"
            elif tier == "new_proposed":
                parsed["review_status"] = "PROPOSED_NEW_TAXONOMY"
            else:
                parsed["review_status"] = "NEEDS_CLARIFICATION"
            return parsed
    except Exception:
        pass
    return {
        "entity_domain": "unknown",
        "entity_subgroup": "unknown",
        "inference_tier": "unknown",
        "inference_confidence": "low",
        "inference_reasoning": "LLM inference failed",
        "alternative_domain": "",
        "review_status": "NEEDS_CLARIFICATION",
    }
```

### Prompt template — add as module-level constant

```python
_DOMAIN_INFERENCE_PROMPT = """\
You are classifying a business entity into the FA (The Football Association) \
data architecture taxonomy.

The current known domains and subgroups are:
{taxonomy_context}

Entity name: {entity_name}
FA Handbook definition: {handbook_definition}

Follow this DECISION PROCESS in priority order:

TIER 1 — Map to existing taxonomy (strongly preferred):
  If the entity clearly belongs to an existing domain/subgroup, assign it there.
  Set inference_tier: "existing"

TIER 2 — Propose new taxonomy:
  If the entity does not fit any existing domain/subgroup, but the entity context
  provides enough information to propose a meaningful new Domain and/or Subgroup,
  propose sensible names that follow the same naming conventions as the existing taxonomy.
  Set inference_tier: "new_proposed"
  Note: prefer this over Tier 3 whenever possible.

TIER 3 — Unknown (last resort):
  Only if there is genuinely insufficient context to classify the entity.
  Set inference_tier: "unknown"

Return a JSON object with exactly these fields:
- entity_domain:       domain name (existing, proposed new name, or "unknown")
- entity_subgroup:     subgroup name (existing, proposed new name, "" if none, or "unknown")
- inference_tier:      "existing" | "new_proposed" | "unknown"
- inference_confidence: "high" | "medium" | "low"
  - high:   clear semantic match, only one plausible option
  - medium: plausible but two or more options could apply
  - low:    genuinely ambiguous
- inference_reasoning: one or two sentences explaining the assignment
- alternative_domain:  next most likely domain if confidence is not "high", else ""

For Tier 1, use domain and subgroup names EXACTLY as listed in the taxonomy.
For Tier 2, follow the same Title Case naming conventions as existing entries.
Return only the JSON object, no other text."""
```

### Building the taxonomy context string

Add a helper function called before `consolidate_catalog()`:

```python
def build_taxonomy_context(conceptual_entities: list[dict]) -> str:
    """Build a JSON taxonomy string from known entities for use in inference prompts."""
    taxonomy: dict[str, dict[str, list[str]]] = {}
    for e in conceptual_entities:
        domain = e.get("domain", "")
        subgroup = e.get("subgroup", "")   # requires Enhancement 2
        name = e.get("entity_name", "")
        if not domain:
            continue
        taxonomy.setdefault(domain, {})
        taxonomy[domain].setdefault(subgroup or "_entities", []).append(name)

    # Format as readable JSON for prompt
    output = {}
    for domain, subgroups in sorted(taxonomy.items()):
        output[domain] = {}
        for sg, entities in sorted(subgroups.items()):
            key = sg if sg != "_entities" else "entities"
            output[domain][key] = sorted(entities)[:10]  # limit examples per subgroup

    return json.dumps(output, indent=2)
```

### Wiring into `consolidate_catalog()`

In `consolidate_catalog()`, at the start of Step 2 (HANDBOOK_ONLY processing), add:

```python
# Build taxonomy context once for all HANDBOOK_ONLY inference calls
taxonomy_context = build_taxonomy_context(conceptual_entities)

for term_entry in handbook_terms:
    # ... existing checks ...
    if is_handbook_only:
        inferred = infer_domain_for_handbook_entity(
            entity_name=term,
            handbook_definition=term_entry.get("definition", ""),
            taxonomy_context=taxonomy_context,
            model_collections=model_collections,
            rag_config=rag_config,
        )
        record = {
            "fact_sheet_id": "",
            "entity_name": term,
            "domain": inferred.get("entity_domain", "HANDBOOK_DISCOVERED"),
            "subgroup": inferred.get("entity_subgroup", ""),
            "hierarchy_level": "",
            "source": "HANDBOOK_ONLY",
            "leanix_description": "Not documented in LeanIX — candidate for model addition",
            "formal_definition": term_entry.get("definition", ""),
            # ... other existing fields ...
            "inferred": True,
            "inference_tier": inferred.get("inference_tier", "unknown"),
            "inference_confidence": inferred.get("inference_confidence", "low"),
            "inference_reasoning": inferred.get("inference_reasoning", ""),
            "alternative_domain": inferred.get("alternative_domain", ""),
            "review_status": inferred.get("review_status", "NEEDS_CLARIFICATION"),
        }
```

### Confidence scoring guidance for LLM

Include this in the taxonomy context or system prompt context:
- **high** — clear semantic match (e.g. "Kit Manufacturer" → PARTY/Organisation)
- **medium** — plausible but ambiguous (e.g. "Sponsorship Reporting" → AGREEMENTS or CAMPAIGN?)
- **low** — genuinely unclear (e.g. "Arbitration Panel" → AGREEMENTS or GOVERNANCE?)

**Review status mapping:**

| Tier | Confidence | `review_status` |
|---|---|---|
| existing | high | `PENDING` |
| existing | medium or low | `NEEDS_CLARIFICATION` |
| new_proposed | any | `PROPOSED_NEW_TAXONOMY` |
| unknown | any | `NEEDS_CLARIFICATION` |

`PROPOSED_NEW_TAXONOMY` entries require SME sign-off before the proposed domain/subgroup
is considered for inclusion in the LeanIX conceptual model.

---

## Sequencing

```
[ ] 0. Verify current consumer fix  (208 entities, 17 relationships — clean run with num_queries=1)
[ ] 1. Enhancement 1a — Parser: detect object-wrapped groups + re-ingest
         → PARTY entities move from additional_entities paragraph to party bullet section
         → Verify consumer still extracts 208 entities (or more if some were double-counted)
[ ] 2. Enhancement 1b — Parser: spatial subgroup assignment + re-ingest
         → PARTY entities gain Individual / Organisation / Team / Household / Business Unit subgroup
[ ] 3. Enhancement 2  — Consumer: parse subgroup headings; add subgroup to output JSON
[ ] 4. Enhancement 3  — Consumer: entity-to-entity relationships from Handbook (new Step 6b)
[ ] 5. Enhancement 4  — Consumer: LLM inference of domain/subgroup for HANDBOOK_ONLY entities
```

Enhancement 4 requires Enhancement 2 so that `build_taxonomy_context()` has subgroup data
to populate the inference prompt. Enhancement 3 is independent of 2 and 4 and can run in
parallel once Enhancement 1a is complete.

---

## Acceptance Criteria

Validation commands assume the catalog JSON is at `.tmp/fa_consolidated_catalog.json`
and entity relationships at `.tmp/fa_entity_relationships.json`.

**Confirmed baseline metrics (run 2026-03-03):**
- Total entities: 294 (208 LeanIX, 86 HANDBOOK_ONLY)
- BOTH: 18 | LEANIX_ONLY: 190 | HANDBOOK_ONLY: 86
- PARTY: 27 entities, **0 with fact_sheet_id** (paragraph extraction has no IDs)
- PARTY+CHANNEL+ACCOUNTS+ASSETS+ADDITIONAL = 68 (all from `additional_entities` collection)
- Subgroup field: empty on all 294 entities

| Step | Validation command | Expected result |
|---|---|---|
| 0 — baseline domains | `jq '[.[] \| .domain] \| unique' .tmp/fa_consolidated_catalog.json` | PARTY IS present (27 entities via paragraph format `_ENTITY_GROUP_PAT`); all 27 have empty `fact_sheet_id` |
| 0 — baseline PARTY ids | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); p=[e for e in d if e.get('domain')=='PARTY']; print(sum(1 for e in p if e.get('fact_sheet_id')), '/', len(p))"` | `0 / 27` (baseline: all PARTY entities lack IDs — paragraph format) |
| 1a — parser fix | `jq '[.[] \| select(.domain == "PARTY")] \| length' .tmp/fa_consolidated_catalog.json` | ≥ 27 entities with domain PARTY (count unchanged; now from bullet format) |
| 1a — fact_sheet_id | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); p=[e for e in d if e.get('domain')=='PARTY']; print(sum(1 for e in p if e.get('fact_sheet_id')), '/', len(p))"` | `27 / 27` (all PARTY entities now have fact_sheet_id from bullet format) |
| 1a — shrink check | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); n=[e for e in d if e.get('domain') in ('CHANNEL','ACCOUNTS','ASSETS','ADDITIONAL')]; print(len(n))"` | ~41 (was 41 before fix; PARTY:27 has moved out of this group — total `additional_entities` drops from 68 to 41) |
| 1b — subgroups | `jq '[.[] \| select(.subgroup != "" and .subgroup != null)] \| length' .tmp/fa_consolidated_catalog.json` | ≥ 100 entities across all domains have a non-empty subgroup |
| 1b — per domain | `jq '[.[] \| select(.subgroup != "")] \| group_by(.domain) \| map({domain: .[0].domain, count: length})' .tmp/fa_consolidated_catalog.json` | AGREEMENTS, PRODUCT, TRANSACTION AND EVENTS, CAMPAIGN, PARTY all show counts > 0 |
| 3 — entity rels | `jq 'length' .tmp/fa_entity_relationships.json` | 50–150 bidirectional entity relationships |
| 3 — bidirectional | `jq '[.[] \| .source_entity] \| unique \| length' .tmp/fa_entity_relationships.json` | Each relationship appears from both directions |
| 4 — inferred count | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); print(sum(1 for e in d if e.get('inferred')))"` | ~86 (one per HANDBOOK_ONLY entity) |
| 4 — no HANDBOOK_DISCOVERED | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); print(sum(1 for e in d if e.get('domain')=='HANDBOOK_DISCOVERED'))"` | 0 (all assigned — existing, proposed, or unknown) |
| 4 — tier breakdown | `python3 -c "import json; from collections import Counter; d=json.load(open('.tmp/fa_consolidated_catalog.json')); print(Counter(e.get('inference_tier','n/a') for e in d if e.get('inferred')))"` | existing: majority, new_proposed: some, unknown: few or zero |
| 4 — proposed new | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); print([(e['entity_name'],e['entity_domain'],e['entity_subgroup']) for e in d if e.get('inference_tier')=='new_proposed'])"` | List of proposed new taxonomy entries for SME review |
| 4 — needs review | `python3 -c "import json; d=json.load(open('.tmp/fa_consolidated_catalog.json')); print(sum(1 for e in d if e.get('review_status')=='NEEDS_CLARIFICATION'))"` | > 0 (low-confidence or unknown-tier inferences flagged) |

---

## Rollback Plan

Before any re-ingestion step (Enhancements 1a, 1b), back up the ChromaDB and DocStore:

```bash
# Backup (run BEFORE re-ingestion)
CHROMA_DIR=$(grep 'persist_directory' elt_llm_ingest/config/rag_config.yaml | awk '{print $2}')
cp -r "$CHROMA_DIR" "${CHROMA_DIR}.backup_$(date +%Y%m%d_%H%M%S)"
```

To rollback if re-ingestion produces incorrect results:

```bash
# Find the backup dir (most recent)
ls -dt ${CHROMA_DIR}.backup_* | head -1

# Restore
rm -rf "$CHROMA_DIR"
mv "$(ls -dt ${CHROMA_DIR}.backup_* | head -1)" "$CHROMA_DIR"
```

The consumer (`fa_consolidated_catalog.py`) reads from ChromaDB/DocStore at runtime — no
consumer code changes are needed to restore; simply re-run the consumer against the
restored database.

---

## Design Decisions and Open Questions

### Subgroup containers as entities

After Enhancement 1b, `Individual`, `Organisation`, `Team`, `Household`, and `Business Unit`
will appear as bullet entries in the PARTY domain section alongside leaf entities (Player,
Club etc.). They ARE subgroup containers in the visual model, not leaf entities. Options:

**Option A (recommended):** Add `"is_subgroup_container": true` to the entity record for
these labels. Mark them `"review_status": "NEEDS_CLARIFICATION"` so stakeholders can decide
whether they should be imported to Purview as standalone entities or treated as grouping
labels only. Identify them by width > 200px from geometry data captured in `LeanIXAsset`.

**Option B:** Exclude them entirely from entity extraction by filtering on geometry width
(width ≤ 100px for leaf entities). Risk: loses the subgroup label from the catalog.

Recommendation: Option A — retain in catalog, let stakeholders decide.

### CHANNEL, ACCOUNTS, ASSETS subgroup strategy

These 38 entities remain in paragraph format after all parser fixes (no draw.io group
container exists for them in the XML). Their subgroup structure IS visible in the diagram
(CHANNEL → Physical Channel → TV, Radio; ACCOUNTS → Financial Accounts → ...) but their
XML parent is always root (`parent="1"`), so `_assign_subgroups()` never processes them.

**Option A (recommended for now):** Leave as flat `subgroup: ""` via `_ENTITY_GROUP_PAT`.
These are technical/infrastructure entities, lower priority for the business glossary.

**Option B (future):** To unlock subgroup assignment for these, Enhancement 1a must first
be extended to detect CHANNEL, ACCOUNTS, and ASSETS as group containers (currently they
are plain factSheet objects at root level with no group style). Once treated as groups,
`_assign_subgroups()` will handle them automatically — no additional logic needed since
the generic spatial approach already iterates all groups.

### Cardinality cross-validation (low priority)

Enhancement 3 captures cardinality from the Handbook. The LeanIX model has domain-level
cardinality only. A future validation step could cross-reference the two:

```python
def validate_cardinality_against_leanix(entity_relationships, domain_relationships):
    """Flag cases where Handbook-inferred cardinality conflicts with LeanIX domain cardinality."""
    # e.g. Handbook says Player→Club is many:1; LeanIX says PARTY→PARTY is many:many
    # → flag for review, not an error (entity-level can be more specific than domain-level)
```

This is low priority — entity-level cardinality is legitimately more specific than
domain-level. Flag conflicts as informational, not errors.
