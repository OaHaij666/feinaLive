from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

from apps.live.models import LiveEvent, LivePlatform

LiveEventCallback = Callable[[LiveEvent], Awaitable[None]]


class LivePlatformAdapter(Protocol):
    platform: LivePlatform
    room_id: str

    @property
    def is_running(self) -> bool: ...

    def set_event_callback(self, callback: LiveEventCallback) -> None: ...

    async def connect(self) -> None: ...

    async def close(self) -> None: ...
