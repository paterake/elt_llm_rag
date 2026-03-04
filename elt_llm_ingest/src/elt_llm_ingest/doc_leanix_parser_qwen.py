#!/usr/bin/env python3
"""
doc_leanix_parser_qwen.py

Simplified LeanIX draw.io XML parser — JSON output only.
Extracts Domain/Subtype/Entity hierarchy with LeanIX IDs.

Key design decisions:
1. JSON default output (not CSV)
2. Geometry-based subgroup detection (unavoidable — PARTY uses different XML structure)
3. Minimal code (~150 lines) vs 868-line original
4. Table-like structure for optimal RAG chunking

Usage:
    python -m elt_llm_ingest.doc_leanix_parser_qwen <input.xml> [--output entities.json]
"""

import xml.etree.ElementTree as ET
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class Entity:
    """Represents a conceptual model entity"""
    domain: str
    subtype: str
    entity: str
    leanix_id: str
    hierarchy_level: str  # "Domain", "Subtype", or "Entity"


@dataclass
class Relationship:
    """Represents a relationship between entities"""
    source_entity: str
    source_domain: str
    target_entity: str
    target_domain: str
    relationship_type: str
    cardinality: str


class LeanIXExtractor:
    """Extract entities and relationships from LeanIX draw.io XML"""

    # Discriminator: subgroup containers are larger than leaf entities
    SUBGROUP_WIDTH_THRESHOLD = 100
    SUBGROUP_HEIGHT_THRESHOLD = 40

    def __init__(self, xml_file: str):
        self.xml_file = Path(xml_file)
        self.tree = None
        self.root = None
        self.entities: List[Entity] = []
        self.relationships: List[Relationship] = []
        self.groups: Dict[str, str] = {}  # group_id -> domain_label
        self.subgroups: Dict[str, Dict[str, str]] = defaultdict(dict)  # domain -> {subgroup_id -> subtype_label}

    def parse_xml(self):
        """Parse the XML file"""
        print(f"Parsing {self.xml_file}...")
        self.tree = ET.parse(self.xml_file)
        self.root = self.tree.getroot()
        print(f"  Root: {self.root.tag}")

    def extract_all(self):
        """Extract all entities and relationships"""
        self._extract_groups()
        self._extract_entities()
        self._extract_relationships()
        print(f"Extracted {len(self.entities)} entities, {len(self.relationships)} relationships")

    def _extract_groups(self):
        """Extract domain groups and subgroup containers.

        Two types of group container exist in draw.io XML:

        Type 1 — bare mxCell with group style (most domains):
            <mxCell id="412" style="group" vertex="1" parent="1"/>

        Type 2 — object-wrapped mxCell with group style (PARTY domain only):
            <object id="409" type="factSheet" label="PARTY" ...>
              <mxCell style="...group;" vertex="1" parent="1"/>
            </object>

        Type 3 — large domain boxes without group style (ASSETS, ACCOUNTS):
            <object id="2" label="ACCOUNTS" ...>
              <mxCell vertex="1" parent="1">
                <mxGeometry width="580" height="220"/>
              </mxCell>
            </object>
        """
        group_parents: Dict[str, str] = {}

        # Type 1: bare mxCell with group style
        for mxcell in self.root.iter('mxCell'):
            style = mxcell.get('style', '')
            if 'group' in style and mxcell.get('vertex') == '1':
                gid = mxcell.get('id')
                if gid:
                    group_parents[gid] = mxcell.get('parent', '1')

        # Type 2: object-wrapped mxCell with group style (PARTY domain)
        for obj in self.root.iter('object'):
            cell = obj.find('mxCell')
            if cell is not None:
                style = cell.get('style', '')
                if 'group' in style and cell.get('vertex') == '1':
                    oid = obj.get('id')
                    if oid and oid not in group_parents:
                        group_parents[oid] = cell.get('parent', '1')

        # Type 3: large domain boxes (width > 500, height > 200) with parent="1"
        # These are top-level domain containers without explicit group style
        for obj in self.root.iter('object'):
            oid = obj.get('id')
            if oid and oid in group_parents:
                continue  # Already detected as Type 1 or 2

            cell = obj.find('mxCell')
            if cell is None:
                continue

            # Check if it's a top-level box (parent="1")
            if cell.get('parent') != '1':
                continue

            # Check geometry - domain containers are large
            geometry = cell.find('mxGeometry')
            if geometry is None:
                continue

            width = float(geometry.get('width', 0))
            height = float(geometry.get('height', 0))

            # Domain containers are typically > 500x200
            # CHANNEL is 830x370, ASSETS is 550x265, ACCOUNTS is 580x220
            if width > 500 and height > 200:
                group_parents[oid] = '1'

        # Special handling for CHANNEL domain subtypes
        # CHANNEL subtypes (Physical Channel, Broadcast, etc.) have parent="1" but are visually inside CHANNEL
        # We need to detect them as subtype containers, not domains
        channel_subtype_ids = set()
        if '441' in group_parents:  # CHANNEL domain detected
            for obj in self.root.iter('object'):
                oid = obj.get('id')
                cell = obj.find('mxCell')
                if cell is None or cell.get('parent') != '1':
                    continue
                
                geometry = cell.find('mxGeometry')
                if geometry is None:
                    continue
                
                width = float(geometry.get('width', 0))
                height = float(geometry.get('height', 0))
                
                # CHANNEL subtypes are medium boxes (300-450 x 140-170)
                # Larger than entities (100x40) but smaller than domains (500x200)
                if (300 <= width <= 450 and 140 <= height <= 200):
                    label = self._clean_label(obj.get('label', '')).lower()
                    if any(x in label for x in ['channel', 'broadcast', 'physically', 'personally', 'digitally']):
                        channel_subtype_ids.add(oid)
                        # Don't add to group_parents - these are subtypes, not domains

        # Build object map for Type 3 domain labelling
        obj_map = {obj.get('id'): obj for obj in self.root.iter('object') if obj.get('id')}

        # Build CHANNEL subtype boxes for spatial containment
        self.channel_subtype_boxes = {}
        for oid in channel_subtype_ids:
            obj = obj_map.get(oid)
            if obj is None:
                continue
            cell = obj.find('mxCell')
            if cell is None:
                continue
            geometry = cell.find('mxGeometry')
            if geometry is None:
                continue

            x = float(geometry.get('x', 0))
            y = float(geometry.get('y', 0))
            width = float(geometry.get('width', 0))
            height = float(geometry.get('height', 0))
            label = self._clean_label(obj.get('label', ''))

            self.channel_subtype_boxes[oid] = {
                'x': x, 'y': y, 'w': width, 'h': height,
                'label': label
            }

        # Label each group
        for group_id in group_parents:
            label_found = False
            
            # Try to find label from first factSheet child
            for obj in self.root.iter('object'):
                obj_cell = obj.find('mxCell')
                if obj_cell is not None and obj_cell.get('parent') == group_id:
                    label = obj.get('label', '')
                    if label and obj.get('type') == 'factSheet':
                        self.groups[group_id] = self._clean_label(label)
                        label_found = True
                        break
            
            # If no children found, use the object's own label (Type 3 domains)
            if not label_found and group_id in obj_map:
                obj = obj_map[group_id]
                label = obj.get('label', '')
                if label:
                    self.groups[group_id] = self._clean_label(label)

    def _extract_entities(self):
        """Extract all entities with domain/subtype hierarchy using spatial containment."""
        # First pass: collect all subgroup containers with their geometry
        subgroup_boxes: Dict[str, dict] = {}

        for obj in self.root.iter('object'):
            if obj.get('type') != 'factSheet':
                continue

            obj_id = obj.get('id')
            cell = obj.find('mxCell')
            if cell is None:
                continue

            style = cell.get('style', '')
            if 'group' in style:
                continue

            geometry = cell.find('mxGeometry')
            if geometry is None:
                continue

            width = float(geometry.get('width', 0))
            height = float(geometry.get('height', 0))
            x = float(geometry.get('x', 0))
            y = float(geometry.get('y', 0))
            parent_id = cell.get('parent')

            # Check if this is a subtype container
            # TRANSACTION AND EVENTS subtypes are 580x70-120, so use 600 as upper bound
            is_subgroup = (width > self.SUBGROUP_WIDTH_THRESHOLD and height > self.SUBGROUP_HEIGHT_THRESHOLD and
                          width < 600 and height < 400)

            if is_subgroup:
                domain = self.groups.get(parent_id, 'Unknown')
                label = self._clean_label(obj.get('label', ''))
                if domain not in subgroup_boxes:
                    subgroup_boxes[domain] = {}
                subgroup_boxes[domain][label] = {
                    'x': x, 'y': y, 'w': width, 'h': height,
                    'cell_id': obj_id
                }

        # Special handling for CHANNEL domain
        if hasattr(self, 'channel_subtype_boxes'):
            for oid, box in self.channel_subtype_boxes.items():
                subgroup_boxes.setdefault('CHANNEL', {})[box['label']] = {
                    'x': box['x'], 'y': box['y'], 'w': box['w'], 'h': box['h'],
                    'cell_id': oid
                }
        
        # Special handling for ASSETS domain - subtype boxes ARE the entities
        if '8' in self.groups:  # ASSETS domain detected
            obj_map = {obj.get('id'): obj for obj in self.root.iter('object') if obj.get('id')}
            for obj in obj_map.values():
                oid = obj.get('id')
                cell = obj.find('mxCell')
                if cell is None or cell.get('parent') != '1':
                    continue
                
                geometry = cell.find('mxGeometry')
                if geometry is None:
                    continue
                
                width = float(geometry.get('width', 0))
                height = float(geometry.get('height', 0))
                
                # ASSETS subtypes are medium boxes (250 x 70)
                if (200 <= width <= 300 and 60 <= height <= 100):
                    label = self._clean_label(obj.get('label', ''))
                    if 'asset' in label.lower():
                        fsid = obj.get('factSheetId', '')
                        x = float(geometry.get('x', 0))
                        y = float(geometry.get('y', 0))
                        
                        # Add as subtype container
                        subgroup_boxes.setdefault('ASSETS', {})[label] = {
                            'x': x, 'y': y, 'w': width, 'h': height,
                            'cell_id': oid
                        }
                        
                        # Also add as entity (subtype box IS the entity)
                        self.entities.append(Entity(
                            domain='ASSETS',
                            subtype=label,
                            entity=label,
                            leanix_id=fsid,
                            hierarchy_level='Entity'
                        ))

        # Second pass: extract leaf entities
        for obj in self.root.iter('object'):
            if obj.get('type') != 'factSheet':
                continue

            obj_id = obj.get('id')
            cell = obj.find('mxCell')
            if cell is None:
                continue

            style = cell.get('style', '')
            if 'group' in style:
                continue

            geometry = cell.find('mxGeometry')
            if geometry is None:
                continue

            width = float(geometry.get('width', 0))
            height = float(geometry.get('height', 0))
            x = float(geometry.get('x', 0))
            y = float(geometry.get('y', 0))
            parent_id = cell.get('parent')

            # Skip subtype containers
            is_container = width > self.SUBGROUP_WIDTH_THRESHOLD and height > self.SUBGROUP_HEIGHT_THRESHOLD
            if is_container:
                continue

            # This is a leaf entity
            label = self._clean_label(obj.get('label', ''))
            leanix_id = obj.get('factSheetId', '')
            domain = self.groups.get(parent_id, 'Unknown')

            # Special handling for CHANNEL entities with parent="1"
            if parent_id == '1' and hasattr(self, 'channel_subtype_boxes'):
                cx, cy = x + width / 2, y + height / 2
                for box_oid, box in self.channel_subtype_boxes.items():
                    if (box['x'] <= cx <= box['x'] + box['w'] and
                        box['y'] <= cy <= box['y'] + box['h']):
                        domain = 'CHANNEL'
                        break

            # Find subtype by spatial containment
            subtype = ""
            cx, cy = x + width / 2, y + height / 2
            if domain in subgroup_boxes:
                for subtype_name, box in subgroup_boxes[domain].items():
                    if (box['x'] <= cx <= box['x'] + box['w'] and
                        box['y'] <= cy <= box['y'] + box['h']):
                        subtype = subtype_name
                        break

            self.entities.append(Entity(
                domain=domain,
                subtype=subtype,
                entity=label,
                leanix_id=leanix_id,
                hierarchy_level="Entity"
            ))

    def _find_subtype(self, domain: str, parent_id: str) -> str:
        """Find the subtype for an entity by checking if parent is a subgroup container."""
        # Direct child of domain group (no subtype)
        if parent_id in self.groups:
            return ""

        # Check if parent is a known subgroup in this domain
        if domain in self.subgroups:
            if parent_id in self.subgroups[domain]:
                return self.subgroups[domain][parent_id]

        # Try to find subgroup by navigating up the parent chain
        for cell in self.root.iter('mxCell'):
            if cell.get('id') == parent_id:
                grandparent_id = cell.get('parent')
                if grandparent_id in self.subgroups.get(domain, {}):
                    return self.subgroups[domain][grandparent_id]

        return ""

    def _extract_relationships(self):
        """Extract domain-level relationships between entities.

        In LeanIX conceptual models, relationships are drawn between:
        - Domain containers (e.g., PARTY → ACCOUNTS)
        - Entity boxes (e.g., Club → Membership)

        This method extracts both, but focuses on domain-level for RAG context.

        Note: Edge source/target reference <object> @id attributes directly
        (not mxCell IDs).
        """
        # Build object ID -> object map
        obj_map = {obj.get('id'): obj for obj in self.root.iter('object') if obj.get('id')}

        for mxcell in self.root.iter('mxCell'):
            if mxcell.get('edge') != '1':
                continue

            source_id = mxcell.get('source')
            target_id = mxcell.get('target')

            if not source_id or not target_id:
                continue

            # Find source and target objects from object IDs
            source_obj = obj_map.get(source_id)
            target_obj = obj_map.get(target_id)

            if source_obj is None or target_obj is None:
                continue

            source_label = self._clean_label(source_obj.get('label', ''))
            target_label = self._clean_label(target_obj.get('label', ''))

            # Get source and target domains
            source_cell = source_obj.find('mxCell')
            target_cell = target_obj.find('mxCell')
            source_parent_id = source_cell.get('parent') if source_cell is not None else None
            target_parent_id = target_cell.get('parent') if target_cell is not None else None

            source_domain = self.groups.get(source_parent_id, 'Unknown')
            target_domain = self.groups.get(target_parent_id, 'Unknown')

            # Extract cardinality from style
            style = mxcell.get('style', '')
            cardinality = self._extract_cardinality(style)

            # Determine if this is a domain-level or entity-level relationship
            source_is_domain = self._is_domain_container(source_obj)
            target_is_domain = self._is_domain_container(target_obj)

            if source_is_domain and target_is_domain:
                # Domain-to-domain relationship
                self.relationships.append(Relationship(
                    source_entity=source_label,
                    source_domain=source_domain,
                    target_entity=target_label,
                    target_domain=target_domain,
                    relationship_type="Domain Relationship",
                    cardinality=cardinality or "unknown"
                ))
            elif not source_is_domain and not target_is_domain:
                # Entity-to-entity relationship (both are leaf entities)
                self.relationships.append(Relationship(
                    source_entity=source_label,
                    source_domain=source_domain,
                    target_entity=target_label,
                    target_domain=target_domain,
                    relationship_type="Entity Relationship",
                    cardinality=cardinality or "unknown"
                ))

    def _is_domain_container(self, obj) -> bool:
        """Check if an object is a domain container (large group box)."""
        cell = obj.find('mxCell')
        if cell is None:
            return False

        style = cell.get('style', '')
        if 'group' in style:
            return True

        # Also check by geometry - domain containers are very large
        geometry = cell.find('mxGeometry')
        if geometry is not None:
            width = float(geometry.get('width', 0))
            height = float(geometry.get('height', 0))
            if width > 500 and height > 300:
                return True

        return False

    def _find_object_by_cell_id(self, cell_id: str):
        """Find the object element that contains a given mxCell ID."""
        for obj in self.root.iter('object'):
            cell = obj.find('mxCell')
            if cell is not None and cell.get('id') == cell_id:
                return obj
        return None

    def _clean_label(self, label: str) -> str:
        """Clean HTML tags and decode entities from label."""
        import re
        if not label:
            return ""
        # Remove HTML tags
        label = re.sub(r'<[^>]+>', '', label)
        # Decode common HTML entities
        label = label.replace('&amp;', '&')
        label = label.replace('&lt;', '<')
        label = label.replace('&gt;', '>')
        label = label.replace('&nbsp;', ' ')
        # Clean up whitespace
        label = ' '.join(label.split())
        return label.strip()

    def _extract_relationship_type(self, style: str) -> Optional[str]:
        """Extract relationship type from style attribute."""
        if 'edgeStyle=entityRelationEdgeStyle' in style:
            return "Entity Relationship"
        return None

    def _extract_cardinality(self, style: str) -> Optional[str]:
        """Extract cardinality from endArrow/startArrow attributes."""
        parts = []

        # Start arrow
        if 'startArrow=ERzeroToMany' in style:
            parts.append("0..*")
        elif 'startArrow=ERoneToMany' in style:
            parts.append("1..*")
        elif 'startArrow=ERoneToOne' in style:
            parts.append("1..1")
        elif 'startArrow=ERzeroToOne' in style:
            parts.append("0..1")

        if not parts:
            return None

        parts.append("-")

        # End arrow
        if 'endArrow=ERzeroToMany' in style:
            parts.append("0..*")
        elif 'endArrow=ERoneToMany' in style:
            parts.append("1..*")
        elif 'endArrow=ERoneToOne' in style:
            parts.append("1..1")
        elif 'endArrow=ERzeroToOne' in style:
            parts.append("0..1")

        return "".join(parts) if len(parts) > 1 else None

    def to_dict(self) -> dict:
        """Convert extracted data to dictionary format with four sections:
        domains, subtypes, entities, relationships."""
        
        # Build object map for ID lookup
        obj_map = {obj.get('id'): obj for obj in self.root.iter('object') if obj.get('id')}
        
        # Build domains list with LeanIX IDs
        domains_dict = {}
        for entity in self.entities:
            domain = entity.domain
            if domain not in domains_dict:
                # Find domain LeanIX ID from groups
                domain_id = None
                for gid, glabel in self.groups.items():
                    if glabel == domain:
                        # Try to find the object for this group
                        if gid in obj_map:
                            domain_id = obj_map[gid].get('factSheetId')
                        else:
                            # Type 1 groups (bare mxCell) - find first child factSheet
                            for obj in self.root.iter('object'):
                                cell = obj.find('mxCell')
                                if cell is not None and cell.get('parent') == gid:
                                    domain_id = obj.get('factSheetId')
                                    break
                        if domain_id:
                            break
                
                domains_dict[domain] = {
                    "domain": domain,
                    "leanix_id": domain_id,
                    "entity_count": 0
                }
            domains_dict[domain]["entity_count"] += 1
        
        # Build subtypes list with LeanIX IDs
        subtypes_dict = {}
        for entity in self.entities:
            if not entity.subtype:
                continue
            
            key = (entity.domain, entity.subtype)
            if key not in subtypes_dict:
                # Find subtype LeanIX ID
                subtype_id = None
                for obj in self.root.iter('object'):
                    cell = obj.find('mxCell')
                    if cell is None:
                        continue
                    
                    # Check if this is a subtype container in the right domain
                    geometry = cell.find('mxGeometry')
                    if geometry is None:
                        continue
                    
                    width = float(geometry.get('width', 0))
                    height = float(geometry.get('height', 0))
                    
                    # Subtype container: 100 < w < 560, 40 < h < 400
                    if (width > 100 and width < 560 and 
                        height > 40 and height < 400 and
                        self._clean_label(obj.get('label', '')) == entity.subtype):
                        subtype_id = obj.get('factSheetId')
                        break
                
                subtypes_dict[key] = {
                    "domain": entity.domain,
                    "subtype": entity.subtype,
                    "leanix_id": subtype_id,
                    "entity_count": 0
                }
            subtypes_dict[key]["entity_count"] += 1
        
        return {
            "metadata": {
                "source_file": str(self.xml_file.name),
                "total_entities": len(self.entities),
                "total_relationships": len(self.relationships),
                "total_domains": len(domains_dict),
                "total_subtypes": len(subtypes_dict)
            },
            "domains": list(domains_dict.values()),
            "subtypes": list(subtypes_dict.values()),
            "entities": [asdict(e) for e in self.entities],
            "relationships": [asdict(r) for r in self.relationships]
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def save_json(self, output_path: str):
        """Save extracted data to JSON file."""
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, 'w', encoding='utf-8') as f:
            f.write(self.to_json())

        print(f"Saved JSON to {output}")
        return str(output)


def main():
    parser = argparse.ArgumentParser(
        description="Extract LeanIX entities and relationships to JSON"
    )
    parser.add_argument(
        "input_file",
        type=str,
        help="Path to LeanIX draw.io XML file"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output JSON file path (default: <input>.json)"
    )

    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = args.output or str(input_path.with_suffix('.json'))

    extractor = LeanIXExtractor(str(input_path))
    extractor.parse_xml()
    extractor.extract_all()
    extractor.save_json(output_path)

    # Print summary
    data = extractor.to_dict()
    print(f"\n=== Summary ===")
    print(f"Total entities: {data['metadata']['total_entities']}")
    print(f"Total relationships: {data['metadata']['total_relationships']}")
    print(f"Total domains: {data['metadata']['total_domains']}")
    print(f"Total subtypes: {data['metadata']['total_subtypes']}")


if __name__ == "__main__":
    main()
