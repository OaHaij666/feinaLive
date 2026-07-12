from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class MutualContextEntry:
    actor: str
    kind: str
    summary: str
    metadata: dict[str, Any]
    created_at: float


class MutualContext:
    """Small, ephemeral window that lets HostRuntime and AgentRuntime see each other."""

    def __init__(self, maxlen: int = 16, ttl_seconds: float = 600.0) -> None:
        self._entries: deque[MutualContextEntry] = deque(maxlen=maxlen)
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def record(
        self,
        actor: str,
        kind: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        text = summary.strip()
        if not text:
            return
        async with self._lock:
            self._prune_locked(time.time())
            self._entries.append(
                MutualContextEntry(actor, kind, text[:800], dict(metadata or {}), time.time())
            )

    async def recent(self, limit: int = 12) -> list[MutualContextEntry]:
        async with self._lock:
            self._prune_locked(time.time())
            return list(self._entries)[-limit:]

    async def to_prompt_text(self, limit: int = 12, max_chars: int = 4000) -> str:
        entries = await self.recent(limit)
        if not entries:
            return "（暂无近期共享动态）"
        text = "\n".join(f"- {item.actor}/{item.kind}: {item.summary}" for item in entries)
        return text[-max_chars:]

    async def snapshot(self) -> list[dict[str, Any]]:
        return [asdict(item) for item in await self.recent(100)]

    def _prune_locked(self, now: float) -> None:
        while self._entries and now - self._entries[0].created_at > self._ttl_seconds:
            self._entries.popleft()


_mutual_context: MutualContext | None = None


def get_mutual_context() -> MutualContext:
    global _mutual_context
    if _mutual_context is None:
        _mutual_context = MutualContext()
    return _mutual_context
