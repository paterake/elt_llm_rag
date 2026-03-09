"""Agent planners — ReAct and Plan-and-Execute patterns."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from llama_index.core.tools import BaseTool

logger = logging.getLogger(__name__)


@dataclass
class ReActPlanner:
    """ReAct (Reason + Act) planner for agentic workflows.

    Implements the ReAct pattern:
    1. Reason: Analyze the query and determine what information is needed
    2. Act: Call appropriate tools to gather information
    3. Observe: Process tool outputs
    4. Repeat: Continue until sufficient information gathered
    5. Synthesize: Generate final answer

    Attributes:
        tools: Available tools for the agent
        max_iterations: Maximum reasoning loops before forcing synthesis
        verbose: Enable detailed logging
    """

    tools: list[BaseTool] = field(default_factory=list)
    max_iterations: int = 10
    verbose: bool = True

    def plan(self, query: str, context: dict[str, Any]) -> dict[str, Any]:
        """Create initial plan for answering the query.

        Args:
            query: User query
            context: Current context (conversation history, workspace)

        Returns:
            Plan dict with reasoning and proposed actions
        """
        # Analyze query complexity
        query_lower = query.lower()

        # Determine required tools based on query patterns
        required_tools = []

        if any(word in query_lower for word in ["governance", "rule", "policy", "handbook"]):
            required_tools.append("rag_query")

        if any(word in query_lower for word in ["entity", "data object", "interface", "application", "inventory"]):
            required_tools.append("json_lookup")

        if any(word in query_lower for word in ["relationship", "connected", "flow", "traverse"]):
            required_tools.append("graph_traversal")

        # Default to all tools if unclear
        if not required_tools:
            required_tools = ["rag_query", "json_lookup", "graph_traversal"]

        plan = {
            "query_analysis": query,
            "required_tools": required_tools,
            "proposed_steps": self._generate_steps(query, required_tools),
            "confidence": "high" if len(required_tools) <= 2 else "medium",
        }

        logger.info("ReAct plan created: %d steps", len(plan["proposed_steps"]))
        return plan

    def _generate_steps(self, query: str, tools: list[str]) -> list[dict[str, str]]:
        """Generate proposed reasoning steps.

        Args:
            query: User query
            tools: Tools to use

        Returns:
            List of step dicts with tool and description
        """
        steps = []

        # Heuristic step generation based on query patterns
        if "relationship" in query.lower() or "connected" in query.lower():
            # Multi-hop query pattern
            steps.append({"tool": "json_lookup", "action": "Identify primary entities"})
            steps.append({"tool": "graph_traversal", "action": "Find relationships"})
            steps.append({"tool": "rag_query", "action": "Get governance context"})
        elif "governance" in query.lower() or "rule" in query.lower():
            # Governance query pattern
            steps.append({"tool": "rag_query", "action": "Query FA Handbook"})
            steps.append({"tool": "json_lookup", "action": "Verify entity exists in model"})
        else:
            # General query pattern
            for tool in tools:
                steps.append({"tool": tool, "action": f"Query using {tool}"})

        return steps

    def next_action(
        self,
        query: str,
        history: list[dict[str, Any]],
        workspace: dict[str, Any],
    ) -> dict[str, Any]:
        """Determine next action based on query and history.

        Args:
            query: Original user query
            history: Previous tool calls and observations
            workspace: Current working memory

        Returns:
            Action dict with tool_name, tool_input, and reasoning
        """
        # Check if any tool calls resulted in errors
        has_errors = any(h.get("status") == "error" for h in history)
        has_json_error = any(
            h.get("tool") == "json_lookup" and h.get("status") == "error"
            for h in history
        )
        
        # Check what information we have
        has_entity_data = any(
            h.get("tool") == "json_lookup" and h.get("status") == "success"
            for h in history
        )
        has_rag_data = any(
            h.get("tool") == "rag_query" and h.get("status") == "success"
            for h in history
        )
        has_relationships = any("relationship" in str(h.get("observation", "")).lower() for h in history)

        # If JSON lookup failed, switch to RAG-only strategy
        if has_json_error and not has_rag_data:
            return {
                "tool_name": "rag_query",
                "tool_input": {"collection": "fa_handbook", "query": query},
                "reasoning": "JSON lookup unavailable - using RAG to query FA Handbook directly",
            }

        # First call - start with RAG (more reliable than JSON lookup which may not exist)
        if not history:
            return {
                "tool_name": "rag_query",
                "tool_input": {"collection": "fa_handbook", "query": query},
                "reasoning": "Starting with FA Handbook RAG query",
            }

        # If we have RAG data but no entity context, try JSON lookup
        if has_rag_data and not has_entity_data and not has_json_error:
            return {
                "tool_name": "json_lookup",
                "tool_input": {"entity_type": "model"},
                "reasoning": "Need entity data from conceptual model",
            }

        # Check if query is about relationships
        if "relationship" in query.lower() or "connected" in query.lower() or "flow" in query.lower():
            if not has_relationships and not has_json_error:
                return {
                    "tool_name": "graph_traversal",
                    "tool_input": {"entity_name": "extracted_entity", "max_depth": 2},
                    "reasoning": "Need relationship information from graph traversal",
                }

        # If we have RAG data, synthesize
        if has_rag_data:
            return {
                "tool_name": None,
                "tool_input": {},
                "reasoning": "Sufficient information gathered - ready to synthesize final answer",
            }

        # Default: try RAG query
        if not has_rag_data:
            return {
                "tool_name": "rag_query",
                "tool_input": {"collection": "fa_handbook", "query": query},
                "reasoning": "Querying FA Handbook for context",
            }

        # All information gathered - ready to synthesize
        return {
            "tool_name": None,
            "tool_input": {},
            "reasoning": "Sufficient information gathered - ready to synthesize final answer",
        }


@dataclass
class PlanExecutePlanner:
    """Plan-and-Execute planner for complex multi-step workflows.

    Separates planning from execution:
    1. Generate complete plan upfront
    2. Execute each step sequentially
    3. Synthesize final answer

    Better for batch workflows where all steps are known upfront.
    """

    tools: list[BaseTool] = field(default_factory=list)
    max_steps: int = 20

    def create_plan(self, query: str) -> list[dict[str, Any]]:
        """Create complete execution plan.

        Args:
            query: User query

        Returns:
            List of step dicts with tool calls and parameters
        """
        # For complex queries, generate multi-step plan
        plan = []

        # Step 1: Always start with entity identification
        plan.append({
            "step": 1,
            "tool": "json_lookup",
            "params": {"entity_type": "model"},
            "description": "Identify entities in conceptual model",
        })

        # Step 2: Add relationship traversal if needed
        if any(word in query.lower() for word in ["relationship", "connected", "flow", "between"]):
            plan.append({
                "step": 2,
                "tool": "graph_traversal",
                "params": {"max_depth": 2},
                "description": "Traverse entity relationships",
            })

        # Step 3: Add RAG query for governance/context
        plan.append({
            "step": len(plan) + 1,
            "tool": "rag_query",
            "params": {"collection": "fa_handbook"},
            "description": "Query FA Handbook for governance and context",
        })

        return plan

    def execute_step(
        self,
        step: dict[str, Any],
        tool_executors: dict[str, Callable],
        previous_results: list[Any],
    ) -> Any:
        """Execute a single plan step.

        Args:
            step: Step dict with tool and params
            tool_executors: Map of tool names to callables
            previous_results: Results from previous steps

        Returns:
            Step execution result
        """
        tool_name = step.get("tool")
        params = step.get("params", {})

        # Inject previous results if needed
        if previous_results:
            params["previous_results"] = previous_results

        executor = tool_executors.get(tool_name)
        if not executor:
            logger.warning("Unknown tool: %s", tool_name)
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            result = executor(**params)
            logger.info("Step %d executed: %s", step["step"], tool_name)
            return result
        except Exception as e:
            logger.exception("Step %d failed: %s", step["step"], tool_name)
            return {"error": str(e)}
