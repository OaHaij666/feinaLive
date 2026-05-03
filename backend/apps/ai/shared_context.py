"""共享存储层 - 游戏 Graph 与主播 Graph 之间的共享状态

包含:
- 主播回答历史 (FIFO): 主播LLM读写，游戏LLM只读
- 游戏LLM历史 (FIFO): 游戏LLM读写
- 总记忆 (异步总结): 专用LLM定时更新
"""

import asyncio
import logging
import re
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class HostHistoryEntry:
    danmaku: str
    reply: str
    user: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "danmaku": self.danmaku,
            "reply": self.reply,
            "user": self.user,
            "timestamp": self.timestamp,
        }


@dataclass
class GameHistoryEntry:
    action: str
    params: dict
    result: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "params": self.params,
            "result": self.result,
            "timestamp": self.timestamp,
        }


@dataclass
class LongTermMemory:
    core: str = ""
    important: str = ""
    recent: str = ""
    key_events: list[str] = field(default_factory=list)
    last_updated: float = 0.0

    def to_dict(self) -> dict:
        return {
            "core": self.core,
            "important": self.important,
            "recent": self.recent,
            "key_events": self.key_events,
            "last_updated": self.last_updated,
        }


class SharedContext:
    def __init__(
        self,
        host_history_maxlen: int = 50,
        game_history_maxlen: int = 30,
    ):
        self._host_history: deque[HostHistoryEntry] = deque(maxlen=host_history_maxlen)
        self._game_history: deque[GameHistoryEntry] = deque(maxlen=game_history_maxlen)
        self._memory = LongTermMemory()
        self._lock = asyncio.Lock()

    async def add_host_entry(self, danmaku: str, reply: str, user: str = ""):
        async with self._lock:
            self._host_history.append(HostHistoryEntry(danmaku=danmaku, reply=reply, user=user))
            logger.debug(f"主播历史更新: [{user or '观众'}] {danmaku[:20]} -> [{reply[:20]}]")

    async def add_game_entry(self, action: str, params: dict, result: str = ""):
        async with self._lock:
            self._game_history.append(GameHistoryEntry(action=action, params=params, result=result))
            logger.debug(f"游戏历史更新: {action}({params})")

    async def get_host_history(self, limit: int = 20) -> list[HostHistoryEntry]:
        async with self._lock:
            entries = list(self._host_history)
            return entries[-limit:]

    async def get_host_history_text(self, limit: int = 20) -> str:
        entries = await self.get_host_history(limit)
        if not entries:
            return "（暂无互动）"
        lines = []
        for e in entries:
            user_label = e.user or "观众"
            lines.append(f"{user_label}: {e.danmaku} | 主播: {e.reply}")
        return "\n".join(lines)

    async def get_game_history(self, limit: int = 15) -> list[GameHistoryEntry]:
        async with self._lock:
            entries = list(self._game_history)
            return entries[-limit:]

    async def get_game_history_text(self, limit: int = 15) -> str:
        entries = await self.get_game_history(limit)
        if not entries:
            return "（暂无操作）"
        lines = []
        for e in entries:
            lines.append(f"{e.action}({e.params}) -> {e.result}")
        return "\n".join(lines)

    async def get_memory(self) -> LongTermMemory:
        async with self._lock:
            return LongTermMemory(
                core=self._memory.core,
                important=self._memory.important,
                recent=self._memory.recent,
                key_events=list(self._memory.key_events),
                last_updated=self._memory.last_updated,
            )

    async def update_memory(self, core: str | None = None, important: str | None = None, recent: str | None = None, key_events: list[str] | None = None):
        async with self._lock:
            if core is not None:
                self._memory.core = core
            if important is not None:
                self._memory.important = important
            if recent is not None:
                self._memory.recent = recent
            if key_events is not None:
                self._memory.key_events = key_events
            self._memory.last_updated = time.time()
            logger.info(f"记忆更新: core={len(self._memory.core)} chars, important={len(self._memory.important)} chars, recent={len(self._memory.recent)} chars")

    async def clear_all_memory(self):
        async with self._lock:
            self._memory.core = ""
            self._memory.important = ""
            self._memory.recent = ""
            self._memory.key_events = []
            self._memory.last_updated = time.time()
        logger.info("记忆已清空（新游戏开始）")

    async def search_replace_memory(
        self,
        memory_type: str,
        mode: str,
        search: str,
        replace: str,
        end: str = "",
    ):
        async with self._lock:
            content = self._get_memory_content(memory_type)
            if content is None:
                raise ValueError(f"Unknown memory type: {memory_type}")

            new_content = self._do_search_replace(
                content=content,
                mode=mode,
                search=search,
                replace=replace,
                end=end,
            )

            self._set_memory_content(memory_type, new_content)
            logger.info(f"记忆搜索替换: {memory_type}, mode={mode}")

    def _get_memory_content(self, memory_type: str) -> str | None:
        if memory_type == "core":
            return self._memory.core
        elif memory_type == "important":
            return self._memory.important
        elif memory_type == "recent":
            return self._memory.recent
        return None

    def _set_memory_content(self, memory_type: str, content: str):
        if memory_type == "core":
            self._memory.core = content
        elif memory_type == "important":
            self._memory.important = content
        elif memory_type == "recent":
            self._memory.recent = content

    def _do_search_replace(
        self,
        content: str,
        mode: str,
        search: str,
        replace: str,
        end: str,
    ) -> str:
        if mode == "exact":
            return content.replace(search, replace)

        elif mode == "fuzzy":
            pattern = re.escape(search)
            pattern = re.sub(r"\s+", r"\\s+", pattern)
            return re.sub(pattern, replace, content, flags=re.IGNORECASE)

        elif mode == "range":
            if not end:
                raise ValueError("range mode requires 'end' parameter")
            start_idx = content.find(search)
            end_idx = content.find(end, start_idx + len(search) if start_idx != -1 else 0)
            if start_idx == -1 or end_idx == -1:
                return content
            return content[:start_idx] + replace + content[end_idx + len(end):]

        else:
            raise ValueError(f"Unknown mode: {mode}")

    async def rewrite_memory(self, memory_type: str, content: str):
        async with self._lock:
            if memory_type == "core":
                self._memory.core = content
            elif memory_type == "important":
                self._memory.important = content
            elif memory_type == "recent":
                self._memory.recent = content
            else:
                raise ValueError(f"Unknown memory type: {memory_type}")
            logger.info(f"记忆重写: {memory_type} -> {len(content)} chars")

    async def trim_histories(self, keep_seconds: float = 300):
        now = time.time()
        async with self._lock:
            while self._host_history and (now - self._host_history[0].timestamp) > keep_seconds:
                self._host_history.popleft()
            while self._game_history and (now - self._game_history[0].timestamp) > keep_seconds:
                self._game_history.popleft()

    async def get_context_summary(self) -> dict:
        host_entries = await self.get_host_history(limit=10)
        game_entries = await self.get_game_history(limit=10)
        memory = await self.get_memory()
        return {
            "host_history": [e.to_dict() for e in host_entries],
            "game_history": [e.to_dict() for e in game_entries],
            "memory": memory.to_dict(),
        }


_shared_context: SharedContext | None = None


def get_shared_context() -> SharedContext:
    global _shared_context
    if _shared_context is None:
        _shared_context = SharedContext()
    return _shared_context
