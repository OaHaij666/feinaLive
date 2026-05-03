"""MCP 客户端 - 与 MCP 兼容游戏通信"""

import asyncio
import json
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._tools_cache: list[dict] | None = None
        self._tools_cache_time: float = 0.0
        self._request_id: int = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def call(self, method: str, params: dict | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._next_id(),
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/mcp",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    logger.error(f"MCP错误: {data['error']}")
                    return None
                return data.get("result")
        except httpx.HTTPStatusError as e:
            logger.error(f"MCP HTTP错误 {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            logger.error(f"MCP调用失败 [{method}]: {e}")
            return None

    async def get_tools(self, force_refresh: bool = False) -> list[dict]:
        now = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        if not force_refresh and self._tools_cache and (now - self._tools_cache_time) < 60:
            return self._tools_cache

        result = await self.call("tools/list")
        if result and "tools" in result:
            self._tools_cache = result["tools"]
            self._tools_cache_time = now
            return self._tools_cache
        return []

    async def call_tool(self, tool_name: str, arguments: dict | None = None) -> Any:
        params = {"name": tool_name}
        if arguments:
            params["arguments"] = arguments
        result = await self.call("tools/call", params)
        if result:
            logger.info(f"MCP工具执行成功: {tool_name}")
        return result

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
                return resp.status_code == 200
        except Exception:
            return False
