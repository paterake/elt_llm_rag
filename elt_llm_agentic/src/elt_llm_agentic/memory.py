"""Conversation and workspace memory for interactive chat sessions."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConversationMemory:
    """Short-term conversation history with FIFO eviction.

    Stores user queries + assistant responses to enable contextual
    follow-up questions across multi-turn sessions.
    """

    messages: list[dict[str, Any]] = field(default_factory=list)
    max_messages: int = 50

    def add_message(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        while len(self.messages) > self.max_messages:
            self.messages.pop(0)

    def get_history(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m.get("role") != "system"]

    def get_recent(self, n: int = 5) -> list[dict[str, Any]]:
        return self.messages[-n:]

    def to_context_string(self) -> str:
        return "\n\n".join(
            f"{m['role'].upper()}: {m['content']}" for m in self.messages
        )

    def clear(self) -> None:
        self.messages.clear()


@dataclass
class WorkspaceMemory:
    """Key-value scratchpad + reasoning trace for debugging agent steps."""

    workspace: dict[str, Any] = field(default_factory=dict)
    traces: list[dict[str, Any]] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.workspace[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.workspace.get(key, default)

    def add_trace(self, step: str, action: str, result: str) -> None:
        self.traces.append({"step": step, "action": action, "result": result})

    def get_traces(self) -> list[dict[str, Any]]:
        return self.traces.copy()

    def export_traces(self) -> str:
        lines = ["--- Reasoning Trace ---"]
        for t in self.traces:
            lines.append(f"Step {t['step']}: {t['action']}")
            lines.append(f"  {t['result'][:200]}")
        return "\n".join(lines)

    def clear(self) -> None:
        self.workspace.clear()
        self.traces.clear()
