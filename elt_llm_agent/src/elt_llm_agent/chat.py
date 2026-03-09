"""Interactive chat CLI for ReAct agent."""

from __future__ import annotations

import argparse
import logging
import sys

from elt_llm_agent import ReActAgent, AgentConfig


def main():
    """Run interactive agent chat."""
    parser = argparse.ArgumentParser(
        description="Interactive Agentic RAG chat",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive chat
  uv run python -m elt_llm_agent.chat

  # With different model
  uv run python -m elt_llm_agent.chat --model qwen3.5:9b

  # Quiet mode (no reasoning trace)
  uv run python -m elt_llm_agent.chat --quiet

Commands in chat:
  /reset     - Reset conversation memory
  /trace     - Show reasoning trace from last query
  /history   - Show conversation history
  /exit      - Exit chat
        """,
    )

    parser.add_argument(
        "--model",
        type=str,
        default="qwen3.5:9b",
        help="LLM model to use (default: qwen3.5:9b)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum reasoning iterations (default: 10)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Hide reasoning trace output",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create agent
    config = AgentConfig(
        model=args.model,
        max_iterations=args.max_iterations,
        verbose=not args.quiet,
    )
    agent = ReActAgent(config)

    print("=" * 60)
    print("Agentic RAG Chat")
    print("=" * 60)
    print(f"Model: {args.model}")
    print(f"Max iterations: {args.max_iterations}")
    print("Type /exit to quit, /reset to clear conversation")
    print("=" * 60)
    print()

    # Interactive loop
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle commands
        if user_input.startswith("/"):
            cmd = user_input.lower()
            if cmd == "/exit":
                print("Goodbye!")
                break
            elif cmd == "/reset":
                agent.reset()
                print("Conversation reset.")
            elif cmd == "/trace":
                trace = agent.export_trace()
                print(trace)
            elif cmd == "/history":
                history = agent.get_history()
                for msg in history:
                    print(f"{msg['role'].upper()}: {msg['content'][:200]}")
            else:
                print(f"Unknown command: {user_input}")
            continue

        # Query agent
        print("Agent: ", end="", flush=True)

        try:
            response = agent.query(user_input, include_trace=not args.quiet)
            print(response.response)

            if not args.quiet and response.reasoning_trace:
                print("\n--- Reasoning Trace ---")
                for step in response.reasoning_trace:
                    print(f"  Step {step['step']}: {step['action']}")
                    print(f"    → {step['result'][:100]}")
                print()

        except Exception as e:
            print(f"Error: {e}")
            logging.exception("Query failed")


if __name__ == "__main__":
    main()
