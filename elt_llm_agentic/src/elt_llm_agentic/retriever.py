"""AgenticRetriever — LLM-driven iterative RAG retrieval.

The core design difference from elt_llm_consumer's fixed pipeline:

  Consumer (naive):
    1. BM25 route sections (fixed alias list)
    2. Keyword scan (entity name only)
    3. Single query_collections call
    4. Single LLM synthesis
    → Fixed number of operations, same sequence for every entity

  AgenticRetriever (agentic):
    1. Initial RAG retrieve (entity name)
    2. LLM assesses: "Is this sufficient? What's missing?"
    3. If not sufficient: LLM chooses next action (different query, alias
       keyword scan, targeted section query, or done)
    4. Repeat until sufficient evidence or max_iterations reached
    5. Final synthesis combining all gathered evidence
    → Variable number of operations, LLM controls the strategy

The key: _decide_action() calls the LLM to pick the next query.
Not keyword heuristics — the LLM reads what has been retrieved and
decides what gap remains to be filled.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # elt_llm_rag/
_DEFAULT_RAG_CONFIG = _REPO_ROOT / "elt_llm_ingest/config/rag_config.yaml"

# ---------------------------------------------------------------------------
# Boilerplate detection — used by the KEYWORD guard to distinguish
# "found real content" from "retrieval returned but LLM synthesised nothing"
# ---------------------------------------------------------------------------

_BOILERPLATE_FRAGMENTS = (
    "not defined in fa handbook",
    "not specified in fa handbook",
    "not listed in the document",
    "not mentioned in the",
    "no governance rules are imposed",
    "no specific rules imposed",
    "no specific governance",
    "no authority is explicitly",
    "does not exercise any authority",
    "is absent",
    "no information available",
    "the provided text does not",
    "i was unable to",
    "i cannot find",
    "no equivalent definition",
    "no explicit governance",
)


def _is_boilerplate(text: str) -> bool:
    """Return True if the text is a boilerplate negative/empty response."""
    lower = text.strip().lower()
    return any(frag in lower[:400] for frag in _BOILERPLATE_FRAGMENTS)


# ---------------------------------------------------------------------------
# Action types returned by _decide_action
# ---------------------------------------------------------------------------

_ACTION_RE = re.compile(
    r"^(RETRIEVE|KEYWORD|DONE)"
    r"(?:\s+sections:\s*(\[[^\]]*\]))?"
    r"(?:\s+query:\s*\"([^\"]+)\")?"
    r"(?:\s+terms:\s*(\[[^\]]*\]))?",
    re.IGNORECASE | re.MULTILINE,
)

_DECISION_PROMPT = """\
You are an information retrieval agent searching the FA Handbook for entity context.

ENTITY: '{entity_name}'
ALIASES: {aliases}

RETRIEVED SO FAR:
{observations_summary}

QUERIES / TERMS ALREADY TRIED:
{tried_summary}

TASK:
Choose the single best next action to fill the most important remaining gap.

AVAILABLE ACTIONS (respond with EXACTLY ONE):

RETRIEVE sections: ["s01","s05",...] query: "your search query"
  - Runs a hybrid RAG retrieval (BM25 + vector + reranker) against specific sections.
  - Use a focused query that targets what is still missing.
  - Provide 2–6 section names (e.g. "fa_handbook_s01") if you have a strong prior,
    OR omit the sections list for automatic BM25 routing: RETRIEVE query: "..."
  - Do NOT repeat a query already tried.

KEYWORD terms: ["term1", "term2"]
  - Scans all sections for verbatim mentions of these terms.
  - Use for aliases or exact phrases you suspect appear in operational rules.
  - Useful when RAG didn't surface the right chunks.

DONE
  - Choose DONE when you have sufficient evidence for FORMAL_DEFINITION +
    GOVERNANCE_RULES, OR you have exhausted all reasonable approaches
    (tried entity name, 2+ aliases, keyword scan).

DECISION RULES:
- If no observations yet → RETRIEVE with entity name (automatic routing).
- If initial RAG returned sparse/empty → try KEYWORD with top 2 aliases.
- If keyword scan found content but RAG missed it → RETRIEVE targeting those sections.
- If tried entity name + 2 aliases + keyword scan → DONE.
- Never repeat a query or term set already in the tried list.

