from __future__ import annotations

from apps.live.adapters.base import LiveEventCallback
from apps.live.models import LiveEvent, LivePlatform


class TestLiveAdapter:
    """In-process platform whose events are produced by the control panel."""

    platform = LivePlatform.TEST
    room_id = "test"

    def __init__(self, _room_id: str = "test") -> None:
        self._callback: LiveEventCallback | None = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def set_event_callback(self, callback: LiveEventCallback) -> None:
        self._callback = callback

    async def connect(self) -> None:
        self._running = True

    async def close(self) -> None:
        self._running = False

    async def emit_event(self, event: LiveEvent) -> None:
        if not self._running or self._callback is None:
            raise RuntimeError("test live platform is not running")
        await self._callback(event)
