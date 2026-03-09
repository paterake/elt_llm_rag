"""Agent memory — conversation history and working workspace."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationMemory:
    """Short-term conversation memory for agent interactions.

    Stores the conversation history (user queries + agent responses)
    to enable contextual follow-up questions.

    Attributes:
        messages: List of conversation turns
        max_messages: Maximum messages to retain (FIFO eviction)
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    max_messages: int = 50

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to conversation history.

        Args:
            role: Message role ("user", "assistant", "system")
            content: Message content
            **kwargs: Additional metadata (e.g., tool_calls, sources)
        """
        message = {
            "role": role,
            "content": content,
            **kwargs,
        }
        self.messages.append(message)

        # Evict old messages if over limit
        while len(self.messages) > self.max_messages:
            self.messages.pop(0)

        logger.debug("Added %s message to conversation memory", role)

    def get_history(self, include_system: bool = False) -> list[dict[str, Any]]:
        """Get conversation history.

        Args:
            include_system: Whether to include system messages

        Returns:
            List of message dicts
        """
        if include_system:
            return self.messages.copy()
        return [m for m in self.messages if m.get("role") != "system"]

    def get_recent(self, n: int = 5) -> list[dict[str, Any]]:
        """Get most recent N messages.

        Args:
            n: Number of messages to return

        Returns:
            List of recent messages
        """
        return self.messages[-n:]

    def clear(self) -> None:
        """Clear conversation history."""
        self.messages.clear()
        logger.debug("Conversation memory cleared")

    def to_context_string(self) -> str:
        """Convert conversation history to context string for LLM.

        Returns:
            Formatted conversation history
        """
        lines = []
        for msg in self.messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role.upper()}: {content}")
        return "\n\n".join(lines)


@dataclass
class WorkspaceMemory:
    """Long-term working memory for agent reasoning and scratchpad.

    Stores intermediate results, extracted entities, and reasoning
    traces across multi-step agent workflows.

    Attributes:
        workspace: Key-value store for working memory
        traces: List of reasoning traces for debugging
    """

    workspace: dict[str, Any] = field(default_factory=dict)
    traces: list[dict[str, Any]] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        """Store a value in working memory.

        Args:
            key: Storage key
            value: Value to store (must be JSON-serializable)
        """
        self.workspace[key] = value
        logger.debug("Workspace: set %s", key)

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from working memory.

        Args:
            key: Storage key
            default: Default value if key not found

        Returns:
            Stored value or default
        """
        return self.workspace.get(key, default)

    def delete(self, key: str) -> bool:
        """Delete a value from working memory.

        Args:
            key: Storage key

        Returns:
            True if key existed and was deleted
        """
        if key in self.workspace:
            del self.workspace[key]
            logger.debug("Workspace: deleted %s", key)
            return True
        return False

    def add_trace(self, step: str, action: str, result: str, metadata: dict[str, Any] | None = None) -> None:
        """Add a reasoning trace for debugging and audit.

        Args:
            step: Step number in agent reasoning
            action: Action taken (e.g., "tool_call", "reasoning", "synthesis")
            result: Result of the action
            metadata: Optional additional metadata
        """
        trace = {
            "step": step,
            "action": action,
            "result": result,
            "metadata": metadata or {},
        }
        self.traces.append(trace)
        logger.debug("Trace: step=%d, action=%s", step, action)

    def get_traces(self) -> list[dict[str, Any]]:
        """Get all reasoning traces.

        Returns:
            List of trace dicts
        """
        return self.traces.copy()

    def clear(self) -> None:
        """Clear working memory and traces."""
        self.workspace.clear()
        self.traces.clear()
        logger.debug("Workspace memory cleared")

    def export_traces(self) -> str:
        """Export traces as formatted string for debugging.

        Returns:
            Formatted trace output
        """
        lines = ["--- Agent Reasoning Trace ---"]
        for trace in self.traces:
            lines.append(f"Step {trace['step']}: {trace['action']}")
            lines.append(f"  Result: {trace['result'][:200]}...")
        return "\n".join(lines)
