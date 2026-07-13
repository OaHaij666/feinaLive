import asyncio

import pytest

from apps.live.dispatcher import dispatch_live_event
from apps.live.models import (
    GiftValue,
    LiveEvent,
    LiveEventEnvelope,
    LiveEventType,
    LiveGift,
    LivePlatform,
    LiveUser,
)
from apps.live.runtime import LivePlatformRuntime, reset_live_runtime


class CapturingQueue:
    def __init__(self):
        self.messages = []

    async def put(self, message):
        self.messages.append(message)
        return True


@pytest.mark.asyncio
async def test_simulated_gift_traverses_adapter_runtime_dispatcher_and_consumer_queue(
    monkeypatch,
):
    runtime = LivePlatformRuntime()
    reset_live_runtime(runtime)
    runtime.set_event_handler(dispatch_live_event)
    await runtime.start(LivePlatform.TEST, "test")
    queue = CapturingQueue()
    monkeypatch.setattr("apps.live.dispatcher.get_message_queue", lambda: queue)

    await runtime.inject_test_event(
        LiveEvent(
            event_id="simulated-gift-1",
            type=LiveEventType.GIFT,
            timestamp=1,
            user=LiveUser(
                platform=LivePlatform.TEST,
                platform_user_id="viewer",
                display_name="测试观众",
            ),
            gift=LiveGift(
                name="小花花",
                count=2,
                value=GiftValue(
                    value_minor=250,
                    platform_value=250,
                    platform_unit="模拟人民币分",
                ),
            ),
        )
    )
    await asyncio.sleep(0)

    assert len(queue.messages) == 1
    message = queue.messages[0]
    assert message.msg_type == "gift_thanks"
    assert message.user_id == "test:viewer"
    assert message.data["value_minor"] == 250
    await runtime.stop()
    reset_live_runtime()


@pytest.mark.asyncio
async def test_standard_gift_enters_host_consumer_queue_with_canonical_value(monkeypatch):
    runtime = LivePlatformRuntime()
    reset_live_runtime(runtime)
    context = await runtime.start(LivePlatform.TEST, "test")
    queue = CapturingQueue()
    monkeypatch.setattr("apps.live.dispatcher.get_message_queue", lambda: queue)
    event = LiveEvent(
        event_id="gift-standard-1",
        type=LiveEventType.GIFT,
        timestamp=1,
        user=LiveUser(
            platform=LivePlatform.TEST,
            platform_user_id="viewer",
            display_name="观众",
        ),
        gift=LiveGift(
            name="玫瑰",
            count=3,
            value=GiftValue(
                value_minor=30,
                platform_value=3,
                platform_unit="抖币",
            ),
        ),
    )
    await dispatch_live_event(LiveEventEnvelope(context=context, event=event))
    assert len(queue.messages) == 1
    message = queue.messages[0]
    assert message.msg_type == "gift_thanks"
    assert message.user_id == "test:viewer"
    assert message.data["value_minor"] == 30
    assert message.data["gift"]["value"]["currency"] == "CNY"
    await runtime.stop()
    reset_live_runtime()


@pytest.mark.asyncio
async def test_standard_danmaku_reaches_host_brain_with_platform_scoped_user_id(monkeypatch):
    runtime = LivePlatformRuntime()
    reset_live_runtime(runtime)
    context = await runtime.start(LivePlatform.TEST, "test")
    received = []

    class Brain:
        def push_danmaku(self, **values):
            received.append(values)
            return True

    async def no_music(*args, **kwargs):
        return None

    monkeypatch.setattr("apps.live.danmaku_handler.get_host_brain", lambda: Brain())
    monkeypatch.setattr("apps.live.danmaku_handler.process_music_danmaku", no_music)
    event = LiveEvent(
        event_id="danmaku-standard-1",
        type=LiveEventType.DANMAKU,
        timestamp=1,
        user=LiveUser(
            platform=LivePlatform.TEST,
            platform_user_id="sec-viewer",
            display_name="抖音观众",
        ),
        content="你好",
    )
    result = await dispatch_live_event(LiveEventEnvelope(context=context, event=event))
    assert result.accepted
    assert received[0]["user_id"] == "test:sec-viewer"
    assert received[0]["content"] == "你好"
    await runtime.stop()
    reset_live_runtime()
