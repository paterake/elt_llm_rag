"""Shared types and print helpers for ranking diagnostics."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChunkResult:
    rank: int
    score: float
    collection: str     # from node metadata (source_file or collection key)
    text_preview: str   # first 100 chars, whitespace-collapsed
    full_text: str
    is_keyword_chunk: bool  # True if this chunk was a verbatim keyword match


@dataclass
class RankingResult:
    ranker: str
    query: str
    total_candidates: int
    top_k_cutoff: int
    chunks: list[ChunkResult]   # ALL chunks, ranked 1..N


def _collection_label(node) -> str:
    """Extract a short section label from node metadata."""
    meta = getattr(node, "metadata", {}) or {}
    # Try common metadata keys used during ingestion
    for key in ("collection", "source_file", "file_name", "section"):
        val = meta.get(key, "")
        if val:
            return str(val)
    return "unknown"


def print_ranking(result: RankingResult, show_dropped: bool = True) -> None:
    """Print a formatted ranking result table."""
    cutoff = result.top_k_cutoff
    print(f"\n{'='*70}")
    print(f"  RANKING: {result.ranker.upper()}")
    print(f"{'='*70}")
    print(f"  Candidates: {result.total_candidates}  |  top_k cutoff: {cutoff}")
    print(f"  Query: {result.query[:100]}{'...' if len(result.query) > 100 else ''}")

    # Keyword chunk summary
    kw_chunks = [c for c in result.chunks if c.is_keyword_chunk]
    if kw_chunks:
        print(f"\n  Keyword chunk positions (verbatim matches for entity):")
        for c in kw_chunks:
            status = "INCLUDED" if c.rank <= cutoff else "DROPPED"
            flag = " <-- !" if status == "DROPPED" else ""
            print(f"    Rank {c.rank:>3}/{result.total_candidates}  [{status}]{flag}  {c.text_preview[:80]}")
    else:
        print(f"\n  No keyword chunks in candidate pool")

    # Full ranked list
    print(f"\n  {'Rank':>4}  {'Score':>7}  {'KW':>2}  Collection                  Preview")
    print(f"  {'----':>4}  {'-------':>7}  {'--':>2}  {'-'*27} {'-'*40}")

    passed = [c for c in result.chunks if c.rank <= cutoff]
    dropped = [c for c in result.chunks if c.rank > cutoff]

    for c in passed:
        kw_flag = "✓" if c.is_keyword_chunk else " "
        preview = c.text_preview[:40]
        coll = c.collection[-27:] if len(c.collection) > 27 else c.collection
        print(f"  {c.rank:>4}  {c.score:>7.4f}  {kw_flag:>2}  {coll:<27}  {preview}")

    if dropped:
        print(f"  {'':>4}  {'':>7}  {'':>2}  {'--- cutoff ---'}")
        if show_dropped:
            for c in dropped[:20]:
                kw_flag = "✓" if c.is_keyword_chunk else " "
                preview = c.text_preview[:40]
                coll = c.collection[-27:] if len(c.collection) > 27 else c.collection
                print(f"  {c.rank:>4}  {c.score:>7.4f}  {kw_flag:>2}  {coll:<27}  {preview}")
            if len(dropped) > 20:
                print(f"  ... ({len(dropped) - 20} more dropped)")
