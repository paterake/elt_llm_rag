"""Query interface for RAG systems."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from llama_index.core import VectorStoreIndex, Settings

from elt_llm_core.config import RagConfig
from elt_llm_core.models import create_embedding_model, create_llm_model
from elt_llm_core.query_engine import QueryConfig, QueryResult, create_query_engine
from elt_llm_core.vector_store import (
    ChromaConfig,
    create_chroma_client,
    create_storage_context,
    get_docstore_path,
    list_collections_by_prefix,
)

logger = logging.getLogger(__name__)


def load_index(
    collection_name: str,
    rag_config: RagConfig,
) -> VectorStoreIndex:
    """Load an existing vector index from Chroma.

    Args:
        collection_name: Name of the Chroma collection.
        rag_config: RAG configuration.

    Returns:
        VectorStoreIndex loaded from storage.
    """
    logger.info("Loading index from Chroma: %s", collection_name)

    # Create Chroma client
    chroma_client = create_chroma_client(rag_config.chroma)

    # Create storage context
    storage_context = create_storage_context(
        chroma_client,
        collection_name,
    )

    # Set embedding model
    embed_model = create_embedding_model(rag_config.ollama)
    Settings.embed_model = embed_model

    # Load index from storage
    index = VectorStoreIndex.from_vector_store(
        storage_context.vector_store,
        storage_context=storage_context,
    )

    logger.info("Index loaded successfully")
    return index


def load_indices(
    collection_names: list[str],
    rag_config: RagConfig,
) -> list[VectorStoreIndex]:
    """Load multiple vector indices from Chroma.

    Args:
        collection_names: List of collection names.
        rag_config: RAG configuration.

    Returns:
        List of VectorStoreIndex instances.
    """
    indices = []
    for name in collection_names:
        try:
            index = load_index(name, rag_config)
            indices.append(index)
            logger.info("Loaded index for collection: %s", name)
        except Exception as e:
            logger.warning("Failed to load collection '%s': %s", name, e)
    return indices


def resolve_collection_prefixes(
    prefixes: list[str],
    rag_config: RagConfig,
) -> list[str]:
    """Resolve prefix patterns to actual collection names from ChromaDB.

    Uses '{prefix}_' matching so 'fa_leanix' resolves to all 'fa_leanix_*'
    collections that currently exist in the database.

    Args:
        prefixes: List of prefix strings (without trailing underscore).
        rag_config: RAG configuration (used to locate the ChromaDB instance).

    Returns:
        Sorted list of matching collection names. Warns if a prefix matches nothing.
    """
    if not prefixes:
        return []

    client = create_chroma_client(rag_config.chroma)
    resolved: list[str] = []
    for prefix in prefixes:
        matches = list_collections_by_prefix(client, prefix)
        if not matches:
            logger.warning("No collections found matching prefix '%s_*'", prefix)
        else:
            logger.info("Prefix '%s' resolved to: %s", prefix, matches)
            resolved.extend(matches)
    return resolved


def discover_relevant_sections(
    entity_name: str,
    section_prefix: str,
    rag_config: RagConfig,
    threshold: float = 0.0,
    bm25_top_k: int = 3,
) -> list[str]:
    """Stage-1 BM25 section routing: find handbook sections relevant to entity_name.

    Runs BM25 keyword retrieval (no LLM, no embedding) against every collection
    matching ``{section_prefix}_sNN``. Returns collection names whose best BM25
    score exceeds ``threshold``, sorted by score descending.

    This is a fast, no-LLM operation — it only reads docstore JSON files and runs
    in-memory BM25 scoring. Typical runtime: 1-3 seconds for 44 sections.

    Args:
        entity_name: Entity name used as the BM25 query (e.g. "Match Official").
        section_prefix: ChromaDB collection prefix (e.g. "fa_handbook").
        rag_config: RAG configuration (used to locate docstores).
        threshold: Minimum BM25 score to include a section (default 0.0 = any hit).
        bm25_top_k: BM25 candidates per section for scoring (default 3).

    Returns:
        Collection names sorted by relevance score (best first).
        Returns empty list if BM25 is unavailable or no sections score above threshold.
    """
    try:
        from llama_index.core import StorageContext
        from llama_index.retrievers.bm25 import BM25Retriever
        import logging as _logging
        _logging.getLogger("bm25s").setLevel(_logging.WARNING)
    except ImportError:
        logger.warning(
            "llama-index-retrievers-bm25 not installed — section routing disabled. "
            "Run: uv add llama-index-retrievers-bm25 --package elt-llm-query"
        )
        return []

    # Resolve all collections for this prefix, then filter to sNN pattern
    all_collections = resolve_collection_prefixes([section_prefix], rag_config)
    section_pat = re.compile(rf'^{re.escape(section_prefix)}_s\d{{2}}$')
    section_collections = [c for c in all_collections if section_pat.match(c)]

    if not section_collections:
        logger.warning("No section collections found matching '%s_sNN'", section_prefix)
        return []

    scored: list[tuple[str, float]] = []

    for collection_name in sorted(section_collections):
        docstore_path = get_docstore_path(rag_config.chroma, collection_name)
        if not docstore_path.exists():
            continue

        try:
            storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
            nodes = list(storage.docstore.docs.values())
            if not nodes:
                continue

            k = min(bm25_top_k, len(nodes))
            bm25 = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=k)
            hits = bm25.retrieve(entity_name)
            if not hits:
                continue

            max_score = max((n.score for n in hits if n.score is not None), default=0.0)
            if max_score >= threshold:
                scored.append((collection_name, max_score))

        except Exception as e:
            logger.debug("BM25 section scan failed for '%s': %s", collection_name, e)

    scored.sort(key=lambda x: x[1], reverse=True)
    logger.info(
        "Section routing '%s': %d/%d sections above threshold %.2f → %s",
        entity_name, len(scored), len(section_collections), threshold,
        [c for c, _ in scored[:5]],
    )
    return [c for c, _ in scored]


def _build_hybrid_retriever(
    index: VectorStoreIndex,
    collection_name: str,
    rag_config: RagConfig,
    top_k: int,
):
    """Build a hybrid BM25 + vector retriever for a collection.

    Falls back to pure vector search if the docstore doesn't exist or BM25
    is unavailable (e.g. package not installed).

    Args:
        index: Loaded VectorStoreIndex for vector retrieval.
        collection_name: Collection name (used to locate the docstore).
        rag_config: RAG configuration.
        top_k: Number of results each retriever should return before merging.

    Returns:
        A retriever — either QueryFusionRetriever (hybrid) or plain vector retriever.
    """
    docstore_path = get_docstore_path(rag_config.chroma, collection_name)
    logger.info("Hybrid search: resolved docstore path = %s", docstore_path.resolve())

    if not docstore_path.exists():
        logger.warning(
            "No docstore found at '%s' for collection '%s' — run ingestion first to enable hybrid search. "
            "Falling back to vector-only.",
            docstore_path.resolve(),
            collection_name,
        )
        return index.as_retriever(similarity_top_k=top_k)

    try:
        from llama_index.core import StorageContext
        from llama_index.core.retrievers import QueryFusionRetriever
        from llama_index.retrievers.bm25 import BM25Retriever

        # bm25s resets its own logger to DEBUG on import — suppress it after the fact
        import logging as _logging
        _logging.getLogger("bm25s").setLevel(_logging.WARNING)

        docstore_storage = StorageContext.from_defaults(persist_dir=str(docstore_path))
        nodes = list(docstore_storage.docstore.docs.values())
        logger.info("Loaded %d nodes from docstore at '%s'", len(nodes), docstore_path.resolve())

        if not nodes:
            logger.warning("Docstore for '%s' is empty; falling back to vector-only.", collection_name)
            return index.as_retriever(similarity_top_k=top_k)

        logger.info(
            "Building hybrid retriever for '%s' (%d nodes from docstore)",
            collection_name,
            len(nodes),
        )

        # QueryFusionRetriever reads Settings.llm at construction time.
        # Set it now with Ollama so it doesn't fall back to OpenAI.
        from elt_llm_core.models import create_llm_model
        Settings.llm = create_llm_model(rag_config.ollama)

        # BM25 requires k <= number of nodes; cap it to avoid a warning on small collections
        bm25_top_k = min(top_k, len(nodes))
        vector_retriever = index.as_retriever(similarity_top_k=top_k)
        bm25_retriever = BM25Retriever.from_defaults(nodes=nodes, similarity_top_k=bm25_top_k)
        logger.info("BM25Retriever created successfully for '%s'", collection_name)

        hybrid_retriever = QueryFusionRetriever(
            retrievers=[vector_retriever, bm25_retriever],
            similarity_top_k=top_k,
            num_queries=rag_config.query.num_queries,
            mode="reciprocal_rerank",
        )
        logger.info("Hybrid (QueryFusionRetriever) ready for '%s'", collection_name)
        return hybrid_retriever

    except ImportError:
        logger.warning(
            "llama-index-retrievers-bm25 not installed; falling back to vector-only. "
            "Run: uv add llama-index-retrievers-bm25"
        )
        return index.as_retriever(similarity_top_k=top_k)
    except Exception as e:
        logger.warning(
            "Hybrid retriever failed for '%s': %s — falling back to vector-only.",
            collection_name,
            e,
            exc_info=True,
        )
        return index.as_retriever(similarity_top_k=top_k)


def _apply_mmr(
    query_norm: "np.ndarray",
    doc_norms: "np.ndarray",
    nodes: list,
    k: int,
    threshold: float,
) -> list:
    """Select k diverse nodes via Maximal Marginal Relevance.

    Iteratively picks the node that maximises:
        threshold * sim(node, query) - (1 - threshold) * max_sim(node, selected)

    Args:
        query_norm: Normalised query embedding (1-D).
        doc_norms: Normalised document embeddings (N × D).
        nodes: Candidate NodeWithScore list aligned with doc_norms rows.
        k: Number of nodes to select.
        threshold: Lambda — 0 = max diversity, 1 = max relevance.

    Returns:
        MMR-selected subset (up to k nodes) in selection order.
    """
    import numpy as np

    n = len(nodes)
    k = min(k, n)
    relevance = doc_norms @ query_norm      # (N,) cosine sim to query
    sim_matrix = doc_norms @ doc_norms.T    # (N,N) pairwise cosine sim

    selected: list[int] = []
    remaining = list(range(n))

    while len(selected) < k and remaining:
        if not selected:
            best = max(remaining, key=lambda i: float(relevance[i]))
        else:
            sel = selected  # capture for lambda
            best = max(
                remaining,
                key=lambda i: (
                    threshold * float(relevance[i])
                    - (1 - threshold) * float(np.max(sim_matrix[i, sel]))
                ),
            )
        selected.append(best)
        remaining.remove(best)

    return [nodes[i] for i in selected]


def _rerank_nodes_embedding(
    query: str,
    nodes: list,
    rag_config: RagConfig,
) -> list:
    """Rerank nodes by query-document cosine similarity using the Ollama embedding model.

    Uses the same nomic-embed-text model already running locally — no external downloads.
    Computes a fresh embedding for the query and each candidate chunk, then re-sorts by
    cosine similarity and trims to reranker_top_k.

    Args:
        query: The query string.
        nodes: List of NodeWithScore to rerank.
        rag_config: RAG configuration.

    Returns:
        Reranked list of NodeWithScore with cosine similarity as score.
    """
    import numpy as np
    from llama_index.core.schema import NodeWithScore

    embed_model = create_embedding_model(rag_config.ollama)
    top_k = rag_config.query.reranker_top_k

    logger.info(
        "Embedding reranker%s: scoring %d nodes with '%s'",
        "+MMR" if rag_config.query.use_mmr else "",
        len(nodes),
        rag_config.ollama.embedding_model,
    )

    query_emb = np.array(embed_model.get_text_embedding(query))
    texts = [n.node.text for n in nodes]
    doc_embs = np.array(embed_model.get_text_embedding_batch(texts))

    # Normalise once — reused for both relevance scoring and MMR
    query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-9)
    doc_norms = doc_embs / (np.linalg.norm(doc_embs, axis=1, keepdims=True) + 1e-9)

    if rag_config.query.use_mmr:
        # Single embedding pass: MMR selects top_k diverse+relevant nodes
        selected = _apply_mmr(query_norm, doc_norms, nodes, top_k, rag_config.query.mmr_threshold)
        node_to_idx = {id(n): i for i, n in enumerate(nodes)}
        relevance = doc_norms @ query_norm
        result = [
            NodeWithScore(node=n.node, score=float(relevance[node_to_idx[id(n)]]))
            for n in selected
        ]
        result.sort(key=lambda x: x.score, reverse=True)
    else:
        scores = doc_norms @ query_norm
        ranked = sorted(zip(nodes, scores), key=lambda x: float(x[1]), reverse=True)
        result = [NodeWithScore(node=n.node, score=float(s)) for n, s in ranked[:top_k]]

    logger.info(
        "Embedding reranker: kept top %d/%d (scores %.4f – %.4f)",
        len(result), len(nodes),
        result[0].score if result else 0.0,
        result[-1].score if result else 0.0,
    )
    return result


def _rerank_nodes_cross_encoder(
    query: str,
    nodes: list,
    rag_config: RagConfig,
) -> list:
    """Rerank nodes using a cross-encoder (sentence-transformers).

    Cross-encoders score query+document jointly rather than independently,
    yielding higher ranking quality than embedding cosine similarity at the
    cost of ~200–800 ms extra latency per rerank call.

    Requires: sentence-transformers>=3.0.0
      uv add sentence-transformers --package elt-llm-query
    Model: rag_config.query.reranker_model (cross-encoder/ms-marco-MiniLM-L-6-v2)

    Falls back to embedding reranker if sentence-transformers is not installed.
    """
    from llama_index.core.schema import NodeWithScore

    try:
        from sentence_transformers import CrossEncoder
    except ImportError:
        logger.warning(
            "sentence-transformers not installed; falling back to embedding reranker. "
            "Run: uv add sentence-transformers --package elt-llm-query"
        )
        return _rerank_nodes_embedding(query, nodes, rag_config)

    try:
        top_k = rag_config.query.reranker_top_k
        model = CrossEncoder(rag_config.query.reranker_model)
        pairs = [(query, n.node.text) for n in nodes]
        scores = model.predict(pairs)
        ranked = sorted(zip(nodes, scores), key=lambda x: float(x[1]), reverse=True)
        result = [NodeWithScore(node=n.node, score=float(s)) for n, s in ranked[:top_k]]
        logger.info(
            "Cross-encoder reranker (%s): kept top %d/%d nodes",
            rag_config.query.reranker_model, len(result), len(nodes),
        )
        return result
    except Exception as e:
        logger.warning("Cross-encoder reranker failed: %s — falling back to embedding.", e)
        return _rerank_nodes_embedding(query, nodes, rag_config)


def _reorder_for_lost_in_middle(nodes: list) -> list:
    """Reorder context chunks to mitigate the lost-in-the-middle effect.

    LLMs attend best to content at the start and end of the context window.
    This interleaves reranked chunks so the most-relevant appear at both ends:

        Input  (best→worst): [A, B, C, D, E, F, G, H]
        Output:              [A, C, E, G, H, F, D, B]

    The highest-scoring chunk goes to position 0, second-highest to position -1,
    third-highest to position 1, and so on.

    Reference: Liu et al. (2023), "Lost in the Middle".
    """
    if len(nodes) <= 2:
        return nodes
    result: list = [None] * len(nodes)
    left, right = 0, len(nodes) - 1
    for i, node in enumerate(nodes):
        if i % 2 == 0:
            result[left] = node
            left += 1
        else:
            result[right] = node
            right -= 1
    return result


def _rerank_nodes(
    query: str,
    nodes: list,
    rag_config: RagConfig,
) -> list:
    """Rerank retrieved nodes and optionally reorder for LLM attention.

    Pipeline:
      1. Rerank by relevance (+ optional MMR diversity):
           "embedding"     — cosine similarity via Ollama (default, no extra packages)
           "cross-encoder" — sentence-transformers CrossEncoder (higher quality)
      2. Optional lost-in-the-middle reordering (use_lost_in_middle: true)

    Falls back gracefully: cross-encoder → embedding → original list.

    Args:
        query: The query string.
        nodes: List of NodeWithScore from prior retrieval.
        rag_config: RAG configuration.

    Returns:
        Reranked (and optionally reordered) list of NodeWithScore.
    """
    if not rag_config.query.use_reranker or not nodes:
        return nodes

    strategy = rag_config.query.reranker_strategy

    if strategy not in ("embedding", "cross-encoder"):
        logger.warning(
            "Unknown reranker_strategy '%s'; using 'embedding'.", strategy
        )

    if strategy == "cross-encoder":
        reranked = _rerank_nodes_cross_encoder(query, nodes, rag_config)
    else:
        try:
            reranked = _rerank_nodes_embedding(query, nodes, rag_config)
        except Exception as e:
            logger.warning("Embedding reranker failed: %s — returning original nodes.", e)
            return nodes

    if rag_config.query.use_lost_in_middle and reranked:
        reranked = _reorder_for_lost_in_middle(reranked)
        logger.info("Lost-in-middle reordering applied to %d chunks", len(reranked))

    return reranked


def query_collection(
    collection_name: str,
    query: str,
    rag_config: RagConfig,
) -> QueryResult:
    """Query a collection.

    Args:
        collection_name: Name of the Chroma collection.
        query: Query string.
        rag_config: RAG configuration.

    Returns:
        QueryResult with response and source nodes.
    """
    logger.info("Querying collection '%s': %s", collection_name, query)

    # Load index
    index = load_index(collection_name, rag_config)

    # When reranker is enabled, retrieve more candidates upfront before filtering
    retrieve_k = (
        rag_config.query.reranker_retrieve_k
        if rag_config.query.use_reranker
        else rag_config.query.similarity_top_k
    )

    # Build retriever — hybrid (BM25 + vector) when enabled and docstore exists
    retriever = None
    if rag_config.query.use_hybrid_search:
        retriever = _build_hybrid_retriever(index, collection_name, rag_config, retrieve_k)

    if rag_config.query.use_reranker:
        from llama_index.core.response_synthesizers import get_response_synthesizer
        if retriever is None:
            retriever = index.as_retriever(similarity_top_k=retrieve_k)
        nodes = retriever.retrieve(query)
        nodes = _rerank_nodes(query, nodes, rag_config)

        llm = create_llm_model(rag_config.ollama)
        system_prompt = rag_config.query.system_prompt
        if system_prompt:
            llm.system_prompt = system_prompt
        Settings.llm = llm

        synthesizer = get_response_synthesizer(llm=llm)
        response = synthesizer.synthesize(query, nodes=nodes)
        source_nodes = [
            {"text": n.node.text, "metadata": n.node.metadata, "score": n.score}
            for n in nodes
        ]
        logger.info("Query complete")
        return QueryResult(response=str(response), source_nodes=source_nodes)

    # Reranker disabled — original path unchanged
    query_config = QueryConfig(
        similarity_top_k=rag_config.query.similarity_top_k,
        system_prompt=rag_config.query.system_prompt,
    )
    result = query_index(index, query, rag_config, query_config, retriever=retriever)
    logger.info("Query complete")
    return result


def query_collections(
    collection_names: list[str],
    query: str,
    rag_config: RagConfig,
) -> QueryResult:
    """Query multiple collections and combine results.

    Retrieves chunks from all collections via vector search first, then makes
    a single LLM synthesis call with all combined context. This ensures the LLM
    sees relevant content from every collection rather than discarding all but
    the first collection's response.

    Args:
        collection_names: List of collection names to query.
        query: Query string.
        rag_config: RAG configuration.

    Returns:
        QueryResult with combined response and source nodes.
    """
    from llama_index.core.response_synthesizers import get_response_synthesizer

    logger.info("Querying %d collections: %s", len(collection_names), collection_names)

    # Load all indices
    indices = load_indices(collection_names, rag_config)

    if not indices:
        return QueryResult(
            response="No collections found. Please ingest documents first.",
            source_nodes=[],
        )

    top_k = rag_config.query.similarity_top_k
    # When reranker is on, fetch more per collection so the reranker has real candidates to score
    per_collection_k = (
        max(rag_config.query.reranker_retrieve_k // max(len(collection_names), 1), 5)
        if rag_config.query.use_reranker
        else max(top_k, 5)
    )

    # Step 1: Retrieve chunks from every collection — hybrid or vector search, no LLM yet.
    # Full-context mode: if a collection has ≤ full_context_max_chunks nodes, pass ALL of
    # them directly instead of running retrieval. Small focused sections fit in the LLM
    # context window and benefit from full visibility.
    from llama_index.core import StorageContext
    from llama_index.core.schema import NodeWithScore

    full_ctx_threshold = rag_config.query.full_context_max_chunks
    all_nodes = []
    for index, name in zip(indices, collection_names):
        docstore_path = get_docstore_path(rag_config.chroma, name)
        used_full_context = False
        if full_ctx_threshold > 0 and docstore_path.exists():
            try:
                ds = StorageContext.from_defaults(persist_dir=str(docstore_path))
                all_doc_nodes = list(ds.docstore.docs.values())
                if 0 < len(all_doc_nodes) <= full_ctx_threshold:
                    all_nodes.extend(
                        NodeWithScore(node=n, score=1.0) for n in all_doc_nodes
                    )
                    logger.info(
                        "Collection '%s': full-context mode (%d nodes ≤ threshold %d)",
                        name, len(all_doc_nodes), full_ctx_threshold,
                    )
                    used_full_context = True
            except Exception as e:
                logger.debug("Full-context check failed for '%s': %s", name, e)

        if not used_full_context:
            if rag_config.query.use_hybrid_search:
                retriever = _build_hybrid_retriever(index, name, rag_config, per_collection_k)
            else:
                retriever = index.as_retriever(similarity_top_k=per_collection_k)
            nodes = retriever.retrieve(query)
            all_nodes.extend(nodes)
            logger.info("Collection '%s' retrieved %d nodes (hybrid/vector)", name, len(nodes))

    if not all_nodes:
        return QueryResult(response="No relevant content found in any collection.", source_nodes=[])

    # Step 2: Merge candidates from all collections.
    # When reranker is enabled, do NOT pre-truncate to top_k here — pass all candidates to
    # the reranker so every collection stays represented in the scoring pool.
    # The reranker itself trims to reranker_top_k.
    # When reranker is disabled, truncate to similarity_top_k for the LLM.
    all_nodes.sort(key=lambda x: x.score or 0.0, reverse=True)
    if not rag_config.query.use_reranker:
        all_nodes = all_nodes[:top_k]

    # Step 2b: Cross-encoder reranking — replaces flat RRF scores with genuine relevance scores
    all_nodes = _rerank_nodes(query, all_nodes, rag_config)

    # Step 3: Single LLM synthesis call with all combined context
    llm = create_llm_model(rag_config.ollama)
    system_prompt = rag_config.query.system_prompt
    if system_prompt:
        llm.system_prompt = system_prompt
    Settings.llm = llm

    synthesizer = get_response_synthesizer(llm=llm)
    response = synthesizer.synthesize(query, nodes=all_nodes)

    source_nodes = [
        {
            "text": n.node.text,
            "metadata": n.node.metadata,
            "score": n.score,
        }
        for n in all_nodes
    ]

    return QueryResult(response=str(response), source_nodes=source_nodes)


def query_index(
    index: VectorStoreIndex,
    query: str,
    rag_config: RagConfig,
    query_config: QueryConfig,
    retriever=None,
) -> QueryResult:
    """Query an index.

    Args:
        index: VectorStoreIndex to query.
        query: Query string.
        rag_config: RAG configuration.
        query_config: Query configuration.
        retriever: Optional custom retriever (e.g. hybrid BM25+vector).

    Returns:
        QueryResult with response and source nodes.
    """
    from elt_llm_core.query_engine import query_index as core_query

    return core_query(index, query, rag_config.ollama, query_config, retriever=retriever)


def interactive_query(
    collection_name: str,
    rag_config: RagConfig,
) -> None:
    """Run interactive query session.

    Args:
        collection_name: Name of the Chroma collection.
        rag_config: RAG configuration.
    """
    print("\n=== RAG Query Interface ===")
    print(f"Collection: {collection_name}")
    print("Type 'quit' or 'exit' to stop\n")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        try:
            result = query_collection(collection_name, user_input, rag_config)
            print("\n=== Response ===\n")
            print(result.response)
            print(f"\n[Sources: {len(result.source_nodes)}]")
        except Exception as e:
            print(f"Error: {e}")


def interactive_query_collections(
    collection_names: list[str],
    rag_config: RagConfig,
) -> None:
    """Run interactive query session across multiple collections.

    Args:
        collection_names: List of collection names.
        rag_config: RAG configuration.
    """
    print("\n=== RAG Query Interface (Multi-Collection) ===")
    print(f"Collections: {', '.join(collection_names)}")
    print("Type 'quit' or 'exit' to stop\n")

    while True:
        try:
            user_input = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if not user_input:
            continue

        try:
            result = query_collections(collection_names, user_input, rag_config)
            print("\n=== Response ===\n")
            print(result.response)
            print(f"\n[Sources: {len(result.source_nodes)}]")
        except Exception as e:
            print(f"Error: {e}")
