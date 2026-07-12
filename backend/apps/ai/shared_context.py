"""Legacy Host conversation window.

Cross-runtime awareness now lives in ``apps.agent.mutual_context.MutualContext``;
long-term and game memory live in MemoryEngine. This module retains only the
recent viewer/host exchanges required by Host prompt assembly.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import asdict, dataclass

from apps.config import config


@dataclass(frozen=True, slots=True)
class HostHistoryEntry:
    danmaku: str
    reply: str
    user: str = ""
    timestamp: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class SharedContext:
    """Deprecated name for the Host-only recent conversation FIFO."""

    def __init__(
        self,
        host_history_maxlen: int | None = None,
        game_history_maxlen: int | None = None,
    ) -> None:
        del game_history_maxlen
        maxlen = host_history_maxlen or config.agent_host_history_maxlen
        self._host_history: deque[HostHistoryEntry] = deque(maxlen=maxlen)
        self._lock = asyncio.Lock()

    async def add_host_entry(self, danmaku: str, reply: str, user: str = "") -> None:
        async with self._lock:
            self._host_history.append(
                HostHistoryEntry(
                    danmaku=danmaku,
                    reply=reply,
                    user=user,
                    timestamp=time.time(),
                )
            )

    async def get_host_history(self, limit: int = 20) -> list[HostHistoryEntry]:
        async with self._lock:
            return list(self._host_history)[-limit:]

    async def get_host_history_text(self, limit: int = 20) -> str:
        entries = await self.get_host_history(limit)
        if not entries:
            return "（暂无互动）"
        return "\n".join(
            f"{item.user or '观众'}: {item.danmaku} | 主播: {item.reply}" for item in entries
        )

    async def trim_histories(self, keep_seconds: float = 300) -> None:
        now = time.time()
        async with self._lock:
            while self._host_history and now - self._host_history[0].timestamp > keep_seconds:
                self._host_history.popleft()

    async def get_context_summary(self) -> dict:
        return {
            "host_history": [item.to_dict() for item in await self.get_host_history(limit=10)]
        }


_shared_context: SharedContext | None = None


def get_shared_context() -> SharedContext:
    global _shared_context
    if _shared_context is None:
        _shared_context = SharedContext()
    return _shared_context
