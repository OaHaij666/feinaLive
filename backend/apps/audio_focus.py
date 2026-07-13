from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

FocusListener = Callable[[bool], Awaitable[None]]


class AudioFocusCoordinator:
    """Tracks audible foreground owners and notifies background audio domains."""

    def __init__(self) -> None:
        self._holders: set[str] = set()
        self._listeners: list[FocusListener] = []
        self._lock = asyncio.Lock()

    def register(self, listener: FocusListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    async def acquire(self, holder_id: str) -> None:
        async with self._lock:
            was_active = bool(self._holders)
            self._holders.add(holder_id)
            listeners = list(self._listeners) if not was_active else []
        await self._notify(listeners, True)

    async def release(self, holder_id: str) -> None:
        async with self._lock:
            was_active = bool(self._holders)
            self._holders.discard(holder_id)
            listeners = list(self._listeners) if was_active and not self._holders else []
        await self._notify(listeners, False)

    @staticmethod
    async def _notify(listeners: list[FocusListener], active: bool) -> None:
        if listeners:
            await asyncio.gather(
                *(listener(active) for listener in listeners),
                return_exceptions=True,
            )


_coordinator: AudioFocusCoordinator | None = None


def get_audio_focus_coordinator() -> AudioFocusCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = AudioFocusCoordinator()
    return _coordinator
