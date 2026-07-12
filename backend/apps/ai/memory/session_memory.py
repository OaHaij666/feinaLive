"""Per-run game memory and the pending event window."""

from __future__ import annotations

import logging
import time
import uuid
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
    """Three text layers plus an event FIFO for the current game run."""

    def __init__(self, pending_maxlen: int = 40, summarize_threshold: int = 12):
        threshold = max(1, int(summarize_threshold))
        # Pending events are durable and must never be silently evicted when the
        # LLM is unavailable. The engine consumes this unbounded queue in fixed
        # batches; ``pending_maxlen`` remains a compatibility argument.
        self._pending_maxlen = None
        self._summarize_threshold = threshold
        self._core = ""
        self._important = ""
        self._recent = ""
        self._active = False
        self._game_id = ""
        self._session_id = ""
        self._pending_events: deque[SessionMemoryEvent] = deque()
        self._next_event_id = 1
        self._summarized_until_id = 0
        self._last_event_at = 0.0

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
    def game_id(self) -> str:
        return self._game_id

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def last_event_at(self) -> float:
        return self._last_event_at

    @property
    def pending_events(self) -> list[SessionMemoryEvent]:
        return list(self._pending_events)

    @property
    def summarized_until_id(self) -> int:
        return self._summarized_until_id

    @property
    def summarize_threshold(self) -> int:
        return self._summarize_threshold

    def set_summarize_threshold(self, value: int) -> None:
        self._summarize_threshold = max(1, int(value))

    def update_core(self, content: str):
        self._core = str(content or "").strip()

    def update_important(self, content: str):
        self._important = str(content or "").strip()

    def update_recent(self, content: str):
        self._recent = str(content or "").strip()

    def append_recent(self, content: str):
        content = str(content or "").strip()
        if content:
            self._recent = f"{self._recent}\n{content}".strip()

    def append_event(
        self,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        event_id: int | None = None,
        created_at: float | None = None,
    ) -> SessionMemoryEvent | None:
        content = str(content or "").strip()
        if not content:
            return None
        assigned_id = int(event_id or self._next_event_id)
        event = SessionMemoryEvent(
            event_id=assigned_id,
            event_type=event_type,
            content=content,
            metadata=metadata or {},
            created_at=float(created_at or time.time()),
        )
        self._next_event_id = max(self._next_event_id, assigned_id + 1)
        self._pending_events.append(event)
        self._last_event_at = max(self._last_event_at, event.created_at)
        return event

    def should_summarize(self) -> bool:
        return len(self._pending_events) >= self._summarize_threshold

    def is_idle(self, idle_seconds: float, now: float | None = None) -> bool:
        return bool(
            self._pending_events
            and self._last_event_at
            and float(now or time.time()) - self._last_event_at >= max(1.0, idle_seconds)
        )

    def pending_to_prompt_text(self) -> str:
        return "\n".join(event.to_prompt_line() for event in self._pending_events)

    def pending_context_to_prompt_text(self, max_chars: int = 12000) -> str:
        """Return the newest complete events that fit the agent context budget.

        Under normal conditions the pending queue is no longer than one summary
        batch, so every unsummarized event is visible. The budget only becomes
        relevant when summarization is unavailable and durable events accumulate.
        """
        budget = max(1000, int(max_chars))
        selected: list[str] = []
        used = 0
        for event in reversed(self._pending_events):
            line = event.to_prompt_line()
            cost = len(line) + (1 if selected else 0)
            if selected and used + cost > budget:
                break
            if not selected and cost > budget:
                line = line[-budget:]
                cost = len(line)
            selected.append(line)
            used += cost
        selected.reverse()
        return "\n".join(selected)

    def apply_summary(
        self,
        summary: SessionMemorySummary | dict[str, str],
        *,
        until_event_id: int | None = None,
    ):
        if isinstance(summary, dict):
            core = summary.get("core", self._core)
            important = summary.get("important", self._important)
            recent = summary.get("recent", self._recent)
        else:
            core = summary.core or self._core
            important = summary.important or self._important
            recent = summary.recent or self._recent
        self._core = str(core or "").strip()
        self._important = str(important or "").strip()
        self._recent = str(recent or "").strip()

        boundary = int(
            until_event_id or (self._pending_events[-1].event_id if self._pending_events else 0)
        )
        if boundary:
            self._summarized_until_id = max(self._summarized_until_id, boundary)
            self._pending_events = deque(
                event for event in self._pending_events if event.event_id > boundary
            )
        logger.info("游戏单局记忆总结完成: until_event_id=%s", boundary)

    def search_replace(self, layer: str, search: str, replace: str) -> bool:
        attr = f"_{layer}"
        current = getattr(self, attr, None)
        if current is None or search not in current:
            return False
        setattr(self, attr, current.replace(search, replace))
        return True

    def clear(self):
        self._core = ""
        self._important = ""
        self._recent = ""
        self._pending_events.clear()
        self._next_event_id = 1
        self._summarized_until_id = 0
        self._last_event_at = 0.0
        self._game_id = ""
        self._session_id = ""
        self._active = False

    def start_session(self, game_id: str, session_id: str | None = None):
        self.clear()
        self._active = True
        self._game_id = str(game_id)
        self._session_id = session_id or uuid.uuid4().hex
        logger.info("游戏单局记忆已开始: game=%s session=%s", self._game_id, self._session_id)

    def end_session(self) -> None:
        self._active = False

    def restore(
        self,
        *,
        game_id: str,
        session_id: str,
        core: str,
        important: str,
        recent: str,
        summarized_until_id: int,
        events: list[SessionMemoryEvent],
    ) -> None:
        self.start_session(game_id, session_id)
        self._core = core
        self._important = important
        self._recent = recent
        self._summarized_until_id = int(summarized_until_id)
        for event in events:
            self.append_event(
                event.event_type,
                event.content,
                event.metadata,
                event_id=event.event_id,
                created_at=event.created_at,
            )

    def to_prompt_text(self) -> str:
        sections: list[str] = []
        if self._core:
            sections.append(f"【核心记忆】\n{self._core}")
        if self._important:
            sections.append(f"【重要记忆】\n{self._important}")
        if self._recent:
            sections.append(f"【最近记忆】\n{self._recent}")
        if self._pending_events:
            sections.append("【待总结近期事件】\n" + self.pending_context_to_prompt_text())
        return "\n\n".join(sections)


__all__ = ["SessionMemory", "SessionMemoryEvent", "SessionMemorySummary"]
