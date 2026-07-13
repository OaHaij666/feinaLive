import asyncio

import pytest

from apps.ai.messaging.queue import Message, PriorityMessageQueue
from apps.live.models import LiveEvent, LiveEventType, LivePlatform
from apps.live.runtime import LivePlatformRuntime, reset_live_runtime
from core.websocket import ConnectionManager


class FakeAdapter:
    def __init__(self, platform: LivePlatform, room_id: str):
        self.platform = platform
        self.room_id = room_id
        self.callback = None
        self.is_running = False
        self.close_count = 0

    def set_event_callback(self, callback):
        self.callback = callback

    async def connect(self):
        self.is_running = True

    async def close(self):
        self.close_count += 1
        self.is_running = False

    async def emit(self, event):
        assert self.callback is not None
        await self.callback(event)


class FakeAdapterFactory:
    def __init__(self):
        self.adapters: list[FakeAdapter] = []

    def __call__(self, platform, room_id):
        adapter = FakeAdapter(platform, room_id)
        self.adapters.append(adapter)
        return adapter


class AllowAllRateLimiter:
    def allow(self, source: str, msg_type: str) -> bool:
        return True


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, code=1000, reason=""):
        pass


@pytest.mark.asyncio
async def test_switch_closes_old_adapter_and_drops_late_events():
    factory = FakeAdapterFactory()
    runtime = LivePlatformRuntime(factory)
    events = []
    runtime.set_event_handler(lambda envelope: _append(events, envelope))

    first = await runtime.start(LivePlatform.BILIBILI, "100")
    old = factory.adapters[0]
    second = await runtime.start(LivePlatform.DOUYIN, "abc")
    current = factory.adapters[1]
    await old.emit(LiveEvent(type=LiveEventType.ROOM_STATS, timestamp=1))
    await current.emit(LiveEvent(type=LiveEventType.ROOM_STATS, timestamp=2))
    await asyncio.sleep(0)

    assert old.close_count == 1
    assert runtime.active_context == second
    assert first.generation < second.generation
    assert [item.context.platform for item in events] == [LivePlatform.DOUYIN]
    await runtime.stop()


async def _append(events, envelope):
    events.append(envelope)


@pytest.mark.asyncio
async def test_concurrent_start_still_leaves_one_running_adapter():
    factory = FakeAdapterFactory()
    runtime = LivePlatformRuntime(factory)
    await asyncio.gather(
        runtime.start(LivePlatform.BILIBILI, "100"),
        runtime.start(LivePlatform.DOUYIN, "abc"),
    )
    assert len([adapter for adapter in factory.adapters if adapter.is_running]) == 1
    await runtime.stop()


@pytest.mark.asyncio
async def test_test_session_is_exclusive_and_does_not_bypass_active_session():
    factory = FakeAdapterFactory()
    runtime = LivePlatformRuntime(factory)
    real = await runtime.start(LivePlatform.BILIBILI, "100")
    test = await runtime.start(LivePlatform.TEST, "ignored")
    assert not runtime.is_current(real)
    assert runtime.is_current(test)
    assert test.platform is LivePlatform.TEST
    assert test.room_id == "test"
    assert factory.adapters[0].close_count == 1
    await runtime.stop()


@pytest.mark.asyncio
async def test_test_adapter_events_use_the_runtime_queue():
    runtime = LivePlatformRuntime()
    events = []
    runtime.set_event_handler(lambda envelope: _append(events, envelope))
    context = await runtime.start(LivePlatform.TEST, "ignored")

    await runtime.inject_test_event(
        LiveEvent(type=LiveEventType.DANMAKU, timestamp=1)
    )
    await asyncio.sleep(0)

    assert runtime.is_running
    assert len(events) == 1
    assert events[0].context == context
    assert events[0].event.type is LiveEventType.DANMAKU
    await runtime.stop()


@pytest.mark.asyncio
async def test_queue_rejects_superseded_platform_session_messages():
    factory = FakeAdapterFactory()
    runtime = LivePlatformRuntime(factory)
    reset_live_runtime(runtime)
    first = await runtime.start(LivePlatform.BILIBILI, "100")
    second = await runtime.start(LivePlatform.DOUYIN, "abc")
    queue = PriorityMessageQueue(rate_limiter=AllowAllRateLimiter(), max_size=10)
    assert not await queue.put(
        Message(source="danmaku", msg_type="danmaku", content="stale", context=first.to_dict())
    )
    assert await queue.put(
        Message(source="danmaku", msg_type="danmaku", content="current", context=second.to_dict())
    )
    assert (await queue.get()).content == "current"
    await runtime.stop()
    reset_live_runtime()


@pytest.mark.asyncio
async def test_websocket_manager_keeps_consumers_separate():
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    first_id = await manager.connect(first, "live:bilibili:100")
    second_id = await manager.connect(second, "live:bilibili:100")
    await manager.send_message("live:bilibili:100", {"type": "live_event"})
    await manager.disconnect("live:bilibili:100", first_id)
    await manager.send_message("live:bilibili:100", {"type": "reply"})
    assert first.messages == [{"type": "live_event"}]
    assert second.messages == [{"type": "live_event"}, {"type": "reply"}]
    await manager.disconnect("live:bilibili:100", second_id)
