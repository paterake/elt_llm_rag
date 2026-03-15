"""FA Agentic Catalog — batch entity catalog using AgenticRetriever.

Runs the same 7-step pipeline as elt_llm_consumer but replaces Step 5
(fixed RAG+LLM synthesis) with AgenticRetriever: an LLM-driven iterative
retrieval loop that decides what to query based on what has been found.

Steps 1–4 and 6–7 are identical to the consumer (shared infrastructure).
Step 5 is the agentic difference: each entity gets its own adaptive
retrieval strategy rather than a fixed one-size-fits-all query.

Output file:   .tmp/fa_agentic_catalog_{domain}.json
Compare with:  .tmp/fa_consolidated_catalog_{domain}.json  (consumer)

Usage:
    uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY
    uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY --entity "Club Official"
    uv run --package elt-llm-agentic elt-llm-agentic-catalog --domain PARTY --verbose
"""

import argparse
import json
import logging
import time
from pathlib import Path

from elt_llm_agentic.retriever import AgenticRetriever, RetrieverConfig

# Consumer shared infrastructure (Steps 1–4 and 6–7 are identical)
from elt_llm_consumer.fa_consolidated_catalog import (
    _normalize,
    _get_alias_variants,
    _has_real_definition,
    _has_real_governance,
    load_entities_from_json,
    load_inventory_from_json,
    extract_handbook_terms_from_docstore,
    load_relationships_from_json,
)
from elt_llm_core.config import load_config

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
for _lib in ("httpx", "httpcore", "chromadb", "llama_index", "bm25s"):
    logging.getLogger(_lib).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Default paths — derived from ingest configs (same as consumer)
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).parent                           # elt_llm_agentic/src/elt_llm_agentic/
_REPO_ROOT = _THIS_DIR.parent.parent.parent                 # elt_llm_rag/
_RAG_CONFIG = _REPO_ROOT / "elt_llm_ingest/config/rag_config.yaml"
_OUTPUT_DIR = _REPO_ROOT / ".tmp"

_DEFAULT_MODEL_JSON = Path(
    "~/Documents/__data/resources/thefa/DAT_V00.01_FA Enterprise Conceptual Data Model_model.json"
).expanduser()
_DEFAULT_INVENTORY_JSON = Path(
    "~/Documents/__data/resources/thefa/20260227_085233_UtvKD_inventory_inventory.json"
).expanduser()

# ---------------------------------------------------------------------------
# Entities confirmed absent even when queried with all aliases
# (subset of consumer's no_handbook_coverage — Household, Business Unit,
# Managed Service Workers.  Supplier/Customer/etc. are NOT here because
# alias retrieval does find content for them).
# ---------------------------------------------------------------------------
_NO_HANDBOOK_COVERAGE: frozenset[str] = frozenset([
    "Household",
    "Business Unit",
    "Managed Service Workers",
])


# ---------------------------------------------------------------------------
# Batch catalog generation
# ---------------------------------------------------------------------------


