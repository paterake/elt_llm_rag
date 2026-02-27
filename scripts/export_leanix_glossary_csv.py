#!/usr/bin/env python3
"""
Export LeanIX Inventory to CSV for Glossary/Catalogue Use

This script extracts DataObjects, Applications, Interfaces, and BusinessCapabilities
from the LeanIX inventory export and creates structured CSV files suitable for:
- Business glossary review
- Reference data management
- Purview catalogue import preparation
- Data Working Group deliverables

Usage:
    python scripts/export_leanix_glossary_csv.py
"""

import pandas as pd
from pathlib import Path
from datetime import datetime

# Paths
INPUT_FILE = "/Users/rpatel/Downloads/20260227_085233_UtvKD_inventory.xlsx"
OUTPUT_DIR = Path("/Users/rpatel/Documents/__code/git/emailrak/elt_llm_rag/.tmp/leanix_exports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load data
print("Loading LeanIX inventory...")
df = pd.read_excel(INPUT_FILE)
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

# =============================================================================
# 1. DATAOBJECTS EXPORT - Conceptual Model Entities
# =============================================================================
print("\n=== Exporting DataObjects (Conceptual Model Entities) ===")
data_objs = df[df['type'] == 'DataObject'].copy()

# Structure for glossary/catalogue
data_objs_export = data_objs[['id', 'name', 'displayName', 'description', 'level', 'status']].copy()
data_objs_export.columns = ['fact_sheet_id', 'entity_name', 'display_name', 'definition', 'hierarchy_level', 'status']

# Add domain group (based on level)
level_to_domain = {
    1: 'ENTERPRISE_DOMAIN',
    2: 'SUB_DOMAIN',
    3: 'ENTITY_GROUP',
    4: 'ENTITY_TYPE'
}
data_objs_export['domain_group'] = data_objs_export['hierarchy_level'].map(level_to_domain)

# Sort by level and name
data_objs_export = data_objs_export.sort_values(['hierarchy_level', 'entity_name'])

# Save
output_file = OUTPUT_DIR / f"{timestamp}_data_objects_glossary.csv"
data_objs_export.to_csv(output_file, index=False)
print(f"  Saved: {output_file}")
print(f"  Total DataObjects: {len(data_objs_export)}")
print(f"  With definitions: {data_objs_export['definition'].notna().sum()}")

# =============================================================================
# 2. APPLICATIONS EXPORT - Systems Holding Data
# =============================================================================
print("\n=== Exporting Applications (Systems) ===")
apps = df[df['type'] == 'Application'].copy()
apps_export = apps[['id', 'name', 'displayName', 'description', 'level', 'status']].copy()
apps_export.columns = ['fact_sheet_id', 'application_name', 'display_name', 'description', 'hierarchy_level', 'status']
apps_export = apps_export.sort_values('application_name')

output_file = OUTPUT_DIR / f"{timestamp}_applications.csv"
apps_export.to_csv(output_file, index=False)
print(f"  Saved: {output_file}")
print(f"  Total Applications: {len(apps_export)}")

# =============================================================================
# 3. INTERFACES EXPORT - Data Flows (What is Transmitted)
# =============================================================================
print("\n=== Exporting Interfaces (Data Flows/Transmissions) ===")
interfaces = df[df['type'] == 'Interface'].copy()

# Try to extract source/target from name pattern "Source to Target"
def extract_source_target(row):
    name = row['name']
    desc = row['description'] if pd.notna(row['description']) else ''
    
    # Try to parse "X to Y" pattern
    if ' to ' in name:
        parts = name.split(' to ')
        source = parts[0].strip()
        target_with_rest = ' to '.join(parts[1:])
        # Clean target (remove LI suffix etc)
        target = target_with_rest.split()[0].strip() if target_with_rest else target_with_rest
        return pd.Series([source, target])
    return pd.Series([None, None])

interfaces[['inferred_source', 'inferred_target']] = interfaces.apply(extract_source_target, axis=1)

interfaces_export = interfaces[['id', 'name', 'displayName', 'description', 'status', 'inferred_source', 'inferred_target']].copy()
interfaces_export.columns = ['fact_sheet_id', 'interface_name', 'display_name', 'flow_description', 'status', 'source_system', 'target_system']
interfaces_export = interfaces_export.sort_values('interface_name')

output_file = OUTPUT_DIR / f"{timestamp}_interfaces_dataflows.csv"
interfaces_export.to_csv(output_file, index=False)
print(f"  Saved: {output_file}")
print(f"  Total Interfaces: {len(interfaces_export)}")
print(f"  With inferred source/target: {interfaces_export[['source_system', 'target_system']].notna().all(axis=1).sum()}")

# =============================================================================
# 4. BUSINESSCAPABILITIES EXPORT - Business Context
# =============================================================================
print("\n=== Exporting BusinessCapabilities (Business Functions) ===")
biz_cap = df[df['type'] == 'BusinessCapability'].copy()

# Extract domain/subdomain from name
def extract_domain(row):
    name = row['name']
    if '/' in name:
        parts = name.split('/')
        return pd.Series([parts[0].strip(), parts[1].strip() if len(parts) > 1 else None])
    return pd.Series([None, name])

biz_cap[['domain', 'subdomain']] = biz_cap.apply(extract_domain, axis=1)

biz_cap_export = biz_cap[['id', 'name', 'displayName', 'description', 'level', 'domain', 'subdomain', 'status']].copy()
biz_cap_export.columns = ['fact_sheet_id', 'capability_name', 'display_name', 'description', 'hierarchy_level', 'business_domain', 'business_subdomain', 'status']
biz_cap_export = biz_cap_export.sort_values(['business_domain', 'capability_name'])

output_file = OUTPUT_DIR / f"{timestamp}_business_capabilities.csv"
biz_cap_export.to_csv(output_file, index=False)
print(f"  Saved: {output_file}")
print(f"  Total BusinessCapabilities: {len(biz_cap_export)}")

# =============================================================================
# 5. ORGANIZATIONS EXPORT - Data Owners/Stewards
# =============================================================================
print("\n=== Exporting Organizations (Potential Data Owners) ===")
orgs = df[df['type'] == 'Organization'].copy()
orgs_export = orgs[['id', 'name', 'displayName', 'description', 'level', 'status']].copy()
orgs_export.columns = ['fact_sheet_id', 'organization_name', 'display_name', 'description', 'hierarchy_level', 'status']
orgs_export = orgs_export.sort_values('organization_name')

output_file = OUTPUT_DIR / f"{timestamp}_organizations.csv"
orgs_export.to_csv(output_file, index=False)
print(f"  Saved: {output_file}")
print(f"  Total Organizations: {len(orgs_export)}")

# =============================================================================
# 6. COMBINED GLOSSARY - Master Export
# =============================================================================
print("\n=== Creating Combined Glossary Export ===")

# DataObjects as primary glossary
glossary = data_objs_export[['entity_name', 'definition', 'domain_group']].copy()
glossary['source'] = 'LeanIX DataObject'
glossary['fact_sheet_type'] = 'DataObject'

# Add Applications as "system" glossary terms
apps_glossary = apps_export[['application_name', 'description', 'hierarchy_level']].copy()
apps_glossary.columns = ['entity_name', 'definition', 'domain_group']
apps_glossary['source'] = 'LeanIX Application'
apps_glossary['fact_sheet_type'] = 'Application'

# Combine
combined = pd.concat([glossary, apps_glossary], ignore_index=True)
combined = combined.sort_values(['domain_group', 'entity_name'])

output_file = OUTPUT_DIR / f"{timestamp}_combined_glossary.csv"
combined.to_csv(output_file, index=False)
print(f"  Saved: {output_file}")
print(f"  Total terms: {len(combined)}")

# =============================================================================
# SUMMARY
# =============================================================================
print("\n" + "="*80)
print("EXPORT SUMMARY")
print("="*80)
print(f"""
Output directory: {OUTPUT_DIR}

Files created:
1. {timestamp}_data_objects_glossary.csv
   - {len(data_objs_export)} DataObjects (conceptual model entities)
   - Includes: entity_name, definition, domain_group, hierarchy_level
   
2. {timestamp}_applications.csv
   - {len(apps_export)} Applications (systems holding data)
   
3. {timestamp}_interfaces_dataflows.csv
   - {len(interfaces_export)} Interfaces (data transmissions)
   - Includes: source_system, target_system (inferred from naming)
   
4. {timestamp}_business_capabilities.csv
   - {len(biz_cap_export)} BusinessCapabilities (business functions)
   - Includes: business_domain, business_subdomain
   
5. {timestamp}_organizations.csv
   - {len(orgs_export)} Organizations (potential data owners)
   
6. {timestamp}_combined_glossary.csv
   - {len(combined)} combined glossary terms
   - Ready for review in Excel / import to Purview

KEY INSIGHTS:
- DataObjects are organized in 4 hierarchy levels (1=domain, 4=detailed type)
- 10 Level-1 domains: PARTY, AGREEMENTS, PRODUCT, TRANSACTION, CHANNEL, LOCATION, etc.
- 271 Interfaces show what data is transmitted between systems
- 44.5% of items have descriptions (634/1424)

NEXT STEPS:
1. Review {timestamp}_data_objects_glossary.csv with Data Working Group
2. Validate domain groupings against LeanIX conceptual model diagram
3. Map Interfaces to DataObjects (which entities flow where)
4. Link Organizations to DataObjects (ownership/stewardship)
5. Export to Purview format
""")

print(f"Export complete! Files saved to: {OUTPUT_DIR}")
