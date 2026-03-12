"""RAG Retriever — diagnostic tool for inspecting retrieval and ranking.

All output is written to .tmp/ files. Only the output file paths are printed
to the console so they can be shared for review.

Usage (from elt_llm_consumer/):

  # Full diagnostic — all stages, all 3 rankers (writes 4 files)
  uv run --package elt-llm-consumer rag-retriever --entity "Sports Governing Body" --stage all --ranker all

  # Retrieval only
  uv run --package elt-llm-consumer rag-retriever --entity "Sports Governing Body" --stage retrieval

  # One ranker
  uv run --package elt-llm-consumer rag-retriever --entity "Sports Governing Body" --stage ranking --ranker embedding
"""
from __future__ import annotations

import argparse
import contextlib
import io
import logging
import re
import sys
from pathlib import Path

from ._config import DEFAULT_SECTION_PREFIX, get_aliases_for, load_entity_aliases, load_rag_config

# Output directory — same root as all other consumers
_OUTPUT_DIR = Path(__file__).parent.parent.parent.parent.parent / ".tmp"


def _entity_slug(entity_name: str) -> str:
    """Normalise entity name to a safe filename fragment."""
    slug = entity_name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    return slug.strip("_")


def _output_path(slug: str, stage: str, ranker: str | None = None) -> Path:
    """Return the .tmp output file path for a given stage/ranker."""
    if ranker:
        name = f"rag_retriever_{stage}_{ranker}_{slug}.txt"
    else:
        name = f"rag_retriever_{stage}_{slug}.txt"
    return _OUTPUT_DIR / name


def _write_to_file(path: Path, fn, *args, **kwargs):
    """Capture all stdout from fn(*args, **kwargs) and write to path."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return result


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    for lib in ("httpx", "httpcore", "chromadb", "llama_index", "bm25s"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    parser = argparse.ArgumentParser(
        description="RAG pipeline diagnostic — writes output to .tmp/ files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--entity", required=True,
        help='Entity name to probe, e.g. "Sports Governing Body"',
    )
    parser.add_argument(
        "--stage",
        choices=["retrieval", "ranking", "all"],
        default="all",
        help="Pipeline stage to run (default: all)",
    )
    parser.add_argument(
        "--ranker",
        choices=["embedding", "bm25", "boosted", "all"],
        default="all",
        help="Ranking strategy (default: all; only applies when stage=ranking or all)",
    )
    parser.add_argument(
        "--section-prefix", default=DEFAULT_SECTION_PREFIX,
        help=f"ChromaDB section collection prefix (default: {DEFAULT_SECTION_PREFIX})",
    )
    parser.add_argument(
        "--config", type=Path, default=None,
        help="Path to rag_config.yaml (default: elt_llm_ingest/config/rag_config.yaml)",
    )
    parser.add_argument(
        "--no-dropped", action="store_true",
        help="Hide dropped chunks in ranking output",
    )

    args = parser.parse_args()
    slug = _entity_slug(args.entity)

    print(f"Loading config…")
    rag_config = load_rag_config(args.config)
    entity_aliases = load_entity_aliases()
    aliases = get_aliases_for(args.entity, entity_aliases)

    run_retrieval_stage = args.stage in ("retrieval", "all")
    run_ranking_stage = args.stage in ("ranking", "all")

    # ------------------------------------------------------------------
    # Stage: Retrieval — always runs (ranking needs the candidate pool)
    # ------------------------------------------------------------------
    from .retriever import run_retrieval as _run_retrieval

    retrieval_path = _output_path(slug, "retrieval")
    print(f"Running retrieval…")
    retrieval_result = _write_to_file(
        retrieval_path, _run_retrieval,
        entity_name=args.entity,
        rag_config=rag_config,
        aliases=aliases,
        section_prefix=args.section_prefix,
    )
    if run_retrieval_stage:
        print(f"  → {retrieval_path}")

    if not run_ranking_stage:
        return

    if not retrieval_result.candidate_pool:
        print("\n[No candidate pool — cannot run ranking stages]")
        return

    query = (
        f"Entity: {args.entity}\n"
        f"Provide the formal definition, domain context, and governance rules "
        f"for '{args.entity}' as described in the FA Handbook."
    )

    # ------------------------------------------------------------------
    # Stage: Ranking — one file per ranker
    # ------------------------------------------------------------------
    rankers_to_run: list[str] = (
        ["embedding", "bm25", "boosted"] if args.ranker == "all" else [args.ranker]
    )

    from .ranking import print_ranking
    from .ranking import embedding as _embedding
    from .ranking import bm25 as _bm25
    from .ranking import boosted as _boosted

    ranking_results: dict[str, object] = {}

    for ranker_name in rankers_to_run:
        print(f"Running ranker: {ranker_name}…")

        if ranker_name == "embedding":
            result = _embedding.rank(
                query, retrieval_result.candidate_pool,
                retrieval_result.keyword_chunks, rag_config,
            )
        elif ranker_name == "bm25":
            result = _bm25.rank(
                query, retrieval_result.candidate_pool,
                retrieval_result.keyword_chunks, rag_config,
                entity_name=args.entity,
            )
        elif ranker_name == "boosted":
            result = _boosted.rank(
                query, retrieval_result.candidate_pool,
                retrieval_result.keyword_chunks, rag_config,
            )
        else:
            continue

        ranking_results[ranker_name] = result
        ranking_path = _output_path(slug, "ranking", ranker_name)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            print_ranking(result, show_dropped=not args.no_dropped)
        ranking_path.parent.mkdir(parents=True, exist_ok=True)
        ranking_path.write_text(buf.getvalue(), encoding="utf-8")
        print(f"  → {ranking_path}")

    # ------------------------------------------------------------------
    # Summary comparison file (when running multiple rankers)
    # ------------------------------------------------------------------
    if len(rankers_to_run) > 1 and retrieval_result.keyword_chunks:
        summary_path = _output_path(slug, "summary")
        lines = [
            "=" * 70,
            "  KEYWORD CHUNK SUMMARY",
            "=" * 70,
            f"  Entity: {args.entity}",
            f"  Keyword chunks found: {len(retrieval_result.keyword_chunks)}",
            f"  top_k cutoff: {rag_config.query.reranker_top_k}",
            "",
        ]
        for ranker_name, result in ranking_results.items():
            kw_chunks = [c for c in result.chunks if c.is_keyword_chunk]
            lines.append(f"  {ranker_name.upper()}:")
            if kw_chunks:
                for c in kw_chunks:
                    status = "INCLUDED" if c.rank <= result.top_k_cutoff else "DROPPED"
                    lines.append(f"    Rank {c.rank:>3}/{result.total_candidates}  [{status}]  {c.text_preview[:80]}")
            else:
                lines.append("    (no keyword chunks matched in candidate pool)")
            lines.append("")

        lines += [
            "  Key:",
            "    INCLUDED = chunk is sent to the LLM",
            "    DROPPED  = chunk is cut off before the LLM sees it",
            "    DROPPED under embedding but INCLUDED under bm25 → switch reranker strategy",
            "    DROPPED under embedding but boosted injects it  → Option C (force inject)",
        ]

        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"  → {summary_path}  [summary]")