def generate_agentic_catalog(
    model_json: Path,
    inventory_json: Path,
    output_dir: Path,
    domain_filter: str | None = None,
    entity_filter: list[str] | None = None,
    max_iterations: int = 5,
    verbose: bool = False,
) -> None:
    """Generate consolidated catalog using AgenticRetriever for Step 5."""

    if domain_filter:
        domain_filter = domain_filter.upper()
        out_path = output_dir / f"fa_agentic_catalog_{domain_filter.lower()}.json"
    else:
        out_path = output_dir / "fa_agentic_catalog.json"

    print("\n=== FA Agentic Catalog (LLM-driven iterative retrieval) ===")
    print(f"  Retriever: AgenticRetriever (max_iterations={max_iterations})")
    print(f"  Output: {out_path}")

    rag_config_path = _RAG_CONFIG

    # -----------------------------------------------------------------------
    # Step 1: Load entities from _model.json (identical to consumer)
    # -----------------------------------------------------------------------
    print("\n=== Step 1: Load Conceptual Model Entities ===")
    all_entities = load_entities_from_json(model_json)
    entities = all_entities

    if domain_filter:
        entities = [e for e in all_entities if e.get("domain", "").upper() == domain_filter]
        print(f"  After domain filter ({domain_filter}): {len(entities)} entities")

    if entity_filter:
        filter_norms = {_normalize(f) for f in entity_filter}
        entities = [e for e in entities if _normalize(e["entity_name"]) in filter_norms]
        print(f"  Entity filter: {entity_filter} ({len(entities)} entities)")

    # -----------------------------------------------------------------------
    # Step 2: Load inventory descriptions (identical to consumer)
    # -----------------------------------------------------------------------
    print("\n=== Step 2: Load Inventory Descriptions ===")
    inventory_lookup = load_inventory_from_json(inventory_json)
    inventory_descriptions: dict[str, dict] = {}
    matched_inv = 0
    for entity in entities:
        fsid = entity.get("fact_sheet_id", "")
        inv = inventory_lookup.get(fsid, {})
        inventory_descriptions[_normalize(entity["entity_name"])] = inv
        if inv:
            matched_inv += 1
    print(f"  {matched_inv}/{len(entities)} entities matched in inventory")

    # -----------------------------------------------------------------------
    # Step 3: Extract handbook defined terms (identical to consumer)
    # -----------------------------------------------------------------------
    print("\n=== Step 3: Extract Handbook Defined Terms ===")
    rag_config = load_config(rag_config_path)
    handbook_terms = extract_handbook_terms_from_docstore(rag_config)
    print(f"  {len(handbook_terms)} defined terms extracted")

    term_definitions: dict[str, str] = {
        t["term"].lower(): t["definition"] for t in handbook_terms
    }

    # -----------------------------------------------------------------------
    # Step 4: Match terms to entities (identical to consumer)
    # -----------------------------------------------------------------------
    print("\n=== Step 4: Match Handbook Terms to Conceptual Model ===")
    handbook_mappings: dict[str, dict] = {}
    matched_terms = 0
    for term_entry in handbook_terms:
        term = term_entry["term"].lower()
        for entity in entities:
            if term in _normalize(entity["entity_name"]).lower():
                handbook_mappings[term] = {
                    "mapped_entity": entity["entity_name"],
                    "domain": entity["domain"],
                    "mapping_confidence": "medium",
                    "mapping_rationale": f"Name contains term '{term}'",
                }
                matched_terms += 1
                break
    print(f"  {matched_terms}/{len(handbook_terms)} handbook terms matched")

    # -----------------------------------------------------------------------
    # Step 5: Agentic retrieval — LLM-driven per-entity strategy
    # -----------------------------------------------------------------------
    print("\n=== Step 5: Extract Handbook Context (AgenticRetriever) ===")
    retriever = AgenticRetriever(RetrieverConfig(
        max_iterations=max_iterations,
        rag_config_path=rag_config_path,
        verbose=verbose,
    ))

    handbook_context: dict[str, dict] = {}
    total = len(entities)
    total_iterations = 0

    for i, entity in enumerate(entities, 1):
        name = entity.get("entity_name", "")
        domain = entity.get("domain", "UNKNOWN")
        norm = _normalize(name)

        print(f"  [{i:>3}/{total}] {name[:50]:<50}", end="\r", flush=True)

        # Skip entities confirmed absent (same short-circuit as consumer)
        if name in _NO_HANDBOOK_COVERAGE:
            handbook_context[norm] = {
                "formal_definition": "",
                "domain_context": "Not applicable — internal FA business concept outside regulatory scope",
                "governance_rules": "Not documented in FA Handbook — outside governance scope",
                "business_rules": "",
                "lifecycle_states": "",
                "data_classification": "",
                "regulatory_context": "",
                "associated_agreements": "",
                "agentic_trace": [],
                "iterations_used": 0,
            }
            continue

        # Build aliases (same source as consumer entity_aliases.yaml via _get_alias_variants)
        aliases = [v for v in _get_alias_variants(name) if v.lower() != norm.lower()]

        t0 = time.monotonic()
        ctx = retriever.retrieve_entity_context(name, domain, aliases=aliases)
        elapsed = time.monotonic() - t0
        total_iterations += ctx.get("iterations_used", 0)

        if verbose:
            print(f"\n    → {name}: {ctx['iterations_used']} iterations, {elapsed:.1f}s")

        handbook_context[norm] = ctx

    print(f"  {len(handbook_context)} entities processed            ")
    avg_iter = total_iterations / max(len(handbook_context), 1)
    print(f"  Average iterations per entity: {avg_iter:.1f}")

    # -----------------------------------------------------------------------
    # Step 6: Load relationships (identical to consumer)
    # -----------------------------------------------------------------------
    print("\n=== Step 6: Load Relationships ===")
    relationships = load_relationships_from_json(model_json)
    print(f"  {sum(len(v) for v in relationships.values())} relationships loaded")

    # -----------------------------------------------------------------------
    # Step 7: Consolidate
    # -----------------------------------------------------------------------
    print("\n=== Step 7: Consolidating ===")

    output_entities = []
    for entity in entities:
        name = entity["entity_name"]
        norm = _normalize(name)
        ctx = handbook_context.get(norm, {})

        # Source classification
        # Entities confirmed absent are always LEANIX_ONLY — the Step 5 stub
        # must not be evaluated by _has_real_governance (it contains boilerplate
        # text that can pass the check and produce a false BOTH classification).
        if name in _NO_HANDBOOK_COVERAGE:
            source = "LEANIX_ONLY"
            mapped = {}
        else:
            # Check term mapping from Step 4
            term_match = next(
                ((term, m) for term, m in handbook_mappings.items()
                 if _normalize(m.get("mapped_entity", "")) == norm),
                None,
            )

            if term_match:
                source = "BOTH"
                _, mapped = term_match
            elif _has_real_definition(ctx) or _has_real_governance(ctx):
                source = "BOTH"
                mapped = {
                    "mapping_confidence": "medium",
                    "mapping_rationale": "Handbook content found via agentic retrieval",
                }
            else:
                source = "LEANIX_ONLY"
                mapped = {}

        inv = inventory_descriptions.get(norm, {})
        entity_rels = relationships.get(norm, [])

        # Step 3 definition override: if a verbatim "X means Y" def was extracted,
        # it takes precedence over the LLM-synthesised one (same rule as consumer)
        lookup_keys = [name.lower()] + _get_alias_variants(name)
        step3_def = next((term_definitions[k] for k in lookup_keys if k in term_definitions), None)
        formal_def = step3_def or ctx.get("formal_definition", "")

        record = {
            "fact_sheet_id": entity.get("fact_sheet_id", ""),
            "entity_name": name,
            "domain": entity.get("domain", ""),
            "subgroup": entity.get("subgroup", ""),
            "source": source,
            "leanix_description": inv.get("description", ""),
            "formal_definition": formal_def,
            "domain_context": ctx.get("domain_context", ""),
            "governance_rules": ctx.get("governance_rules", ""),
            "business_rules": ctx.get("business_rules", ""),
            "lifecycle_states": ctx.get("lifecycle_states", ""),
            "data_classification": ctx.get("data_classification", ""),
            "regulatory_context": ctx.get("regulatory_context", ""),
            "associated_agreements": ctx.get("associated_agreements", ""),
            "handbook_term": None,
            "mapping_confidence": mapped.get("mapping_confidence", ""),
            "mapping_rationale": mapped.get("mapping_rationale", ""),
            "agentic_iterations": ctx.get("iterations_used", 0),
            "agentic_trace": ctx.get("agentic_trace", []),
            "review_status": "PENDING",
            "review_notes": "AgenticRetriever — LLM-driven iterative retrieval",
            "relationships": entity_rels,
        }
        output_entities.append(record)

    # Write output
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"entities": output_entities}, f, indent=2, ensure_ascii=False)

    print(f"\n  Agentic catalog (JSON) → {out_path}")

    # Summary
    source_counts: dict[str, int] = {}
    for e in output_entities:
        src = e.get("source", "UNKNOWN")
        source_counts[src] = source_counts.get(src, 0) + 1

    print("\n=== Summary by Source ===")
    for src, count in sorted(source_counts.items()):
        print(f"  {src}: {count}")

    with_defs = sum(1 for e in output_entities if _has_real_definition(e))
    with_gov = sum(1 for e in output_entities if _has_real_governance(e))
    avg_iter_final = (
        sum(e.get("agentic_iterations", 0) for e in output_entities) / max(len(output_entities), 1)
    )

    print("\n=== Quality Metrics ===")
    print(f"  Entities with formal definitions: {with_defs}/{len(output_entities)}")
    print(f"  Entities with governance rules:   {with_gov}/{len(output_entities)}")
    print(f"  Average agentic iterations:       {avg_iter_final:.1f}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Generate FA catalog using AgenticRetriever — "
            "LLM-driven iterative retrieval (compare with elt_llm_consumer)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Output: .tmp/fa_agentic_catalog_{domain}.json\n"
            "Compare: .tmp/fa_consolidated_catalog_{domain}.json (consumer)\n\n"
            "The key difference from consumer:\n"
            "  Consumer Step 5: fixed query → retrieve → synthesise\n"
            "  Agentic Step 5:  retrieve → LLM decides what to try next → repeat → synthesise"
        ),
    )
    parser.add_argument("--domain", default=None, metavar="DOMAIN",
                        help="Restrict to one domain (e.g. PARTY, AGREEMENTS)")
    parser.add_argument("--entity", default=None, metavar="ENTITY",
                        help="Restrict to one or more entities (comma-separated)")
    parser.add_argument("--max-iterations", type=int, default=5, metavar="N",
                        help="Max agentic iterations per entity (default: 5)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-iteration trace for each entity")
    parser.add_argument("--output-dir", type=Path, default=_OUTPUT_DIR,
                        help=f"Output directory (default: {_OUTPUT_DIR})")
    parser.add_argument("--model-json", type=Path, default=_DEFAULT_MODEL_JSON)
    parser.add_argument("--inventory-json", type=Path, default=_DEFAULT_INVENTORY_JSON)

    args = parser.parse_args()

    generate_agentic_catalog(
        model_json=args.model_json,
        inventory_json=args.inventory_json,
        output_dir=args.output_dir,
        domain_filter=args.domain,
        entity_filter=[e.strip() for e in args.entity.split(",")] if args.entity else None,
        max_iterations=args.max_iterations,
        verbose=args.verbose,
    )


if __name__ == "__main__":
    main()
