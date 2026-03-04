#!/usr/bin/env python3
"""
doc_leanix_parser.py

Extract LeanIX inventory (assets and relationships) from draw.io/diagrams.net XML export.
Outputs structured data suitable for RAG systems (JSON and Markdown formats).

Usage:
    python -m elt_llm_ingest.doc_leanix_parser <input_file.xml> [--output-format json|markdown|both]
"""

import xml.etree.ElementTree as ET
import json
import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class LeanIXAsset:
    """Represents a LeanIX fact sheet/asset"""
    id: str
    label: str
    fact_sheet_type: str
    fact_sheet_id: str
    parent_group: Optional[str] = None   # top-level domain name
    parent_id: Optional[str] = None
    subgroup: Optional[str] = None       # visual subgroup within domain (Enhancement 1b)
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    style: Optional[str] = None
    raw_attributes: Dict = None


@dataclass
class LeanIXRelationship:
    """Represents a relationship between LeanIX assets"""
    id: str
    source_id: str
    target_id: str
    source_label: Optional[str] = None
    target_label: Optional[str] = None
    relationship_type: Optional[str] = None
    cardinality: Optional[str] = None
    style: Optional[str] = None


class LeanIXExtractor:
    """Extract assets and relationships from LeanIX draw.io XML"""

    def __init__(
        self,
        xml_file: str,
        model_name: str = "Enterprise Conceptual Data Model",
        org_name: str = "the organisation",
    ):
        self.xml_file = Path(xml_file)
        self.model_name = model_name
        self.org_name = org_name
        self.tree = None
        self.root = None
        self.assets: Dict[str, LeanIXAsset] = {}
        self.relationships: List[LeanIXRelationship] = []
        self.groups: Dict[str, str] = {}  # group_id -> group_label
        self._group_parents: Dict[str, str] = {}  # group_id -> parent_id
        self.parent_map = {}  # child -> parent mapping for efficient lookups
        self._group_fact_sheet_ids: Dict[str, str] = {}  # group_id → fact_sheet_id of its label node
        self._domain_ids: Dict[str, str] = {}             # domain_label → fact_sheet_id
        self._subtype_ids: Dict[Tuple[str, str], str] = {}  # (domain_label, subtype_label) → fact_sheet_id

    def parse_xml(self):
        """Parse the XML file"""
        print(f"Parsing {self.xml_file}...")
        try:
            self.tree = ET.parse(self.xml_file)
            self.root = self.tree.getroot()
            # Build parent map for efficient parent lookups
            self.parent_map = {child: parent for parent in self.root.iter() for child in parent}
        except ET.ParseError as e:
            print(f"❌ Error parsing XML: {e}")
            raise
        except FileNotFoundError:
            print(f"❌ File not found: {self.xml_file}")
            raise
        
    def extract_all(self):
        """Extract all assets and relationships"""
        self.extract_groups()
        self.extract_assets()
        self._detect_type3_domains()
        self.extract_relationships()
        self.enrich_relationships()
        self._assign_subgroups()
        self._build_container_ids()
        
    def extract_groups(self):
        """Extract group containers (like PARTY, AGREEMENTS, etc.)

        Two types of group container exist in the draw.io XML:

        Type 1 — bare mxCell with group style (most domains):
            <mxCell id="412" style="group" vertex="1" parent="1"/>

        Type 2 — object-wrapped mxCell with group style (PARTY domain):
            <object id="409" type="factSheet" ...>
              <mxCell style="...group;" vertex="1" parent="1"/>
            </object>

        The original code only detected Type 1. This fix detects both.
        """
        group_parents: Dict[str, str] = {}

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

        # Label each group from its first factSheet child; capture fact_sheet_id
        _group_fact_sheet_ids: Dict[str, str] = {}
        for group_id in group_parents:
            for obj in self.root.iter('object'):
                obj_cell = obj.find('mxCell')
                if obj_cell is not None and obj_cell.get('parent') == group_id:
                    label = obj.get('label', '')
                    if label and obj.get('type') == 'factSheet':
                        self.groups[group_id] = self.clean_label(label)
                        _group_fact_sheet_ids[group_id] = obj.get('factSheetId', '') or ''
                        break

        self._group_fact_sheet_ids = _group_fact_sheet_ids
        # Store parent chain for use by _assign_subgroups() in Enhancement 1b
        self._group_parents = group_parents
    
    def extract_assets(self):
        """Extract all fact sheet assets"""
        for obj in self.root.iter('object'):
            if obj.get('type') == 'factSheet':
                # Skip object-wrapped group containers (Type 2 groups detected in
                # extract_groups). They are structural containers, not leaf entities.
                # Their entity content is represented by a child factSheet inside them.
                if obj.get('id') in self._group_parents:
                    continue
                asset = self.parse_asset(obj)
                if asset:
                    self.assets[asset.id] = asset

        print(f"Extracted {len(self.assets)} assets")
        
    def parse_asset(self, obj: ET.Element) -> Optional[LeanIXAsset]:
        """Parse a single asset from object element"""
        obj_id = obj.get('id')
        if not obj_id:
            return None
            
        mxcell = obj.find('mxCell')
        if mxcell is None:
            return None
            
        # Extract geometry
        geometry = mxcell.find('mxGeometry')
        x = y = width = height = None
        if geometry is not None:
            x = float(geometry.get('x', 0)) if geometry.get('x') else None
            y = float(geometry.get('y', 0)) if geometry.get('y') else None
            width = float(geometry.get('width', 0)) if geometry.get('width') else None
            height = float(geometry.get('height', 0)) if geometry.get('height') else None
            
        # Determine parent group
        parent_id = mxcell.get('parent')
        parent_group = self.groups.get(parent_id)

        # Handle nested groups: if parent is a group that is itself nested inside
        # another group (e.g. Static Data / Time Bounded Groupings inside REFERENCE
        # DATA), elevate domain to the top-level group and use the intermediate
        # group label as the pre-assigned subgroup.
        pre_subgroup: Optional[str] = None
        if parent_group is not None:
            grandparent_id = self._group_parents.get(parent_id)
            if grandparent_id and grandparent_id in self.groups:
                parent_group = self.groups[grandparent_id]
                pre_subgroup = self.groups.get(parent_id)

        # Clean label (remove HTML tags and decode entities)
        raw_label = obj.get('label', '')
        label = self.clean_label(raw_label)

        return LeanIXAsset(
            id=obj_id,
            label=label,
            fact_sheet_type=obj.get('factSheetType', 'Unknown'),
            fact_sheet_id=obj.get('factSheetId', ''),
            parent_group=parent_group,
            parent_id=parent_id,
            subgroup=pre_subgroup,
            x=x,
            y=y,
            width=width,
            height=height,
            style=mxcell.get('style', ''),
            raw_attributes=dict(obj.attrib)
        )
    
    def extract_relationships(self):
        """Extract all relationships (edges) between assets"""
        for mxcell in self.root.iter('mxCell'):
            if mxcell.get('edge') == '1':
                relationship = self.parse_relationship(mxcell)
                if relationship:
                    self.relationships.append(relationship)
                    
        print(f"Extracted {len(self.relationships)} relationships")
        
    def parse_relationship(self, mxcell: ET.Element) -> Optional[LeanIXRelationship]:
        """Parse a single relationship from mxCell element"""
        source_id = mxcell.get('source')
        target_id = mxcell.get('target')
        
        if not source_id or not target_id:
            return None
            
        # Only create relationship if both source and target are known assets
        if source_id not in self.assets or target_id not in self.assets:
            return None
            
        style = mxcell.get('style', '')
        
        # Extract relationship type and cardinality from style
        relationship_type = self.extract_relationship_type(style)
        cardinality = self.extract_cardinality(style)
        
        return LeanIXRelationship(
            id=mxcell.get('id', ''),
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            cardinality=cardinality,
            style=style
        )
    
    def enrich_relationships(self):
        """Add labels to relationships"""
        for rel in self.relationships:
            if rel.source_id in self.assets:
                rel.source_label = self.assets[rel.source_id].label
            if rel.target_id in self.assets:
                rel.target_label = self.assets[rel.target_id].label
    
    def clean_label(self, label: str) -> str:
        """Clean HTML tags and decode entities from label"""
        if not label:
            return ""
        # Remove HTML tags
        label = re.sub(r'<[^>]+>', '', label)
        # Decode common HTML entities
        label = label.replace('&amp;', '&')
        label = label.replace('&lt;', '<')
        label = label.replace('&gt;', '>')
        label = label.replace('&nbsp;', ' ')
        label = label.replace('&#10;', '\n')
        # Clean up whitespace
        label = ' '.join(label.split())
        return label.strip()
    
    def extract_relationship_type(self, style: str) -> Optional[str]:
        """Extract relationship type from style attribute"""
        if 'edgeStyle=entityRelationEdgeStyle' in style:
            return "Entity Relationship"
        elif 'edgeStyle=orthogonalEdgeStyle' in style:
            return "Orthogonal"
        elif 'edgeStyle=elbowEdgeStyle' in style:
            return "Elbow"
        return None
    
    def extract_cardinality(self, style: str) -> Optional[str]:
        """Extract cardinality from endArrow/startArrow attributes"""
        cardinality_parts = []
        
        # Check start arrow
        if 'startArrow=ERzeroToMany' in style:
            cardinality_parts.append("0..*")
        elif 'startArrow=ERoneToMany' in style:
            cardinality_parts.append("1..*")
        elif 'startArrow=ERoneToOne' in style:
            cardinality_parts.append("1..1")
        elif 'startArrow=ERzeroToOne' in style:
            cardinality_parts.append("0..1")
            
        cardinality_parts.append("-")
        
        # Check end arrow
        if 'endArrow=ERzeroToMany' in style:
            cardinality_parts.append("0..*")
        elif 'endArrow=ERoneToMany' in style:
            cardinality_parts.append("1..*")
        elif 'endArrow=ERoneToOne' in style:
            cardinality_parts.append("1..1")
        elif 'endArrow=ERzeroToOne' in style:
            cardinality_parts.append("0..1")
            
        if len(cardinality_parts) > 1:
            return "".join(cardinality_parts)
        return None
    
    def to_dict(self) -> Dict:
        """Convert extracted data to dictionary"""
        return {
            "metadata": {
                "source_file": str(self.xml_file),
                "total_assets": len(self.assets),
                "total_relationships": len(self.relationships),
                "asset_types": list(set(a.fact_sheet_type for a in self.assets.values()))
            },
            "assets": [asdict(asset) for asset in self.assets.values()],
            "relationships": [asdict(rel) for rel in self.relationships]
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    # ------------------------------------------------------------------
    # Structured output (JSON + Markdown)
    # ------------------------------------------------------------------

    def to_entities_rows(self) -> List[Dict]:
        """Return flat list of leaf entity rows.

        Excludes domain root labels and subgroup container labels (detected via
        the same geometry logic used in _assign_subgroups).  Each row has:
            domain, domain_fact_sheet_id,
            subtype, subtype_fact_sheet_id,
            entity_name, fact_sheet_id, fact_sheet_type
        """
        by_group: Dict[str, List[LeanIXAsset]] = defaultdict(list)
        for asset in self.assets.values():
            by_group[asset.parent_group or ""].append(asset)

        rows: List[Dict] = []
        seen: set = set()

        for domain in sorted(by_group.keys()):
            group_assets = by_group[domain]
            # Subgroup container labels: any label that appears as another asset's subgroup
            used_subgroups = {a.subgroup for a in group_assets if a.subgroup}
            leaf_entities = [
                a for a in group_assets
                if a.label.upper() != (domain.upper() if domain else "")
                and a.label not in used_subgroups
            ]
            for asset in sorted(leaf_entities, key=lambda a: (a.subgroup or "", a.label)):
                key = asset.label.lower()
                if key in seen:
                    continue
                seen.add(key)
                subtype = asset.subgroup or ""
                rows.append({
                    "domain": domain,
                    "domain_fact_sheet_id": self._domain_ids.get(domain, ""),
                    "subtype": subtype,
                    "subtype_fact_sheet_id": self._subtype_ids.get((domain, subtype), "") if subtype else "",
                    "entity_name": asset.label,
                    "fact_sheet_id": asset.fact_sheet_id or "",
                    "fact_sheet_type": asset.fact_sheet_type or "",
                })
        return rows

    def to_relationships_rows(self) -> List[Dict]:
        """Return flat list of relationship rows.

        Each row has:
            source_entity, source_domain, target_entity, target_domain,
            cardinality, relationship_type
        """
        rows: List[Dict] = []
        for rel in self.relationships:
            src = self.assets.get(rel.source_id)
            tgt = self.assets.get(rel.target_id)
            rows.append({
                "source_entity": rel.source_label or "",
                "source_domain": src.parent_group if src else "",
                "target_entity": rel.target_label or "",
                "target_domain": tgt.parent_group if tgt else "",
                "cardinality": rel.cardinality or "",
                "relationship_type": rel.relationship_type or "",
            })
        return rows

    def to_model_json(self, indent: int = 2) -> str:
        """Return a structured JSON representation of the model.

        Produces a single JSON document containing metadata, all leaf entities,
        and all relationships.  This is the canonical structured output for
        consumer scripts — structured, self-describing, and suitable for RAG.

        Schema:
            {
              "metadata": {
                "model_name": str,
                "source_file": str,
                "entity_count": int,
                "relationship_count": int
              },
              "entities": [
                {
                  "domain": str,
                  "domain_fact_sheet_id": str,   # LeanIX UUID of the domain container
                  "subtype": str,                # visual subgroup label, may be ""
                  "subtype_fact_sheet_id": str,  # LeanIX UUID of the subtype container, may be ""
                  "entity_name": str,
                  "fact_sheet_id": str,          # LeanIX UUID of the entity itself
                  "fact_sheet_type": str
                }
              ],
              "relationships": [
                {
                  "source_entity": str,
                  "source_domain": str,
                  "target_entity": str,
                  "target_domain": str,
                  "cardinality": str,
                  "relationship_type": str
                }
              ]
            }
        """
        entity_rows = self.to_entities_rows()
        rel_rows = self.to_relationships_rows()
        doc = {
            "metadata": {
                "model_name": self.model_name,
                "source_file": self.xml_file.name,
                "entity_count": len(entity_rows),
                "relationship_count": len(rel_rows),
            },
            "entities": entity_rows,
            "relationships": rel_rows,
        }
        return json.dumps(doc, indent=indent, ensure_ascii=False)

    def to_flat_markdown(self) -> str:
        """Per-entity Markdown for RAG ingestion.

        Each entity gets its own ## heading so the chunker produces one chunk
        per entity — no character-count splitting needed.  Every chunk is
        self-contained: it carries domain, subtype, entity name, and LeanIX ID.
        """
        md: List[str] = [f"# {self.model_name} — Entity Catalogue\n\n"]
        for row in self.to_entities_rows():
            md.append(f"## {row['entity_name']}\n\n")
            md.append(f"- **Domain:** {row['domain']}\n")
            if row["subtype"]:
                md.append(f"- **Subtype:** {row['subtype']}\n")
            if row["fact_sheet_id"]:
                md.append(f"- **LeanIX ID:** `{row['fact_sheet_id']}`\n")
            if row["fact_sheet_type"]:
                md.append(f"- **Type:** {row['fact_sheet_type']}\n")
            md.append("\n")
        return "".join(md)

    def to_flat_relationships_markdown(self) -> str:
        """Per-relationship Markdown for RAG ingestion."""
        md: List[str] = [f"# {self.model_name} — Relationships\n\n"]
        for row in self.to_relationships_rows():
            md.append(f"## {row['source_entity']} → {row['target_entity']}\n\n")
            if row["source_domain"]:
                md.append(f"- **Source domain:** {row['source_domain']}\n")
            if row["target_domain"]:
                md.append(f"- **Target domain:** {row['target_domain']}\n")
            if row["cardinality"]:
                md.append(f"- **Cardinality:** {row['cardinality']}\n")
            if row["relationship_type"]:
                md.append(f"- **Type:** {row['relationship_type']}\n")
            md.append("\n")
        return "".join(md)

    def to_markdown(self) -> str:
        """Convert to sentence-format Markdown optimised for RAG ingestion.

        UUIDs are intentionally omitted — they are preserved in the JSON output
        for LeanIX roundtripping. This file is optimised for semantic embedding:
        each section is self-contained so any chunk retrieved by the RAG system
        carries full domain context.
        """
        md = []

        # Build domain → member list mapping
        assets_by_group: Dict[str, List[LeanIXAsset]] = defaultdict(list)
        for asset in self.assets.values():
            group = asset.parent_group or "Uncategorized"
            assets_by_group[group].append(asset)

        # Separate Uncategorized for special handling
        uncategorized_assets = assets_by_group.pop("Uncategorized", [])
        domain_names = sorted(assets_by_group.keys())

        # ── Overview ──────────────────────────────────────────────────────────
        md.append(f"# {self.model_name}\n\n")
        md.append(
            f"The {self.model_name} (source: {self.xml_file.name}) "
            f"contains {len(self.assets)} DataObject entities organised into "
            f"{len(domain_names)} domain groups: {', '.join(domain_names)}. "
            f"These domains are connected through {len(self.relationships)} entity relationships. "
            "The model captures the key data objects, parties, agreements, products, transactions, "
            f"channels, locations, and reference data that underpin {self.org_name}'s "
            "operations.\n\n"
        )

        # ── One section per domain ────────────────────────────────────────────
        for group_name in domain_names:
            group_assets = sorted(assets_by_group[group_name], key=lambda a: a.label)
            # Exclude the root node (same name as group) from the member list
            members = [a.label for a in group_assets if a.label.upper() != group_name.upper()]

            md.append(f"## {group_name} Domain\n\n")

            member_str = ", ".join(members) if members else "no sub-entities defined"
            md.append(
                f"The {group_name} domain contains {len(group_assets)} entities in the "
                f"{self.model_name}. "
                f"The entities within this domain are: {member_str}.\n\n"
            )

        # ── Uncategorized entities (Party types, Channels, Accounts, Assets) ──
        if uncategorized_assets:
            # Group uncategorized by common patterns
            party_types = []
            channel_types = []
            account_types = []
            asset_types = []
            other = []

            for asset in uncategorized_assets:
                label = asset.label.lower()
                if any(p in label for p in ['player', 'club', 'team', 'individual', 'organisation', 'employee', 'customer', 'member', 'official', 'learner', 'prospect', 'supplier', 'county', 'charity', 'government', 'school', 'authority', 'candidate', 'mentor', 'developer', 'household', 'unit', 'supporter', 'attendee']):
                    party_types.append(asset.label)
                elif any(c in label for c in ['channel', 'broadcast', 'streaming', 'tv', 'radio', 'sms', 'email', 'mobile', 'web', 'portal', 'social', 'push', 'live', 'chat', 'call centre', 'concierge', 'in person', 'pos', 'turnstile', 'merchandise']):
                    channel_types.append(asset.label)
                elif 'account' in label:
                    account_types.append(asset.label)
                elif 'asset' in label or 'data' in label or 'property' in label:
                    asset_types.append(asset.label)
                else:
                    other.append(asset.label)

            md.append("## Additional Model Entities\n\n")
            md.append(
                f"The following entities are defined in the {self.model_name} "
                "and include key party, channel, account, and asset entities.\n\n"
            )

            if party_types:
                md.append(f"**Party Types ({len(party_types)} entities):** {', '.join(sorted(party_types))}.\n\n")
            if channel_types:
                md.append(f"**Channel Types ({len(channel_types)} entities):** {', '.join(sorted(channel_types))}.\n\n")
            if account_types:
                md.append(f"**Account Types ({len(account_types)} entities):** {', '.join(sorted(account_types))}.\n\n")
            if asset_types:
                md.append(f"**Asset Types ({len(asset_types)} entities):** {', '.join(sorted(asset_types))}.\n\n")
            if other:
                md.append(f"**Other Entities ({len(other)} entities):** {', '.join(sorted(other))}.\n\n")

        # ── Relationships as natural language ─────────────────────────────────
        if self.relationships:
            md.append("## Entity Relationships\n\n")
            md.append(
                f"The following relationships define how the domain groups in the "
                f"{self.model_name} connect to one another.\n\n"
            )

            rels_by_source: Dict[str, List[LeanIXRelationship]] = defaultdict(list)
            for rel in self.relationships:
                rels_by_source[rel.source_label or rel.source_id].append(rel)

            for source_label in sorted(rels_by_source.keys()):
                rels = rels_by_source[source_label]

                # List up to 8 representative members of the source domain
                source_members = sorted(
                    a.label for a in self.assets.values()
                    if a.parent_group == source_label and a.label.upper() != source_label.upper()
                )
                source_sample = source_members[:8]
                source_ctx = (
                    f" (including {', '.join(source_sample)}"
                    f"{'...' if len(source_members) > 8 else ''})"
                    if source_sample else ""
                )

                for rel in sorted(rels, key=lambda r: r.target_label or ""):
                    target_label = rel.target_label or rel.target_id
                    cardinality_desc = self._describe_cardinality(rel.cardinality)

                    # List up to 8 representative members of the target domain
                    target_members = sorted(
                        a.label for a in self.assets.values()
                        if a.parent_group == target_label and a.label.upper() != target_label.upper()
                    )
                    target_sample = target_members[:8]
                    target_ctx = (
                        f" (including {', '.join(target_sample)}"
                        f"{'...' if len(target_members) > 8 else ''})"
                        if target_sample else ""
                    )

                    md.append(
                        f"{source_label}{source_ctx} {cardinality_desc} "
                        f"{target_label}{target_ctx}.\n\n"
                    )

        return "".join(md)

    def _describe_cardinality(self, cardinality: Optional[str]) -> str:
        """Convert cardinality notation to a natural language phrase."""
        mapping = {
            "0..*-0..*": "relates to (zero or more to zero or more)",
            "1..*-0..*": "relates to (one or more to zero or more)",
            "0..*-1..*": "relates to (zero or more to one or more)",
            "1..1-0..*": "relates to (exactly one to zero or more)",
            "0..*-1..1": "relates to (zero or more to exactly one)",
            "1..1-1..1": "relates to (exactly one to exactly one)",
        }
        if cardinality and cardinality in mapping:
            return mapping[cardinality]
        return f"relates to ({cardinality})" if cardinality else "relates to"
    
    def _detect_type3_domains(self):
        """Detect domains that use no draw.io group mechanism (Type 3).

        CHANNEL, ACCOUNTS, and ASSETS are laid out without draw.io group containers:
        every element — domain root label, subgroup rectangles, and leaf entities —
        has parent=1 (the canvas root) with purely visual nesting via absolute
        bounding-box geometry.

        Algorithm:
          1. Collect all factSheet assets at parent=1 with no parent_group.
          2. Sort by area descending.
          3. An element is a domain root if its centre is not contained within
             any larger element at the same level.
          4. Assign all elements whose centre falls inside a domain root's bbox
             to that domain (parent_group = domain label, parent_id = domain id).
          5. Remove domain roots from self.assets (structural containers, not
             leaf entities) and register them in self.groups so that
             _assign_subgroups() processes them normally.
        """
        # Ungrouped assets: at parent=1 with no group assignment yet
        ungrouped = [
            a for a in self.assets.values()
            if a.parent_id == '1' and a.parent_group is None
            and a.x is not None and a.y is not None
        ]
        if not ungrouped:
            return

        # Sort largest-first so the containment check hits domain roots quickly
        sorted_by_area = sorted(
            ungrouped,
            key=lambda a: (a.width or 0) * (a.height or 0),
            reverse=True,
        )

        # Domain roots: elements whose bounding box is NOT fully enclosed by any
        # other element.  Using full-bbox containment (not centre-point) avoids
        # false positives when a wide domain root's centre happens to fall inside
        # one of its own child rectangles (observed for CHANNEL and ASSETS).
        domain_roots: List[LeanIXAsset] = []
        for candidate in sorted_by_area:
            cx1 = candidate.x or 0
            cy1 = candidate.y or 0
            cx2 = cx1 + (candidate.width or 0)
            cy2 = cy1 + (candidate.height or 0)
            fully_inside = False
            for other in sorted_by_area:
                if other.id == candidate.id:
                    continue
                ox1 = other.x or 0
                oy1 = other.y or 0
                ox2 = ox1 + (other.width or 0)
                oy2 = oy1 + (other.height or 0)
                if ox1 <= cx1 and cx2 <= ox2 and oy1 <= cy1 and cy2 <= oy2:
                    fully_inside = True
                    break
            if not fully_inside:
                domain_roots.append(candidate)

        if not domain_roots:
            return

        print(f"Detected {len(domain_roots)} Type-3 domain(s): "
              f"{[r.label for r in domain_roots]}")

        # Assign children and register domains
        for root in domain_roots:
            rx, ry = (root.x or 0), (root.y or 0)
            rw, rh = (root.width or 0), (root.height or 0)
            for asset in ungrouped:
                if asset.id == root.id:
                    continue
                cx = (asset.x or 0) + (asset.width or 0) / 2
                cy = (asset.y or 0) + (asset.height or 0) / 2
                if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                    asset.parent_group = root.label
                    asset.parent_id = root.id  # virtual reparent for _assign_subgroups

            # Register in groups dict and remove domain root from assets
            self.groups[root.id] = root.label
            self._group_fact_sheet_ids[root.id] = root.fact_sheet_id or ''
            del self.assets[root.id]

    def _build_container_ids(self):
        """Populate _domain_ids and _subtype_ids from captured group fact sheet IDs.

        Must be called after _assign_subgroups() so that asset.subgroup is set.

        Sources:
          - Type 1 / 2 groups (draw.io group containers) → _group_fact_sheet_ids,
            distinguished by whether their parent is '1' (domain) or another group (subtype).
          - Type 3 domain roots (visual containment, no draw.io group) → also in
            _group_fact_sheet_ids, populated during _detect_type3_domains().
          - Type 3 subgroup containers (large rectangles inside a Type 3 domain) →
            remain in self.assets; identified by asset.label appearing as a subgroup
            value on another asset in the same domain.
        """
        # Pass 1: draw.io group containers (Types 1, 2, and 3 domain roots)
        for group_id, group_label in self.groups.items():
            fid = self._group_fact_sheet_ids.get(group_id, '')
            parent_of_group = self._group_parents.get(group_id, '1')
            if parent_of_group == '1':
                # Top-level domain
                self._domain_ids[group_label] = fid
            elif parent_of_group in self.groups:
                # Nested subtype group (e.g. Static Data inside REFERENCE DATA)
                parent_label = self.groups[parent_of_group]
                grandparent = self._group_parents.get(parent_of_group, '1')
                if grandparent in self.groups:
                    # 3-level nesting (not expected): treat parent as domain, current as subtype
                    domain_label = self.groups[grandparent]
                    self._subtype_ids[(domain_label, parent_label)] = self._group_fact_sheet_ids.get(parent_of_group, '')
                else:
                    self._subtype_ids[(parent_label, group_label)] = fid

        # Pass 2: Type 3 visual subgroup containers (assets filtered from leaf entities)
        by_group: Dict[str, List[LeanIXAsset]] = defaultdict(list)
        for asset in self.assets.values():
            by_group[asset.parent_group or ""].append(asset)

        for domain, group_assets in by_group.items():
            if not domain:
                continue
            used_subgroups = {a.subgroup for a in group_assets if a.subgroup}
            for asset in group_assets:
                if asset.label in used_subgroups and (domain, asset.label) not in self._subtype_ids:
                    self._subtype_ids[(domain, asset.label)] = asset.fact_sheet_id or ''

    def _assign_subgroups(self):
        """Assign leaf entities to their visual subgroup using spatial containment.

        All domain groups in this model use large rectangles as visual subgroup
        containers and 100x40 boxes as leaf entities.  Both are detected purely
        from parsed geometry — no hardcoded group IDs or coordinates.

        Discriminator (verified across all domains):
            subgroup container: width > 100  AND height > 40
            leaf entity:        width <= 100  OR height <= 40

        Edge case confirmed: "Targeted Promotion" in CAMPAIGN is 102x40 — height
        is not > 40, so it is correctly treated as a leaf entity.
        """
        for group_id, domain_name in self.groups.items():
            if not domain_name:
                continue

            subgroup_boxes: List[Tuple[str, float, float, float, float]] = []
            leaf_assets: List[LeanIXAsset] = []

            for asset in self.assets.values():
                if asset.parent_id != group_id:
                    continue
                if asset.label.upper() == domain_name.upper():
                    continue  # skip the root domain label node

                w = asset.width or 0
                h = asset.height or 0

                if w > 100 and h > 40:
                    subgroup_boxes.append(
                        (asset.label, asset.x or 0, asset.y or 0, w, h)
                    )
                else:
                    leaf_assets.append(asset)

            if not subgroup_boxes:
                continue  # domain has no visual subgroups (e.g. LOCATION)

            # Assign each leaf to the subgroup whose bounding box contains its centre
            for asset in leaf_assets:
                cx = (asset.x or 0) + (asset.width or 0) / 2
                cy = (asset.y or 0) + (asset.height or 0) / 2
                for (sg_name, sg_x, sg_y, sg_w, sg_h) in subgroup_boxes:
                    if sg_x <= cx <= sg_x + sg_w and sg_y <= cy <= sg_y + sg_h:
                        asset.subgroup = sg_name
                        break

    def _sanitize_section_key(self, name: str) -> str:
        """Sanitize a domain name into a valid section key for use in collection names."""
        key = name.lower()
        key = re.sub(r'[^a-z0-9]+', '_', key)
        key = key.strip('_')
        return key

    def to_section_files(self) -> Dict[str, str]:
        """Generate section-specific Markdown, one entry per logical domain + relationships.

        Produces focused, self-contained documents suitable for loading into separate
        ChromaDB collections. This avoids the chunking fragmentation that occurs when
        relationships and entity lists are interleaved in a single large Markdown file.

        Returns:
            Dict mapping section_key → markdown_content. Keys are sanitized domain
            names (e.g. 'agreements', 'product', 'transaction_and_events') plus
            'overview', 'additional_entities', and 'relationships'.
        """
        sections: Dict[str, str] = {}

        # Build domain → assets mapping
        assets_by_group: Dict[str, List[LeanIXAsset]] = defaultdict(list)
        for asset in self.assets.values():
            group = asset.parent_group or "Uncategorized"
            assets_by_group[group].append(asset)
        uncategorized_assets = assets_by_group.pop("Uncategorized", [])
        domain_names = sorted(assets_by_group.keys())

        # ── Overview ──────────────────────────────────────────────────────────
        md: List[str] = []
        md.append(f"# {self.model_name} — Overview\n\n")
        md.append(
            f"The {self.model_name} (source: {self.xml_file.name}) "
            f"contains {len(self.assets)} DataObject entities organised into "
            f"{len(domain_names)} named domain groups: {', '.join(domain_names)}. "
            f"These domains are connected through {len(self.relationships)} entity "
            f"relationships.\n\n"
        )
        for group_name in domain_names:
            group_assets = assets_by_group[group_name]
            # Exclude domain root label and labels actively used as subgroup headings.
            # Geometry-only filtering is avoided: some entities (e.g. Team, Household)
            # have wider boxes but are genuine entities, not containers.
            used_subgroups = {a.subgroup for a in group_assets if a.subgroup}
            leaf_count = sum(
                1 for a in group_assets
                if a.label.upper() != group_name.upper()
                and a.label not in used_subgroups
            )
            md.append(f"The **{group_name}** domain contains {leaf_count} entities.\n\n")
        sections["overview"] = "".join(md)

        # ── One section per domain ────────────────────────────────────────────
        for group_name in domain_names:
            group_assets = sorted(assets_by_group[group_name], key=lambda a: a.label)
            # Exclude domain root label and labels actively used as subgroup headings.
            # A label that no entity references as its subgroup is a genuine entity.
            used_subgroups = {a.subgroup for a in group_assets if a.subgroup}
            leaf_entities = [
                a for a in group_assets
                if a.label.upper() != group_name.upper()
                and a.label not in used_subgroups
            ]

            md = []
            md.append(f"# {group_name} Domain — {self.model_name}\n\n")
            md.append(
                f"The {group_name} domain is part of the {self.model_name}. "
                f"It contains {len(leaf_entities)} entities.\n\n"
            )
            if leaf_entities:
                md.append(f"The entities within the {group_name} domain are:\n\n")
                has_subgroups = any(a.subgroup for a in leaf_entities)
                if has_subgroups:
                    by_subgroup: Dict[str, List[LeanIXAsset]] = defaultdict(list)
                    unassigned: List[LeanIXAsset] = []
                    for asset in leaf_entities:
                        if asset.subgroup:
                            by_subgroup[asset.subgroup].append(asset)
                        else:
                            unassigned.append(asset)
                    for sg_name in sorted(by_subgroup.keys()):
                        md.append(f"## {sg_name} Subgroup\n\n")
                        for asset in sorted(by_subgroup[sg_name], key=lambda a: a.label):
                            fsid = f" *(LeanIX ID: `{asset.fact_sheet_id}`)*" if asset.fact_sheet_id else ""
                            md.append(f"- **{asset.label}**{fsid}\n")
                        md.append("\n")
                    for asset in sorted(unassigned, key=lambda a: a.label):
                        fsid = f" *(LeanIX ID: `{asset.fact_sheet_id}`)*" if asset.fact_sheet_id else ""
                        md.append(f"- **{asset.label}**{fsid}\n")
                    if unassigned:
                        md.append("\n")
                else:
                    for asset in leaf_entities:
                        fsid = f" *(LeanIX ID: `{asset.fact_sheet_id}`)*" if asset.fact_sheet_id else ""
                        md.append(f"- **{asset.label}**{fsid}\n")
                    md.append("\n")

            # Include relationships that touch this domain (for co-location context)
            domain_rels = [
                r for r in self.relationships
                if r.source_label == group_name or r.target_label == group_name
            ]
            if domain_rels:
                md.append(f"## {group_name} Domain Relationships\n\n")
                for rel in sorted(domain_rels, key=lambda r: r.target_label or ""):
                    source = rel.source_label or rel.source_id
                    target = rel.target_label or rel.target_id
                    cardinality_desc = self._describe_cardinality(rel.cardinality)
                    md.append(f"- **{source}** {cardinality_desc} **{target}**\n")
                md.append("\n")

            section_key = self._sanitize_section_key(group_name)
            sections[section_key] = "".join(md)

        # ── Additional entities (uncategorized: party types, channels, etc.) ──
        if uncategorized_assets:
            party_types: List[str] = []
            channel_types: List[str] = []
            account_types: List[str] = []
            asset_types: List[str] = []
            other: List[str] = []

            for asset in uncategorized_assets:
                label = asset.label.lower()
                if any(p in label for p in [
                    'player', 'club', 'team', 'individual', 'organisation', 'employee',
                    'customer', 'member', 'official', 'learner', 'prospect', 'supplier',
                    'county', 'charity', 'government', 'school', 'authority', 'candidate',
                    'mentor', 'developer', 'household', 'unit', 'supporter', 'attendee',
                ]):
                    party_types.append(asset.label)
                elif any(c in label for c in [
                    'channel', 'broadcast', 'streaming', 'tv', 'radio', 'sms', 'email',
                    'mobile', 'web', 'portal', 'social', 'push', 'live', 'chat',
                    'call centre', 'concierge', 'in person', 'pos', 'turnstile', 'merchandise',
                ]):
                    channel_types.append(asset.label)
                elif 'account' in label:
                    account_types.append(asset.label)
                elif 'asset' in label or 'data' in label or 'property' in label:
                    asset_types.append(asset.label)
                else:
                    other.append(asset.label)

            md = []
            md.append(f"# Additional Entities — {self.model_name}\n\n")
            md.append(
                f"The following entities are defined in the {self.model_name} "
                "and include key party, channel, account, and asset entities that form the "
                f"core of {self.org_name}'s data landscape.\n\n"
            )
            if party_types:
                md.append(
                    f"**Party Types ({len(party_types)} entities):** "
                    f"{', '.join(sorted(party_types))}.\n\n"
                )
            if channel_types:
                md.append(
                    f"**Channel Types ({len(channel_types)} entities):** "
                    f"{', '.join(sorted(channel_types))}.\n\n"
                )
            if account_types:
                md.append(
                    f"**Account Types ({len(account_types)} entities):** "
                    f"{', '.join(sorted(account_types))}.\n\n"
                )
            if asset_types:
                md.append(
                    f"**Asset Types ({len(asset_types)} entities):** "
                    f"{', '.join(sorted(asset_types))}.\n\n"
                )
            if other:
                md.append(
                    f"**Other Entities ({len(other)} entities):** "
                    f"{', '.join(sorted(other))}.\n\n"
                )
            sections["additional_entities"] = "".join(md)

        # ── Relationships: one headed section per relationship for clean chunking ──
        if self.relationships:
            md = []
            md.append(f"# Entity Relationships — {self.model_name}\n\n")
            md.append(
                f"This document lists all {len(self.relationships)} domain-level entity "
                f"relationships in the {self.model_name}. "
                "Each relationship section is self-contained: it names the source and target "
                "domains, states the cardinality, and lists representative entities from each "
                "domain so that any retrieved chunk carries full context.\n\n"
            )

            rels_by_source: Dict[str, List[LeanIXRelationship]] = defaultdict(list)
            for rel in self.relationships:
                rels_by_source[rel.source_label or rel.source_id].append(rel)

            for source_label in sorted(rels_by_source.keys()):
                for rel in sorted(rels_by_source[source_label], key=lambda r: r.target_label or ""):
                    target_label = rel.target_label or rel.target_id
                    cardinality_desc = self._describe_cardinality(rel.cardinality)

                    source_members = sorted(
                        a.label for a in self.assets.values()
                        if a.parent_group == source_label and a.label.upper() != source_label.upper()
                    )
                    target_members = sorted(
                        a.label for a in self.assets.values()
                        if a.parent_group == target_label and a.label.upper() != target_label.upper()
                    )

                    md.append(f"## Relationship: {source_label} → {target_label}\n\n")
                    md.append(
                        f"**{source_label}** {cardinality_desc} **{target_label}**.\n\n"
                    )
                    if source_members:
                        md.append(
                            f"The **{source_label}** domain includes entities: "
                            f"{', '.join(source_members[:12])}"
                            f"{'...' if len(source_members) > 12 else ''}.\n\n"
                        )
                    if target_members:
                        md.append(
                            f"The **{target_label}** domain includes entities: "
                            f"{', '.join(target_members[:12])}"
                            f"{'...' if len(target_members) > 12 else ''}.\n\n"
                        )
            sections["relationships"] = "".join(md)

        return sections

    def save_sections(self, output_dir: str, prefix: str = "") -> Dict[str, str]:
        """Write each section to a separate Markdown file in output_dir.

        Args:
            output_dir: Directory to write files into (created if it doesn't exist).
            prefix: Optional filename prefix (e.g. 'leanix_').

        Returns:
            Dict mapping section_key → absolute file path.
        """
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)

        sections = self.to_section_files()
        file_map: Dict[str, str] = {}

        for section_key, content in sections.items():
            filename = f"{prefix}{section_key}.md" if prefix else f"{section_key}.md"
            file_path = output_dir_path / filename
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            file_map[section_key] = str(file_path)
            print(f"  Saved section '{section_key}' → {file_path}")

        return file_map

    def save(self, output_path: str, format: str = "both"):
        """Save extracted data to file(s).

        Args:
            output_path: Output file path (used as stem for multi-file formats).
            format: 'json', 'markdown'/'md', 'both', or 'csv' (alias for structured JSON output).
                'csv' writes <stem>_model.json alongside
                <stem>_entities.md and <stem>_relationships.md for RAG ingestion.
        """
        output_path = Path(output_path)

        if format in ("json", "both"):
            json_file = output_path if format == "json" else output_path.with_suffix('.json')
            with open(json_file, 'w', encoding='utf-8') as f:
                f.write(self.to_json())
            print(f"Saved JSON to {json_file}")

        if format in ("markdown", "md", "both"):
            md_file = output_path if format in ("markdown", "md") else output_path.with_suffix('.md')
            with open(md_file, 'w', encoding='utf-8') as f:
                f.write(self.to_markdown())
            print(f"Saved Markdown to {md_file}")

        if format == "csv":
            # 'csv' is a legacy alias — outputs _model.json + flat markdowns (no CSV files)
            stem = output_path.stem
            parent = output_path.parent
            model_json = parent / f"{stem}_model.json"
            entities_md = parent / f"{stem}_entities.md"
            rels_md = parent / f"{stem}_relationships.md"
            model_json.write_text(self.to_model_json(), encoding="utf-8")
            entities_md.write_text(self.to_flat_markdown(), encoding="utf-8")
            rels_md.write_text(self.to_flat_relationships_markdown(), encoding="utf-8")
            rows = self.to_entities_rows()
            print(f"Saved model JSON to {model_json} ({len(rows)} entities, {len(self.relationships)} relationships)")
            print(f"Saved entities Markdown to {entities_md}")
            print(f"Saved relationships Markdown to {rels_md}")


