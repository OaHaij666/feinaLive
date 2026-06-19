"""单局游戏记忆 — 三层文本块 + 待总结事件 FIFO，新游戏时全部清空。

单局记忆的目标是“用完即弃”：它只服务当前一局游戏，不进入长期用户记忆。
近期事件先进入 pending FIFO，达到阈值后由 MemoryEngine 调 LLM 总结进 core / important / recent。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SessionMemoryEvent:
    event_id: int
    event_type: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def to_prompt_line(self) -> str:
        meta = ""
        if self.metadata:
            useful = {k: v for k, v in self.metadata.items() if v not in (None, "", [], {})}
            if useful:
                meta = f" | {useful}"
        return f"[{self.event_id}] {self.event_type}: {self.content}{meta}"


@dataclass
class SessionMemorySummary:
    core: str = ""
    important: str = ""
    recent: str = ""


class SessionMemory:
    """单局游戏记忆 — 三层文本块 + 待总结事件 FIFO。"""

    def __init__(self, pending_maxlen: int = 40, summarize_threshold: int = 12):
        self._core: str = ""
        self._important: str = ""
        self._recent: str = ""
        self._active: bool = False
        self._pending_events: deque[SessionMemoryEvent] = deque(maxlen=pending_maxlen)
        self._next_event_id: int = 1
        self._summarized_until_id: int = 0
        self._summarize_threshold = summarize_threshold

    @property
    def core(self) -> str:
        return self._core

    @property
    def important(self) -> str:
        return self._important

    @property
    def recent(self) -> str:
        return self._recent

    @property
    def active(self) -> bool:
        return self._active

    @property
    def pending_events(self) -> list[SessionMemoryEvent]:
        return list(self._pending_events)

    @property
    def summarized_until_id(self) -> int:
        return self._summarized_until_id

    def update_core(self, content: str):
        self._core = content.strip()

    def update_important(self, content: str):
        self._important = content.strip()

    def update_recent(self, content: str):
        self._recent = content.strip()

    def append_recent(self, content: str):
        content = content.strip()
        if not content:
            return
        if self._recent:
            self._recent += "\n" + content
        else:
            self._recent = content

    def append_event(
        self,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMemoryEvent | None:
        content = str(content or "").strip()
        if not content:
            return None
        event = SessionMemoryEvent(
            event_id=self._next_event_id,
            event_type=event_type,
            content=content,
            metadata=metadata or {},
        )
        self._next_event_id += 1
        self._pending_events.append(event)
        return event

    def should_summarize(self) -> bool:
        return len(self._pending_events) >= self._summarize_threshold

    def pending_to_prompt_text(self) -> str:
        if not self._pending_events:
            return ""
        return "\n".join(e.to_prompt_line() for e in self._pending_events)

    def apply_summary(self, summary: SessionMemorySummary | dict[str, str]):
        if isinstance(summary, dict):
            core = summary.get("core", self._core)
            important = summary.get("important", self._important)
            recent = summary.get("recent", self._recent)
        else:
            core = summary.core or self._core
            important = summary.important or self._important
            recent = summary.recent or self._recent

        self._core = core.strip()
        self._important = important.strip()
        self._recent = recent.strip()

        if self._pending_events:
            self._summarized_until_id = self._pending_events[-1].event_id
        self._pending_events.clear()
        logger.info("单局记忆总结完成: until_event_id=%s", self._summarized_until_id)

    def search_replace(self, layer: str, search: str, replace: str) -> bool:
        """搜索替换指定层的记忆"""
        attr = f"_{layer}"
        current = getattr(self, attr, None)
        if current is None:
            return False
        if search in current:
            setattr(self, attr, current.replace(search, replace))
            return True
        return False

    def clear(self):
        self._core = ""
        self._important = ""
        self._recent = ""
        self._pending_events.clear()
        self._next_event_id = 1
        self._summarized_until_id = 0
        self._active = False

    def start_session(self):
        self.clear()
        self._active = True
        logger.info("单局记忆已清空，新游戏开始")

    def to_prompt_text(self) -> str:
        sections = []
        if self._core:
            sections.append(f"【核心记忆】\n{self._core}")
        if self._important:
            sections.append(f"【重要记忆】\n{self._important}")
        if self._recent:
            sections.append(f"【最近记忆】\n{self._recent}")
        if self._pending_events:
            lines = [e.to_prompt_line() for e in list(self._pending_events)[-8:]]
            sections.append("【待总结近期事件】\n" + "\n".join(lines))
        return "\n\n".join(sections) if sections else ""


__all__ = ["SessionMemory", "SessionMemoryEvent", "SessionMemorySummary"]
