"""Batch query runner for agentic RAG workflows."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from elt_llm_agent import ReActAgent, AgentConfig


def main():
    """Run batch agentic queries."""
    parser = argparse.ArgumentParser(
        description="Agentic RAG batch query runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single query
  uv run python -m elt_llm_agent.query -q "What data objects flow through Player Registration?"

  # Batch queries from file
  uv run python -m elt_llm_agent.query --file queries.json

  # With output file
  uv run python -m elt_llm_agent.query -q "..." --output results.json

  # Show full reasoning trace
  uv run python -m elt_llm_agent.query -q "..." -v
        """,
    )

    parser.add_argument(
        "-q", "--query",
        type=str,
        help="Single query to execute",
    )
    parser.add_argument(
        "--file",
        type=str,
        help="JSON file with list of queries",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output JSON file for results",
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
        "-v", "--verbose",
        action="store_true",
        help="Show detailed reasoning trace",
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

    # Validate input
    if not args.query and not args.file:
        parser.error("Must provide either -q/--query or --file")

    # Load queries
    queries = []
    if args.query:
        queries = [{"query": args.query}]
    elif args.file:
        with open(args.file, "r") as f:
            data = json.load(f)
            if isinstance(data, list):
                queries = data
            elif isinstance(data, dict) and "queries" in data:
                queries = data["queries"]
            else:
                queries = [{"query": str(data)}]

    # Create agent
    config = AgentConfig(
        model=args.model,
        max_iterations=args.max_iterations,
        verbose=args.verbose,
    )
    agent = ReActAgent(config)

    # Execute queries
    results = []

    for i, item in enumerate(queries):
        query_text = item.get("query") if isinstance(item, dict) else str(item)

        logging.info("Query %d/%d: %s", i + 1, len(queries), query_text[:100])

        try:
            response = agent.query(query_text, include_trace=args.verbose)

            result = {
                "query": query_text,
                "response": response.response,
                "tool_calls": response.tool_calls,
            }

            if args.verbose:
                result["reasoning_trace"] = response.reasoning_trace

            results.append(result)

            # Print progress
            print(f"\n--- Query {i + 1}/{len(queries)} ---")
            print(f"Query: {query_text}")
            print(f"Response: {response.response[:500]}...")

            if args.verbose and response.tool_calls:
                print(f"Tool calls: {len(response.tool_calls)}")
                for tc in response.tool_calls:
                    print(f"  - {tc['tool']} (step {tc['step']})")

        except Exception as e:
            logging.exception("Query failed")
            results.append({
                "query": query_text,
                "error": str(e),
            })

    # Write output
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)
        logging.info("Results written to %s", args.output)

    # Summary
    print(f"\n=== Summary ===")
    print(f"Total queries: {len(results)}")
    print(f"Successful: {sum(1 for r in results if 'error' not in r)}")
    print(f"Failed: {sum(1 for r in results if 'error' in r)}")


# Alias for command-line usage: uv run python -m elt_llm_agent.query
query = main

if __name__ == "__main__":
    main()