Respond with exactly one action on a single line. Examples:
  RETRIEVE query: "Club Official governance rules FA Handbook"
  RETRIEVE sections: ["fa_handbook_s01","fa_handbook_s05"] query: "Club Official means definition"
  KEYWORD terms: ["club officer","secretary","director"]
  DONE
"""

_SYNTHESIS_PROMPT = """\
You are an expert on FA (Football Association) governance and rules.

Synthesise a complete terms-of-reference entry for the entity '{entity_name}' in the {domain} domain,
using ONLY the FA Handbook evidence gathered below. Do not invent content not supported by evidence.

EVIDENCE:
{evidence}

Respond using this exact format:

FORMAL_DEFINITION:
[If an explicit 'X means Y' or 'X is defined as Y' statement exists, quote it exactly.
If the entity appears but is never formally defined, write a concise factual description (2–4 sentences).
If the entity does not appear anywhere in the evidence, write: Not defined in FA Handbook.]

DOMAIN_CONTEXT:
[Role and function within the {domain} domain, related entities, authority or scope. 2–4 sentences.]

GOVERNANCE:
[Rules imposed ON '{entity_name}' by the FA, and authority EXERCISED BY '{entity_name}'.
Cite section/rule numbers where possible (e.g. Rule E1, Section 28). 3–8 bullet points.]

BUSINESS_RULES:
[Eligibility conditions, constraints, key business rules. 3–5 bullet points or 2–3 sentences.
If none stated: Not specified in FA Handbook.]

LIFECYCLE_STATES:
[States or statuses this entity can be in. If not applicable: Not specified in FA Handbook.]

DATA_CLASSIFICATION:
[Personal or sensitive data categories associated with this entity. If none: Not specified in FA Handbook.]

REGULATORY_CONTEXT:
[External legislation referenced (e.g. UK GDPR, Companies Act). If none: Not specified in FA Handbook.]

