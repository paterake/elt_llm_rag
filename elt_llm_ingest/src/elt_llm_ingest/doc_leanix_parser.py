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
    parent_group: Optional[str] = None
    parent_id: Optional[str] = None
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

    def __init__(self, xml_file: str):
        self.xml_file = Path(xml_file)
        self.tree = None
        self.root = None
        self.assets: Dict[str, LeanIXAsset] = {}
        self.relationships: List[LeanIXRelationship] = []
        self.groups: Dict[str, str] = {}  # group_id -> group_label
        self.parent_map = {}  # child -> parent mapping for efficient lookups

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
        self.extract_relationships()
        self.enrich_relationships()
        
    def extract_groups(self):
        """Extract group containers (like PARTY, AGREEMENTS, etc.)
        
        Groups are identified as mxCell elements with style containing 'group'.
        """
        for mxcell in self.root.iter('mxCell'):
            style = mxcell.get('style', '')
            if 'group' in style and mxcell.get('vertex') == '1':
                group_id = mxcell.get('id')
                # Find the factSheet object that is the container within this group
                for obj in self.root.iter('object'):
                    obj_cell = obj.find('mxCell')
                    if obj_cell is not None and obj_cell.get('parent') == group_id:
                        # This object is directly in the group - use it as the group label
                        label = obj.get('label', '')
                        if label and obj.get('type') == 'factSheet':
                            self.groups[group_id] = self.clean_label(label)
                            break
    
    def extract_assets(self):
        """Extract all fact sheet assets"""
        for obj in self.root.iter('object'):
            if obj.get('type') == 'factSheet':
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
        md.append("# FA Enterprise Conceptual Data Model\n\n")
        md.append(
            f"The FA Enterprise Conceptual Data Model (source: {self.xml_file.name}) "
            f"contains {len(self.assets)} DataObject entities organised into "
            f"{len(domain_names)} domain groups: {', '.join(domain_names)}. "
            f"These domains are connected through {len(self.relationships)} entity relationships. "
            "The model captures the key data objects, parties, agreements, products, transactions, "
            "channels, locations, and reference data that underpin The Football Association's "
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
                f"The {group_name} domain contains {len(group_assets)} entities in the FA "
                f"Enterprise Conceptual Data Model. "
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
                "The following entities are defined in the FA Enterprise Conceptual Data Model "
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
                "The following relationships define how the domain groups in the FA Enterprise "
                "Conceptual Data Model connect to one another.\n\n"
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
        md.append("# FA Enterprise Conceptual Data Model — Overview\n\n")
        md.append(
            f"The FA Enterprise Conceptual Data Model (source: {self.xml_file.name}) "
            f"contains {len(self.assets)} DataObject entities organised into "
            f"{len(domain_names)} named domain groups: {', '.join(domain_names)}. "
            f"These domains are connected through {len(self.relationships)} entity "
            f"relationships.\n\n"
        )
        for group_name in domain_names:
            group_assets = assets_by_group[group_name]
            members = [a.label for a in group_assets if a.label.upper() != group_name.upper()]
            md.append(f"The **{group_name}** domain contains {len(members)} entities.\n\n")
        sections["overview"] = "".join(md)

        # ── One section per domain ────────────────────────────────────────────
        for group_name in domain_names:
            group_assets = sorted(assets_by_group[group_name], key=lambda a: a.label)
            members = [a.label for a in group_assets if a.label.upper() != group_name.upper()]

            md = []
            md.append(f"# {group_name} Domain — FA Enterprise Conceptual Data Model\n\n")
            md.append(
                f"The {group_name} domain is part of the FA Enterprise Conceptual Data Model. "
                f"It contains {len(members)} entities.\n\n"
            )
            if members:
                md.append(f"The entities within the {group_name} domain are:\n\n")
                for member in members:
                    md.append(f"- **{member}**\n")
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
            md.append("# Additional Entities — FA Enterprise Conceptual Data Model\n\n")
            md.append(
                "The following entities are defined in the FA Enterprise Conceptual Data Model "
                "and include key party, channel, account, and asset entities that form the "
                "core of The Football Association's data landscape.\n\n"
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
            md.append("# Entity Relationships — FA Enterprise Conceptual Data Model\n\n")
            md.append(
                f"This document lists all {len(self.relationships)} domain-level entity "
                "relationships in the FA Enterprise Conceptual Data Model. "
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
            output_path: Output file path. If format is 'both', this is used as base name.
            format: Output format - 'json', 'markdown', 'md', or 'both'.
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