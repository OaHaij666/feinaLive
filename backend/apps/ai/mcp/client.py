"""MCP 客户端 - 与 MCP 兼容游戏通信"""

import asyncio
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 1.0
DEFAULT_TOOLS_CACHE_TTL = 120.0


class MCPClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_delay: float = DEFAULT_RETRY_DELAY,
        tools_cache_ttl: float = DEFAULT_TOOLS_CACHE_TTL,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._retry_delay = retry_delay
        self._tools_cache_ttl = tools_cache_ttl
        self._tools_cache: list[dict] | None = None
        self._tools_cache_time: float = 0.0
        self._request_id: int = 0
        # 复用连接池，避免每次调用创建新 client
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

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

        for attempt in range(self._max_retries):
            try:
                client = await self._get_client()
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
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < self._max_retries - 1:
                    wait = self._retry_delay * (2 ** attempt)
                    logger.warning(
                        f"MCP网络错误 (重试 {attempt + 1}/{self._max_retries}): {e}，{wait:.1f}s后重试"
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error(f"MCP调用失败 [{method}]，已重试{self._max_retries}次: {e}")
            except httpx.HTTPStatusError as e:
                # HTTP 状态码错误不重试（4xx 不会因重试而恢复）
                logger.error(f"MCP HTTP错误 {e.response.status_code}: {e.response.text}")
                return None
            except Exception as e:
                logger.error(f"MCP调用失败 [{method}]: {e}")
                return None

        return None

    async def get_tools(self, force_refresh: bool = False) -> list[dict]:
        now = time.monotonic()
        if not force_refresh and self._tools_cache and (now - self._tools_cache_time) < self._tools_cache_ttl:
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
            client = await self._get_client()
            resp = await client.get(f"{self._base_url}/health", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
