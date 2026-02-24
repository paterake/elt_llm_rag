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
        """Extract group containers (like PARTY, AGREEMENTS, etc.)"""
        # Find all mxCell elements with style="group"
        for mxcell in self.root.iter('mxCell'):
            style = mxcell.get('style', '')
            if 'group' in style and mxcell.get('vertex') == '1':
                group_id = mxcell.get('id')
                # Try to find the label from child object using parent map
                for obj in self.root.iter('object'):
                    obj_cell = obj.find('mxCell')
                    if obj_cell is not None and obj_cell.get('parent') == group_id:
                        label = obj.get('label', '')
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
        """Convert to Markdown format suitable for RAG"""
        md = []
        
        # Header
        md.append("# LeanIX Enterprise Architecture Inventory\n")
        md.append(f"**Source:** {self.xml_file.name}\n")
        md.append(f"**Total Assets:** {len(self.assets)}\n")
        md.append(f"**Total Relationships:** {len(self.relationships)}\n")
        
        # Group assets by type
        assets_by_type = defaultdict(list)
        for asset in self.assets.values():
            assets_by_type[asset.fact_sheet_type].append(asset)
        
        # Assets section
        md.append("\n## Assets by Type\n")
        
        for fact_sheet_type in sorted(assets_by_type.keys()):
            type_assets = assets_by_type[fact_sheet_type]
            md.append(f"\n### {fact_sheet_type}\n")
            md.append(f"*Count: {len(type_assets)}*\n")
            
            # Group by parent if available
            by_parent = defaultdict(list)
            for asset in type_assets:
                parent = asset.parent_group or "Uncategorized"
                by_parent[parent].append(asset)
            
            for parent, assets in sorted(by_parent.items()):
                if parent != "Uncategorized":
                    md.append(f"\n#### {parent}\n")
                
                for asset in sorted(assets, key=lambda x: x.label):
                    md.append(f"- **{asset.label}**")
                    if asset.fact_sheet_id:
                        md.append(f"  - ID: `{asset.fact_sheet_id}`")
            
            md.append("\n")
        
        # Relationships section
        md.append("\n## Relationships\n")
        
        # Group relationships by source
        rels_by_source = defaultdict(list)
        for rel in self.relationships:
            rels_by_source[rel.source_label or rel.source_id].append(rel)
        
        for source in sorted(rels_by_source.keys()):
            rels = rels_by_source[source]
            md.append(f"\n### {source}\n")
            
            for rel in sorted(rels, key=lambda x: x.target_label or ""):
                cardinality = f" [{rel.cardinality}]" if rel.cardinality else ""
                md.append(f"- → **{rel.target_label or rel.target_id}**{cardinality}")
                if rel.relationship_type:
                    md.append(f"  - Type: {rel.relationship_type}")
            
            md.append("\n")
        
        return "".join(md)
    
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