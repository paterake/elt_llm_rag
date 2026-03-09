"""Agent orchestrator — ReAct agent for multi-step RAG workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from llama_index.core.tools import BaseTool

from elt_llm_agent.memory import ConversationMemory, WorkspaceMemory
from elt_llm_agent.planners import ReActPlanner
from elt_llm_agent.tools import rag_query_tool, json_lookup_tool, graph_traversal_tool

logger = logging.getLogger(__name__)


@dataclass
class AgentConfig:
    """Agent configuration.

    Attributes:
        model: LLM model to use (default: qwen3.5:9b)
        max_iterations: Maximum reasoning loops (default: 10)
        verbose: Enable detailed logging (default: True)
        tools: Custom tools (default: standard RAG tools)
    """

    model: str = "qwen3.5:9b"
    max_iterations: int = 10
    verbose: bool = True
    tools: list[BaseTool] | None = None


@dataclass
class AgentResponse:
    """Agent response with reasoning trace.

    Attributes:
        response: Final answer
        reasoning_trace: List of reasoning steps taken
        tool_calls: List of tool calls made
        sources: Source attributions if available
    """

    response: str
    reasoning_trace: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] | None = None


class ReActAgent:
    """ReAct (Reason + Act) agent for multi-step RAG workflows.

    This agent orchestrates complex queries that require:
    - Multiple tool calls (RAG, JSON lookup, graph traversal)
    - Multi-hop reasoning across data sources
    - Contextual follow-up questions

    Usage:
        >>> agent = ReActAgent()
        >>> response = agent.query(
        ...     "What data objects flow through the Player Registration interface?"
        ... )
        >>> print(response.response)
        >>> print(response.reasoning_trace)
    """

    def __init__(self, config: AgentConfig | None = None):
        """Initialize agent.

        Args:
            config: Agent configuration
        """
        self.config = config or AgentConfig()
        self.conversation_memory = ConversationMemory()
        self.workspace_memory = WorkspaceMemory()
        self.planner = ReActPlanner(
            tools=self._get_tools(),
            max_iterations=self.config.max_iterations,
            verbose=self.config.verbose,
        )

        # Tool executors
        self._tool_executors = {
            "rag_query": rag_query_tool,
            "json_lookup": json_lookup_tool,
            "graph_traversal": graph_traversal_tool,
        }

        logger.info("ReActAgent initialized (model=%s)", self.config.model)

    def _get_tools(self) -> list[BaseTool]:
        """Get available tools.

        Returns:
            List of LlamaIndex BaseTool instances
        """
        if self.config.tools:
            return self.config.tools

        from elt_llm_agent.tools import (
            create_rag_query_tool,
            create_json_lookup_tool,
            create_graph_traversal_tool,
        )

        return [
            create_rag_query_tool(),
            create_json_lookup_tool(),
            create_graph_traversal_tool(),
        ]

    def query(self, query: str, include_trace: bool = True) -> AgentResponse:
        """Execute a query using ReAct reasoning loop.

        Args:
            query: User query
            include_trace: Include reasoning trace in response

        Returns:
            AgentResponse with answer and trace
        """
        logger.info("Agent query: %s", query[:100])

        # Add to conversation memory
        self.conversation_memory.add_message("user", query)

        # Initialize reasoning trace
        reasoning_trace = []
        tool_calls = []

        # Create initial plan
        plan = self.planner.plan(query, {})
        reasoning_trace.append({
            "step": 0,
            "action": "plan",
            "result": f"Created plan with {len(plan['proposed_steps'])} steps",
        })

        # Execute reasoning loop
        iteration = 0
        observations = []
        last_tool = None
        consecutive_same_tool = 0

        while iteration < self.config.max_iterations:
            iteration += 1

            # Determine next action
            action = self.planner.next_action(
                query,
                observations,
                self.workspace_memory.workspace,
            )

            # Check if ready to synthesize
            if action["tool_name"] is None:
                logger.info("Agent: Sufficient information gathered")
                break

            # Detect infinite loop: same tool called 3 times in a row
            if action["tool_name"] == last_tool:
                consecutive_same_tool += 1
                if consecutive_same_tool >= 2:
                    logger.warning("Agent: Detected loop (%d consecutive %s calls) - forcing synthesis", 
                                   consecutive_same_tool, action["tool_name"])
                    break
            else:
                consecutive_same_tool = 0
                last_tool = action["tool_name"]

            # Execute tool call
            tool_name = action["tool_name"]
            tool_params = action["tool_input"]

            reasoning_trace.append({
                "step": iteration,
                "action": "reasoning",
                "result": action["reasoning"],
            })

            try:
                executor = self._tool_executors.get(tool_name)
                if not executor:
                    logger.warning("Unknown tool: %s", tool_name)
                    continue

                # Execute tool
                result = executor(**tool_params)

                tool_calls.append({
                    "step": iteration,
                    "tool": tool_name,
                    "params": tool_params,
                    "result_length": len(result) if isinstance(result, str) else 0,
                })

                # Check if tool returned an error or no data
                if "Error:" in result or "No JSON sidecars found" in result or "not found" in result.lower():
                    logger.warning("Tool returned error/no data: %s", tool_name)
                    observations.append({
                        "tool": tool_name,
                        "observation": result[:300],
                        "status": "error",
                    })
                    # Don't retry failed tools - move to next
                    continue

                observations.append({
                    "tool": tool_name,
                    "observation": result[:500] if isinstance(result, str) else result,
                    "status": "success",
                })

                self.workspace_memory.set(f"last_{tool_name}_result", result)

                reasoning_trace.append({
                    "step": iteration,
                    "action": f"tool_call:{tool_name}",
                    "result": f"Got result ({len(result) if isinstance(result, str) else 0} chars)",
                })

                if self.config.verbose:
                    logger.info("Tool %s executed successfully", tool_name)

            except Exception as e:
                logger.exception("Tool call failed: %s", tool_name)
                observations.append({
                    "tool": tool_name,
                    "observation": f"Error: {e}",
                    "status": "error",
                })

        # Synthesize final answer
        response = self._synthesize(query, observations)

        # Add to conversation memory
        self.conversation_memory.add_message("assistant", response)

        return AgentResponse(
            response=response,
            reasoning_trace=reasoning_trace if include_trace else [],
            tool_calls=tool_calls,
        )

    def _synthesize(self, query: str, observations: list[dict[str, Any]]) -> str:
        """Synthesize final answer from observations.

        Args:
            query: Original query
            observations: Tool call results

        Returns:
            Synthesized answer
        """
        # Simple synthesis: combine observations
        # In production, this would call the LLM with a synthesis prompt

        if not observations:
            return "I was unable to gather sufficient information to answer your query."

        # Combine tool results
        parts = []
        for obs in observations:
            tool = obs.get("tool")
            result = obs.get("observation", "")

            if isinstance(result, str):
                # Truncate long results
                if len(result) > 1000:
                    result = result[:1000] + "... (truncated)"
                parts.append(f"[{tool.upper()}]\n{result}")

        # Add synthesis header
        synthesis = [
            f"Based on my analysis of your query: \"{query}\"\n",
            "I gathered information from multiple sources:",
            "",
            "\n\n".join(parts),
            "",
            "---",
            "Note: This is a simplified synthesis. Enable LLM-based synthesis for better answers.",
        ]

        return "\n".join(synthesis)

    def chat(self, message: str) -> str:
        """Chat with the agent (maintains conversation context).

        Args:
            message: User message

        Returns:
            Agent response text
        """
        response = self.query(message, include_trace=False)
        return response.response

    def reset(self) -> None:
        """Reset agent memory (start fresh conversation)."""
        self.conversation_memory.clear()
        self.workspace_memory.clear()
        logger.info("Agent memory reset")

    def get_history(self) -> list[dict[str, Any]]:
        """Get conversation history.

        Returns:
            List of message dicts
        """
        return self.conversation_memory.get_history()

    def export_trace(self) -> str:
        """Export reasoning trace for debugging.

        Returns:
            Formatted trace string
        """
        return self.workspace_memory.export_traces()
