"""Tool call types shared by agent orchestration code."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentAction:
    """Normalized action emitted by an agent decision."""

    name: str
    params: dict[str, Any] = field(default_factory=dict)
    category: str = "game"
    raw: dict[str, Any] | None = None


@dataclass
class ToolResult:
    """Unified result for internal tools, MCP queries, and side effects."""

    name: str
    ok: bool
    data: Any = None
    error: str = ""
    side_effect: bool = False
