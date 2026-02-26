"""Gradio GUI for ELT LLM RAG — Query and Ingest tabs.

Launch:
    uv run python -m elt_llm_api.app
    # → http://localhost:7860
"""
from __future__ import annotations

import logging
from pathlib import Path

import chromadb
import gradio as gr
import yaml

from elt_llm_core.config import RagConfig
from elt_llm_ingest.ingest import ingest_from_config
from elt_llm_query.query import query_collection, query_collections, resolve_collection_prefixes

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_HERE = Path(__file__).resolve()
RAG_CONFIG_PATH = _HERE.parents[3] / "elt_llm_ingest" / "config" / "rag_config.yaml"
PROFILES_DIR = _HERE.parents[3] / "elt_llm_query" / "llm_rag_profile"
INGEST_CONFIG_DIR = _HERE.parents[3] / "elt_llm_ingest" / "config"

# Suppress noisy library loggers
for _lib in ["httpx", "httpcore", "chromadb", "llama_index", "urllib3", "bm25s",
             "llama_index.retrievers.bm25"]:
    logging.getLogger(_lib).setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def list_profiles() -> list[str]:
    return sorted(f.stem for f in PROFILES_DIR.glob("*.yaml"))


def list_ingest_configs() -> list[str]:
    return [
        f.stem for f in sorted(INGEST_CONFIG_DIR.glob("*.yaml"))
        if not f.stem.startswith("todo_") and f.stem != "rag_config"
    ]


def load_profile(profile_name: str) -> tuple[list[str], RagConfig]:
    """Load a query profile YAML and return (collection_names, rag_config).

    Replicates the logic in elt_llm_query/runner.py query() function.
    """
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"
    with open(profile_path) as f:
        profile_data = yaml.safe_load(f)

    rag_config = RagConfig.from_yaml(RAG_CONFIG_PATH)

    # Explicit collections
    explicit = [c["name"] for c in profile_data.get("collections", [])]

    # Prefix-resolved collections
    prefixes = [p["name"] for p in profile_data.get("collection_prefixes", [])]
    resolved: list[str] = []
    if prefixes:
        try:
            resolved = resolve_collection_prefixes(prefixes, rag_config)
        except Exception:
            pass

    # Deduplicate, explicit first
    seen: set[str] = set(explicit)
    for name in resolved:
        if name not in seen:
            explicit.append(name)
            seen.add(name)
    collection_names = explicit

    # Apply profile-level query overrides
    query_overrides = profile_data.get("query", {})
    if "similarity_top_k" in query_overrides:
        rag_config.query.similarity_top_k = query_overrides["similarity_top_k"]
    if "system_prompt" in query_overrides:
        rag_config.query.system_prompt = query_overrides["system_prompt"]

    return collection_names, rag_config


def get_status() -> str:
    """Return a markdown table of current ChromaDB collections."""
    try:
        rag_config = RagConfig.from_yaml(RAG_CONFIG_PATH)
        persist_dir = Path(rag_config.chroma.persist_dir)
        client = chromadb.PersistentClient(path=str(persist_dir))
        collections = client.list_collections()

        if not collections:
            return "_No collections found. Run an ingest first._"

        docstore_dir = persist_dir / "docstores"
        lines = ["| Collection | Chunks | BM25 |", "|------------|--------|------|"]
        total_chunks = 0
        for col in sorted(collections, key=lambda c: c.name):
            if col.name == "file_hashes":
                continue
            count = col.count()
            total_chunks += count
            ds_path = docstore_dir / col.name / "docstore.json"
            bm25 = "✅" if ds_path.exists() else "❌"
            lines.append(f"| `{col.name}` | {count} | {bm25} |")

        lines.append(f"\n_Total: {len(collections)} collections, {total_chunks} chunks_")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Could not connect to ChromaDB: {e}"


# ---------------------------------------------------------------------------
# Query tab
# ---------------------------------------------------------------------------

def run_query(message: str, history: list, profile_name: str) -> str:
    if not profile_name:
        return "⚠️ Select a profile first."
    try:
        collection_names, rag_config = load_profile(profile_name)
    except Exception as e:
        return f"❌ Failed to load profile '{profile_name}': {e}"

    if not collection_names:
        return "⚠️ No collections found for this profile. Check ChromaDB status tab."

    try:
        if len(collection_names) == 1:
            result = query_collection(collection_names[0], message, rag_config)
        else:
            result = query_collections(collection_names, message, rag_config)
    except Exception as e:
        return f"❌ Query failed: {e}"

    # Format sources
    source_lines = []
    for i, src in enumerate(result.source_nodes, 1):
        score = src.get("score") or 0.0
        meta = src.get("metadata", {})
        label = meta.get("source") or meta.get("domain") or meta.get("type") or "unknown"
        preview = (src.get("text") or "")[:120].replace("\n", " ")
        source_lines.append(f"**[{i}]** `{label}` — score: {score:.4f}  \n_{preview}..._")

    sources_block = ""
    if source_lines:
        sources_block = "\n\n---\n**Sources**\n\n" + "\n\n".join(source_lines)

    return result.response + sources_block


# ---------------------------------------------------------------------------
# Ingest tab
# ---------------------------------------------------------------------------

def run_ingest(config_name: str) -> str:
    if not config_name:
        return "⚠️ Select a config first."
    config_path = INGEST_CONFIG_DIR / f"{config_name}.yaml"
    try:
        rag_config = RagConfig.from_yaml(RAG_CONFIG_PATH)
        ingest_from_config(config_path, rag_config)
        return f"✅ Ingestion complete: **{config_name}**"
    except Exception as e:
        return f"❌ Ingestion failed for '{config_name}': {e}"


# ---------------------------------------------------------------------------
# Build UI
# ---------------------------------------------------------------------------

def build_app() -> gr.Blocks:
    profiles = list_profiles()
    ingest_configs = list_ingest_configs()

    with gr.Blocks(title="ELT LLM RAG", theme=gr.themes.Soft()) as app:
        gr.Markdown("# ELT LLM RAG")

        with gr.Tabs():

            # ── Query tab ──────────────────────────────────────────────────
            with gr.Tab("Query"):
                profile_dd = gr.Dropdown(
                    choices=profiles,
                    value=profiles[0] if profiles else None,
                    label="Profile (knowledge base)",
                    scale=1,
                )
                chatbot = gr.ChatInterface(
                    fn=run_query,
                    additional_inputs=[profile_dd],
                    chatbot=gr.Chatbot(height=500, render_markdown=True),
                    textbox=gr.Textbox(placeholder="Ask a question...", lines=2),
                    submit_btn="Ask",
                    retry_btn=None,
                    undo_btn=None,
                )

            # ── Ingest tab ─────────────────────────────────────────────────
            with gr.Tab("Ingest"):
                with gr.Row():
                    ingest_dd = gr.Dropdown(
                        choices=ingest_configs,
                        value=ingest_configs[0] if ingest_configs else None,
                        label="Ingest config",
                        scale=2,
                    )
                    ingest_btn = gr.Button("Run Ingest", variant="primary", scale=1)

                ingest_out = gr.Textbox(
                    label="Result",
                    interactive=False,
                    lines=3,
                )
                ingest_btn.click(fn=run_ingest, inputs=[ingest_dd], outputs=[ingest_out])

                gr.Markdown("---")

                with gr.Row():
                    status_btn = gr.Button("Refresh Status")
                status_md = gr.Markdown(value=get_status)

                status_btn.click(fn=get_status, inputs=[], outputs=[status_md])

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, show_api=False)


if __name__ == "__main__":
    main()