ASSOCIATED_AGREEMENTS:
[Agreement types that govern this entity. If none: Not specified in FA Handbook.]
"""


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class RetrieverConfig:
    """Configuration for AgenticRetriever.

    Attributes:
        max_iterations:  Maximum LLM-driven retrieval steps before forcing synthesis.
        rag_config_path: Path to rag_config.yaml (resolved relative to cwd).
        section_prefix:  ChromaDB collection prefix for handbook sections.
        keyword_chunk_limit: Max alias keyword chunks injected into synthesis prompt.
        verbose:         Print per-iteration trace.
    """

    max_iterations: int = 5
    rag_config_path: Path = field(default_factory=lambda: _DEFAULT_RAG_CONFIG)
    section_prefix: str = "fa_handbook"
    keyword_chunk_limit: int = 8
    verbose: bool = False


# ---------------------------------------------------------------------------
# AgenticRetriever
# ---------------------------------------------------------------------------


class AgenticRetriever:
    """LLM-driven iterative retrieval for a single entity.

    Usage:
        retriever = AgenticRetriever()
        result = retriever.retrieve_entity_context("Club Official", "PARTY", aliases=["officer", "director"])
        # result is a dict with keys: formal_definition, domain_context, governance_rules, ...
    """

    def __init__(self, config: RetrieverConfig | None = None) -> None:
        self.config = config or RetrieverConfig()
        self._rag_config: Any = None  # lazy-loaded

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def retrieve_entity_context(
        self,
        entity_name: str,
        domain: str,
        aliases: list[str] | None = None,
    ) -> dict:
        """Run the agentic ReAct loop to gather handbook context for an entity.

        Returns a dict with keys:
            formal_definition, domain_context, governance_rules, business_rules,
            lifecycle_states, data_classification, regulatory_context,
            associated_agreements, agentic_trace (list of iteration dicts)
        """
        aliases = aliases or []
        rag_config = self._get_rag_config()
        observations: list[dict] = []
        tried_queries: set[str] = set()
        tried_keyword_sets: list[frozenset] = []
        trace: list[dict] = []

        for iteration in range(self.config.max_iterations):
            # Step A: LLM decides next action
            action = self._decide_action(
                entity_name=entity_name,
                aliases=aliases,
                observations=observations,
                tried_queries=tried_queries,
                tried_keyword_sets=tried_keyword_sets,
            )
            trace.append({"iteration": iteration + 1, "action": action})

            if self.config.verbose:
                print(f"    [agentic iter {iteration + 1}] action={action['type']} "
                      + (f"query={action.get('query','')[:60]}" if action["type"] == "RETRIEVE" else
                         f"terms={action.get('terms',[])}"))

            if action["type"] == "DONE":
                break

            # Step B: Execute the chosen action
            if action["type"] == "RETRIEVE":
                query = action["query"]
                sections = action.get("sections") or []
                if not sections:
                    # Auto-route: BM25 section discovery.
                    # Pass the LLM's chosen query as an extra routing term so that
                    # reformulated queries (e.g. "casual worker employment status"
                    # on iteration 2) can surface different sections than iteration 1.
                    sections = self._route_sections(entity_name, aliases, rag_config, extra_query=query)

                obs = self._rag_retrieve(query, sections, rag_config)
                tried_queries.add(query)
                observations.append({
                    "type": "rag",
                    "query": query,
                    "sections": sections,
                    "content": obs,
                    "has_content": bool(obs) and len(obs) > 100,
                })

            elif action["type"] == "KEYWORD":
                terms = action.get("terms", [])
                if not terms:
                    terms = aliases[:3]
                term_set = frozenset(t.lower() for t in terms)
                if term_set not in tried_keyword_sets:
                    tried_keyword_sets.append(term_set)
                    chunks, sections_found = self._keyword_scan(terms, rag_config)
                    observations.append({
                        "type": "keyword",
                        "terms": terms,
                        "sections_found": sections_found,
                        "chunks": chunks,
                        "has_content": bool(chunks),
                    })

        # Step C: Synthesise final answer from all gathered evidence
        result = self._synthesise(entity_name, domain, observations, rag_config)
        result["agentic_trace"] = trace
        result["iterations_used"] = len(trace)
        return result

    # ------------------------------------------------------------------
    # LLM-driven decision
    # ------------------------------------------------------------------

    def _decide_action(
        self,
        entity_name: str,
        aliases: list[str],
        observations: list[dict],
        tried_queries: set[str],
        tried_keyword_sets: list[frozenset],
    ) -> dict:
        """Ask the LLM what to do next. Returns an action dict.

        This is the critical agentic step: the LLM reads what has been
        retrieved so far and decides the best next move — not a keyword
        heuristic, not a fixed sequence.
        """
        # Build observations summary for the LLM
        obs_summary = self._format_observations(observations)
        tried_summary = _format_tried(tried_queries, tried_keyword_sets)

        prompt = _DECISION_PROMPT.format(
            entity_name=entity_name,
            aliases=", ".join(aliases) if aliases else "none",
            observations_summary=obs_summary,
            tried_summary=tried_summary,
        )

        # Early-exit: skip LLM call if no observations yet (always RETRIEVE first).
        # Use a structured question (not bare entity name) so semantic similarity
        # activates chunks where the entity appears in governance/definition context
        # rather than only where the name is the primary subject.
        if not observations:
            return {
                "type": "RETRIEVE",
                "query": (
                    f"What is '{entity_name}' in the FA Handbook? "
                    "Provide its definition, governance rules, and regulatory context."
                ),
                "sections": [],
            }

        try:
            llm = self._get_llm()
            response = str(llm.complete(prompt)).strip()
            action = _parse_action(response)

            # Guard: if LLM wants to stop but no *substantive* content has been
            # found yet and no keyword scan has been attempted, force one keyword
            # pass first.  "Substantive" means the retrieval returned real content,
            # not just boilerplate ("Not defined in FA Handbook", "No governance
            # rules are imposed on...", etc.).  This catches the common failure mode
            # where iter 1 returns > 100 chars of boilerplate so has_content=True,
            # the LLM reads "found content" and declares DONE — even though the
            # content is semantically empty.
            if action["type"] == "DONE":
                has_substantive = any(
                    o.get("has_content") and not _is_boilerplate(o.get("content", ""))
                    for o in observations
                    if o["type"] == "rag"
                ) or any(
                    o.get("has_content")
                    for o in observations
                    if o["type"] == "keyword"
                )
                no_keyword_tried = not any(o["type"] == "keyword" for o in observations)
                if not has_substantive and no_keyword_tried:
                    terms = aliases[:3] if aliases else [entity_name]
                    return {"type": "KEYWORD", "terms": terms}

            return action
        except Exception as e:
            logger.warning("_decide_action LLM call failed (%s) — forcing DONE", e)
            return {"type": "DONE"}

    # ------------------------------------------------------------------
    # Retrieval helpers
    # ------------------------------------------------------------------

    def _route_sections(
        self,
        entity_name: str,
        aliases: list[str],
        rag_config: Any,
        extra_query: str | None = None,
    ) -> list[str]:
        """BM25 section routing for entity name + aliases + optional LLM query.

        extra_query: the LLM's reformulated query text (e.g. from iteration 2+).
        Passed as an additional BM25 term so reformulated queries can surface
        sections the entity name + aliases alone would miss.
        """
        from elt_llm_query.query import discover_relevant_sections, find_sections_by_keyword

        seen: set[str] = set()
        sections: list[str] = []

        # BM25 routing with all aliases
        bm25_sections = discover_relevant_sections(
            entity_name=entity_name,
            section_prefix=self.config.section_prefix,
            rag_config=rag_config,
            threshold=0.0,
            bm25_top_k=3,
            aliases=aliases,
        )
        for s in bm25_sections:
            if s not in seen:
                sections.append(s)
                seen.add(s)

        # If the LLM chose a reformulated query, also route with it as entity_name.
        # This allows iteration 2+ RETRIEVE calls to discover sections that the
        # original entity name / aliases didn't surface.
        if extra_query and extra_query.lower() != entity_name.lower():
            extra_sections = discover_relevant_sections(
                entity_name=extra_query,
                section_prefix=self.config.section_prefix,
                rag_config=rag_config,
                threshold=0.0,
                bm25_top_k=3,
                aliases=[],
            )
            for s in extra_sections:
                if s not in seen:
                    sections.append(s)
                    seen.add(s)

        # Keyword scan for entity name + all alias terms
        for term in [entity_name] + aliases:
            ks, _ = find_sections_by_keyword(term, self.config.section_prefix, rag_config)
            for s in ks:
                if s not in seen:
                    sections.append(s)
                    seen.add(s)

        return sections

    def _rag_retrieve(self, query: str, sections: list[str], rag_config: Any) -> str:
        """Run query_collections and return the synthesised response text."""
        from elt_llm_query.query import query_collections

        if not sections:
            return ""
        try:
            result = query_collections(
                collection_names=sections,
                query=query,
                rag_config=rag_config,
                iterative=False,
            )
            return result.response.strip()
        except Exception as e:
            logger.warning("_rag_retrieve failed for query=%r: %s", query[:60], e)
            return ""

    def _keyword_scan(self, terms: list[str], rag_config: Any) -> tuple[list[str], list[str]]:
        """Verbatim keyword scan across all sections for the given terms.

        Returns (chunks, sections_found).
        """
        from elt_llm_query.query import find_sections_by_keyword

        seen_sections: set[str] = set()
        seen_chunks: set[str] = set()
        all_sections: list[str] = []
        all_chunks: list[str] = []

        for term in terms:
            ks, kc = find_sections_by_keyword(term, self.config.section_prefix, rag_config)
            for s in ks:
                if s not in seen_sections:
                    all_sections.append(s)
                    seen_sections.add(s)
            for c in kc:
                key = " ".join(c.split())
                if key not in seen_chunks:
                    all_chunks.append(c)
                    seen_chunks.add(key)

        return all_chunks, all_sections

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    def _synthesise(
        self,
        entity_name: str,
        domain: str,
        observations: list[dict],
        rag_config: Any,
    ) -> dict:
        """Combine all gathered evidence into a structured entity record.

        If observations are empty, returns a not-found record without an LLM call.
        """
        empty = {
            "formal_definition": "",
            "domain_context": "",
            "governance_rules": "",
            "business_rules": "",
            "lifecycle_states": "",
            "data_classification": "",
            "regulatory_context": "",
            "associated_agreements": "",
        }

        if not any(o.get("has_content") for o in observations):
            return empty

        # Build evidence block from all observations
        evidence_parts: list[str] = []
        for obs in observations:
            if obs["type"] == "rag" and obs.get("has_content"):
                evidence_parts.append(
                    f"[RAG retrieval — query: {obs['query']!r}]\n{obs['content']}"
                )
            elif obs["type"] == "keyword" and obs.get("has_content"):
                chunk_text = "\n".join(
                    f"  - {c[:500]}" for c in obs["chunks"][: self.config.keyword_chunk_limit]
                )
                evidence_parts.append(
                    f"[Keyword scan — terms: {obs['terms']!r}]\n{chunk_text}"
                )

        if not evidence_parts:
            return empty

        evidence = "\n\n".join(evidence_parts)
        prompt = _SYNTHESIS_PROMPT.format(
            entity_name=entity_name,
            domain=domain,
            evidence=evidence,
        )

        try:
            llm = self._get_llm()
            response = str(llm.complete(prompt)).strip()
            return _parse_synthesis(response, empty)
        except Exception as e:
            logger.warning("_synthesise LLM call failed (%s)", e)
            return empty

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_rag_config(self) -> Any:
        if self._rag_config is None:
            from elt_llm_core.config import load_config
            self._rag_config = load_config(self.config.rag_config_path)
        return self._rag_config

    def _get_llm(self) -> Any:
        from elt_llm_core.models import create_llm_model
        return create_llm_model(self._get_rag_config().ollama)

    @staticmethod
    def _format_observations(observations: list[dict]) -> str:
        if not observations:
            return "  (none yet)"
        parts = []
        for i, obs in enumerate(observations, 1):
            if obs["type"] == "rag":
                status = "found content" if obs.get("has_content") else "sparse/empty"
                parts.append(
                    f"  Observation {i}: RAG retrieve — query={obs['query']!r} "
                    f"sections={obs.get('sections', [])} → {status}\n"
                    f"    Preview: {obs['content'][:200].replace(chr(10), ' ')!r}"
                )
            elif obs["type"] == "keyword":
                status = f"{len(obs['chunks'])} chunks found" if obs.get("has_content") else "no matches"
                parts.append(
                    f"  Observation {i}: Keyword scan — terms={obs['terms']!r} → {status}"
                )
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------


def _parse_action(text: str) -> dict:
    """Parse LLM decision response into an action dict.

    Expected formats (one per response):
      RETRIEVE query: "some query text"
      RETRIEVE sections: ["s01","s05"] query: "some query text"
      KEYWORD terms: ["term1", "term2"]
      DONE
    """
    text = text.strip()
    upper = text.upper()

    if upper.startswith("DONE"):
        return {"type": "DONE"}

    if upper.startswith("KEYWORD"):
        terms = _parse_list(text, "terms")
        return {"type": "KEYWORD", "terms": terms}

    if upper.startswith("RETRIEVE"):
        sections = _parse_list(text, "sections")
        query_m = re.search(r'query:\s*"([^"]+)"', text, re.IGNORECASE)
        query = query_m.group(1).strip() if query_m else ""
        if query:
            return {"type": "RETRIEVE", "query": query, "sections": sections}

    # Fallback: treat as DONE to avoid infinite loops
    logger.warning("_parse_action: unrecognised response %r — falling back to DONE", text[:100])
    return {"type": "DONE"}


def _parse_list(text: str, key: str) -> list[str]:
    """Extract a JSON-like list value for a key from action text."""
    m = re.search(rf'{key}:\s*(\[[^\]]*\])', text, re.IGNORECASE)
    if not m:
        return []
    try:
        import json
        raw = m.group(1)
        # Normalise single-quotes to double-quotes
        raw = raw.replace("'", '"')
        return json.loads(raw)
    except Exception:
        # Fallback: split on commas
        inner = re.sub(r'[\[\]"\']', '', m.group(1))
        return [s.strip() for s in inner.split(",") if s.strip()]


def _parse_synthesis(response: str, empty: dict) -> dict:
    """Parse the structured synthesis response into a field dict."""
    result = dict(empty)

    def _extract(label: str) -> str:
        m = re.search(rf"{label}:\s*(.*?)(?=\n[A-Z_]+:|\Z)", response, re.DOTALL | re.IGNORECASE)
        return m.group(1).strip() if m else ""

    result["formal_definition"] = _extract("FORMAL_DEFINITION")
    result["domain_context"] = _extract("DOMAIN_CONTEXT")
    result["governance_rules"] = _extract("GOVERNANCE")
    result["business_rules"] = _extract("BUSINESS_RULES")
    result["lifecycle_states"] = _extract("LIFECYCLE_STATES")
    result["data_classification"] = _extract("DATA_CLASSIFICATION")
    result["regulatory_context"] = _extract("REGULATORY_CONTEXT")
    result["associated_agreements"] = _extract("ASSOCIATED_AGREEMENTS")
    return result


def _format_tried(tried_queries: set[str], tried_keyword_sets: list[frozenset]) -> str:
    parts = []
    for q in sorted(tried_queries):
        parts.append(f"  RAG query: {q!r}")
    for ks in tried_keyword_sets:
        parts.append(f"  Keyword scan: {sorted(ks)!r}")
    return "\n".join(parts) if parts else "  (none yet)"