def extract_leanix_file(input_path: str, output_path: str, format: str = "markdown") -> str:
    """Convenience function to extract LeanIX data and return output content.
    
    Args:
        input_path: Path to input XML file.
        output_path: Path for output file.
        format: Output format - 'json', 'markdown', 'md', or 'both'.
        
    Returns:
        Path to the primary output file.
    """
    extractor = LeanIXExtractor(input_path)
    extractor.parse_xml()
    extractor.extract_all()
    extractor.save(output_path, format)
    
    # Return the primary output file path
    if format in ("markdown", "md"):
        return str(Path(output_path).with_suffix('.md'))
    elif format == "json":
        return str(Path(output_path).with_suffix('.json'))
    else:
        # For 'both', return markdown as primary
        return str(Path(output_path).with_suffix('.md'))


def main():
    parser = argparse.ArgumentParser(
        description="Extract LeanIX inventory from draw.io XML export"
    )
    parser.add_argument(
        "input_file",
        help="Input draw.io XML file"
    )
    parser.add_argument(
        "-o", "--output",
        default="leanix_inventory",
        help="Output file path (without extension for multiple formats)"
    )
    parser.add_argument(
        "-f", "--format",
        choices=["json", "markdown", "md", "both"],
        default="both",
        help="Output format (default: both)"
    )
    
    args = parser.parse_args()
    
    # Extract
    extractor = LeanIXExtractor(args.input_file)
    extractor.parse_xml()
    extractor.extract_all()
    
    # Save
    extractor.save(args.output, args.format)
    
    # Print summary
    print("\n=== Summary ===")
    print(f"Total assets: {len(extractor.assets)}")
    print(f"Total relationships: {len(extractor.relationships)}")
    
    # Show asset types
    asset_types = defaultdict(int)
    for asset in extractor.assets.values():
        asset_types[asset.fact_sheet_type] += 1
    
    print("\nAsset types:")
    for atype, count in sorted(asset_types.items()):
        print(f"  {atype}: {count}")


if __name__ == "__main__":
    main()