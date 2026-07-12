from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any

from apps.agent.capabilities.base import Capability
from apps.agent.state import CapabilityCall, CapabilityResult, Observation


@dataclass(frozen=True, slots=True)
class AgentEvent:
    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: float = field(default_factory=time.time)


class EventInboxCapability(Capability):
    """Bounded process-local event inbox exposed as Agent observations."""

    source = "events"

    def __init__(self, maxlen: int = 200, batch_size: int = 20) -> None:
        self._events: deque[AgentEvent] = deque(maxlen=maxlen)
        self._batch_size = batch_size
        self._lock = asyncio.Lock()
        self._dropped = 0

    async def publish(self, event: AgentEvent) -> None:
        async with self._lock:
            if len(self._events) == self._events.maxlen:
                self._dropped += 1
            self._events.append(event)

    async def definitions(self) -> list[dict[str, Any]]:
        return []

    def owns(self, name: str) -> bool:
        return False

    def is_readonly(self, name: str) -> bool:
        return True

    async def execute(self, call: CapabilityCall) -> CapabilityResult:
        return CapabilityResult(call=call, success=False, error="event inbox is observation-only")

    async def observe(self) -> Observation | None:
        async with self._lock:
            events = [self._events.popleft() for _ in range(min(self._batch_size, len(self._events)))]
        if not events:
            return None
        lines = [
            f"[{event.source}/{event.event_type}] "
            f"{json.dumps(event.payload, ensure_ascii=False, default=str)[:1000]}"
            for event in events
        ]
        return Observation(
            source=self.source,
            summary="外部事件：\n" + "\n".join(lines),
            data=[asdict(event) for event in events],
            actionable=True,
            ref=f"observation:events:{events[-1].event_id}",
        )

    async def stats(self) -> dict[str, int]:
        async with self._lock:
            return {"pending": len(self._events), "dropped": self._dropped}
