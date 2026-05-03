"""MCP 模块 - Model Context Protocol 游戏集成"""

from apps.ai.mcp.base_adapter import BaseGameAdapter, UnifiedAction, UnifiedGameState
from apps.ai.mcp.client import MCPClient

__all__ = ["BaseGameAdapter", "UnifiedAction", "UnifiedGameState", "MCPClient"]
