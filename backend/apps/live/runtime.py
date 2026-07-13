from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from apps.live.adapters.base import LivePlatformAdapter
from apps.live.models import (
    LiveEvent,
    LiveEventEnvelope,
    LiveEventType,
    LivePlatform,
    LiveSessionContext,
)

logger = logging.getLogger(__name__)
LiveEventHandler = Callable[[LiveEventEnvelope], Awaitable[Any]]
AdapterFactory = Callable[[LivePlatform, str], LivePlatformAdapter]


def _default_adapter_factory(platform: LivePlatform, room_id: str) -> LivePlatformAdapter:
    if platform is LivePlatform.BILIBILI:
        from apps.live.adapters.bilibili import BilibiliLiveAdapter

        return BilibiliLiveAdapter(room_id)
    if platform is LivePlatform.DOUYIN:
        from apps.live.adapters.douyin.client import DouyinLiveAdapter

        return DouyinLiveAdapter(room_id)
    if platform is LivePlatform.TEST:
        from apps.live.adapters.test import TestLiveAdapter

        return TestLiveAdapter(room_id)
    raise ValueError(f"Unsupported live platform: {platform.value}")


class LivePlatformRuntime:
    """Own exactly one platform/room session and reject all stale events."""

    def __init__(self, adapter_factory: AdapterFactory | None = None) -> None:
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._lock = asyncio.Lock()
        self._active: LiveSessionContext | None = None
        self._adapter: LivePlatformAdapter | None = None
        self._events: asyncio.Queue[tuple[LiveSessionContext, LiveEvent]] = asyncio.Queue(
            maxsize=1000
        )
        self._worker: asyncio.Task | None = None
        self._generation = 0
        self._handler: LiveEventHandler | None = None

    @property
    def active_context(self) -> LiveSessionContext | None:
        return self._active

    @property
    def is_running(self) -> bool:
        return bool(self._active and self._adapter and self._adapter.is_running)

    def set_event_handler(self, handler: LiveEventHandler) -> None:
        self._handler = handler

    def is_current(self, context: LiveSessionContext) -> bool:
        return context == self._active

    async def start(
        self,
        platform: LivePlatform | str,
        room_id: str | int,
    ) -> LiveSessionContext:
        selected = LivePlatform(platform)
        normalized_room = "test" if selected is LivePlatform.TEST else str(room_id).strip()
        if not normalized_room:
            raise ValueError("live room id must not be empty")

        async with self._lock:
            await self._stop_locked()
            self._generation += 1
            context = LiveSessionContext(
                platform=selected,
                room_id=normalized_room,
                session_id=uuid4().hex,
                generation=self._generation,
            )
            adapter = self._adapter_factory(selected, normalized_room)

            async def on_event(event: LiveEvent) -> None:
                self._enqueue(context, event)

            adapter.set_event_callback(on_event)
            self._active = context
            self._adapter = adapter
            self._worker = asyncio.create_task(
                self._event_loop(), name="live-platform-dispatcher"
            )
            try:
                await adapter.connect()
            except Exception:
                self._active = None
                self._adapter = None
                worker = self._worker
                self._worker = None
                if worker is not None:
                    worker.cancel()
                    await asyncio.gather(worker, return_exceptions=True)
                await adapter.close()
                raise
            logger.info(
                "Activated live platform=%s room=%s session=%s",
                selected.value,
                normalized_room,
                context.session_id,
            )
            return context

    async def inject_test_event(self, event: LiveEvent) -> Any:
        context = self._active
        adapter = self._adapter
        if context is None or context.platform is not LivePlatform.TEST:
            raise RuntimeError("test live platform is not active")
        if adapter is None or adapter.platform is not LivePlatform.TEST:
            raise RuntimeError("test live platform adapter is not running")
        emit_event = getattr(adapter, "emit_event", None)
        if emit_event is None:
            raise RuntimeError("active test adapter cannot emit simulated events")
        await emit_event(event)

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        adapter = self._adapter
        worker = self._worker
        context = self._active
        self._active = None
        self._adapter = None
        self._worker = None
        if adapter is not None:
            await adapter.close()
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        while not self._events.empty():
            self._events.get_nowait()
        if context is not None:
            logger.info("Stopped live session %s", context)

    async def _dispatch(self, context: LiveSessionContext, event: LiveEvent) -> Any:
        if not self.is_current(context):
            logger.debug("Dropped stale live event context=%s event=%s", context, event.type)
            return None
        if event.user is not None and event.user.platform is not context.platform:
            logger.warning(
                "Dropped cross-platform event context=%s user_platform=%s",
                context.platform.value,
                event.user.platform.value,
            )
            return None
        if self._handler is not None:
            return await self._handler(LiveEventEnvelope(context=context, event=event))
        return None

    def _enqueue(self, context: LiveSessionContext, event: LiveEvent) -> None:
        if not self.is_current(context):
            return
        if self._events.qsize() >= 800 and event.type in {
            LiveEventType.LIKE,
            LiveEventType.VIEWER_ENTER,
            LiveEventType.ROOM_STATS,
        }:
            logger.debug("Dropped telemetry event under backpressure: %s", event.type.value)
            return
        try:
            self._events.put_nowait((context, event))
        except asyncio.QueueFull:
            logger.warning("Live event buffer full; dropped %s", event.type.value)

    async def _event_loop(self) -> None:
        while True:
            context, event = await self._events.get()
            try:
                await self._dispatch(context, event)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Live event dispatch failed: %s", event.type.value)


_runtime: LivePlatformRuntime | None = None


def get_live_runtime() -> LivePlatformRuntime:
    global _runtime
    if _runtime is None:
        _runtime = LivePlatformRuntime()
    return _runtime


def reset_live_runtime(runtime: LivePlatformRuntime | None = None) -> LivePlatformRuntime:
    global _runtime
    _runtime = runtime or LivePlatformRuntime()
    return _runtime
