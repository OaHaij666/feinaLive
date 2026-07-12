"""MCP 模块 - Model Context Protocol 游戏集成"""

from apps.ai.mcp.adapter import MCPGameAdapter
from apps.ai.mcp.client import MCPClient
from apps.ai.mcp.games.base import UnifiedAction, UnifiedGameState

__all__ = ["MCPClient", "MCPGameAdapter", "UnifiedAction", "UnifiedGameState"]
