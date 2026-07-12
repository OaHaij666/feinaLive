import asyncio

import pytest

from apps.ai.messaging.queue import Message, PriorityMessageQueue
from apps.live.room_session import (
    LiveRoomSessionManager,
    reset_room_session_manager,
)
from core.websocket import ConnectionManager


class FakeRoomClient:
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.callback = None
        self.is_running = False
        self.close_count = 0

    def set_callback(self, callback):
        self.callback = callback

    async def connect(self):
        self.is_running = True

    async def close(self):
        self.close_count += 1
        self.is_running = False

    async def emit(self, msg_type="danmaku", data=None):
        assert self.callback is not None
        await self.callback(msg_type, data)


class FakeClientFactory:
    def __init__(self):
        self.clients: list[FakeRoomClient] = []

    def __call__(self, room_id: int):
        client = FakeRoomClient(room_id)
        self.clients.append(client)
        return client


class AllowAllRateLimiter:
    def allow(self, source: str, msg_type: str) -> bool:
        return True


class FakeWebSocket:
    def __init__(self):
        self.accepted = False
        self.messages = []
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, message):
        self.messages.append(message)

    async def close(self, code=1000, reason=""):
        self.closed = True


@pytest.mark.asyncio
async def test_switch_closes_old_client_and_drops_late_events():
    factory = FakeClientFactory()
    manager = LiveRoomSessionManager(factory)
    events = []
    manager.set_event_handler(
        lambda context, msg_type, data: _append_event(events, context, msg_type, data)
    )

    first = await manager.activate(100)
    first_client = factory.clients[0]
    second = await manager.activate(200)
    second_client = factory.clients[1]

    assert first_client.close_count == 1
    assert not first_client.is_running
    assert second_client.is_running
    assert manager.active_context == second
    assert first.generation < second.generation

    await first_client.emit(data="late")
    await second_client.emit(data="current")

    assert [(event[0].room_id, event[2]) for event in events] == [("200", "current")]


async def _append_event(events, context, msg_type, data):
    events.append((context, msg_type, data))


@pytest.mark.asyncio
async def test_concurrent_activation_still_leaves_one_running_client():
    factory = FakeClientFactory()
    manager = LiveRoomSessionManager(factory)

    await asyncio.gather(manager.activate(100), manager.activate(200))

    running = [client for client in factory.clients if client.is_running]
    assert len(running) == 1
    assert running[0].room_id == int(manager.active_room_id)


@pytest.mark.asyncio
async def test_queue_rejects_superseded_session_messages():
    factory = FakeClientFactory()
    manager = LiveRoomSessionManager(factory)
    reset_room_session_manager(manager)
    first = await manager.activate(100)
    second = await manager.activate(200)
    queue = PriorityMessageQueue(rate_limiter=AllowAllRateLimiter(), max_size=10)

    stale_accepted = await queue.put(Message(
        source="danmaku",
        msg_type="danmaku",
        content="stale",
        context=first.to_dict(),
    ))
    current_accepted = await queue.put(Message(
        source="danmaku",
        msg_type="danmaku",
        content="current",
        context=second.to_dict(),
    ))

    assert stale_accepted is False
    assert current_accepted is True
    assert (await queue.get()).content == "current"
    await manager.stop()
    reset_room_session_manager()


@pytest.mark.asyncio
async def test_websocket_manager_keeps_consumers_separate():
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    first_id = await manager.connect(first, "100")
    second_id = await manager.connect(second, "100")

    await manager.send_message("100", {"type": "danmaku"})
    await manager.disconnect("100", first_id)
    await manager.send_message("100", {"type": "reply"})

    assert first.messages == [{"type": "danmaku"}]
    assert second.messages == [{"type": "danmaku"}, {"type": "reply"}]
    assert await manager.connection_count("100") == 1
    await manager.disconnect("100", second_id)
