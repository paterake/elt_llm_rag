"""Interactive conversational chat using the FA Handbook RAG system.

Uses elt_llm_query.query_collections directly with conversation memory
so follow-up questions have context from previous turns.

Commands:
  /reset    — clear conversation history
  /history  — show recent conversation
  /graph <entity> [operation]  — graph traversal (e.g. /graph Club neighbors)
  /exit     — quit

Usage:
    uv run --package elt-llm-agentic elt-llm-agentic-chat
    uv run --package elt-llm-agentic elt-llm-agentic-chat --profile fa_handbook_only
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from elt_llm_agentic.memory import ConversationMemory

_REPO_ROOT = Path(__file__).parent.parent.parent.parent  # elt_llm_rag/
_DEFAULT_RAG_CONFIG = _REPO_ROOT / "elt_llm_ingest/config/rag_config.yaml"


def _get_collections(profile: str, rag_config: object) -> list[str]:
    """Resolve collection names for a named profile."""
    from elt_llm_query.query import resolve_collections
    try:
        return resolve_collections(profile, rag_config)
    except Exception:
        # Fallback: all fa_handbook_sNN collections
        from elt_llm_core.vector_store import get_chroma_client
        client = get_chroma_client(rag_config)
        return sorted(
            c.name for c in client.list_collections()
            if c.name.startswith("fa_handbook")
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive FA Handbook chat with conversation memory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Commands during chat:\n"
            "  /reset                      — clear conversation history\n"
            "  /history                    — show recent turns\n"
            "  /graph <entity> [operation] — traverse entity relationships\n"
            "  /exit                       — quit\n\n"
            "Examples:\n"
            "  uv run --package elt-llm-agentic elt-llm-agentic-chat\n"
            "  uv run --package elt-llm-agentic elt-llm-agentic-chat --profile fa_enterprise_architecture"
        ),
    )
    parser.add_argument(
        "--profile", default="fa_handbook_only",
        help="Query profile (default: fa_handbook_only). See elt_llm_query README for options.",
    )
    parser.add_argument(
        "--config", type=Path, default=_DEFAULT_RAG_CONFIG,
        help="Path to rag_config.yaml",
    )
    parser.add_argument("--quiet", action="store_true", help="Hide source citations")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    for lib in ("httpx", "httpcore", "chromadb", "llama_index", "bm25s"):
        logging.getLogger(lib).setLevel(logging.WARNING)

    from elt_llm_core.config import load_config
    from elt_llm_query.query import query_collections

    rag_config = load_config(args.config)
    collections = _get_collections(args.profile, rag_config)

    memory = ConversationMemory()

    print("=" * 60)
    print("FA Handbook Chat")
    print("=" * 60)
    print(f"Profile: {args.profile}  |  Collections: {len(collections)}")
    print("Type /exit to quit, /reset to clear history")
    print("=" * 60)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # --- Commands ---
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd in ("/exit", "/quit"):
                print("Goodbye!")
                break
            elif cmd == "/reset":
                memory.clear()
                print("Conversation cleared.")
            elif cmd == "/history":
                for m in memory.get_recent(6):
                    print(f"{m['role'].upper()}: {m['content'][:200]}")
            elif cmd.startswith("/graph"):
                parts = user_input.split()
                if len(parts) < 2:
                    print("Usage: /graph <entity> [operation]  e.g. /graph Club neighbors")
                else:
                    entity = parts[1]
                    op = parts[2] if len(parts) > 2 else "neighbors"
                    try:
                        from elt_llm_agentic.graph_traversal import graph_traversal
                        print(graph_traversal(entity, operation=op))
                    except Exception as e:
                        print(f"Graph traversal error: {e}")
            else:
                print(f"Unknown command: {user_input}")
            continue

        # --- RAG query with conversation context ---
        memory.add_message("user", user_input)

        # Prepend recent history so follow-up questions have context
        recent = memory.get_recent(4)
        history_ctx = ""
        if len(recent) > 1:
            history_ctx = (
                "\n\nConversation so far:\n"
                + "\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent[:-1])
                + "\n\nNow answer the latest question below.\n"
            )

        query = history_ctx + user_input

        print("Agent: ", end="", flush=True)
        try:
            result = query_collections(collections, query, rag_config, iterative=False)
            answer = result.response.strip()
            print(answer)
            memory.add_message("assistant", answer)
        except Exception as e:
            print(f"Error: {e}")
            logging.exception("Query failed")

        print()


if __name__ == "__main__":
    main()
