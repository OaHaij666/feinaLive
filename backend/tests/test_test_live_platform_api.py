import asyncio

import pytest
from fastapi import HTTPException

from apps.live.models import LiveEventType, LivePlatform
from apps.live.runtime import LivePlatformRuntime, reset_live_runtime
from apps.test_router import TestLiveEventInput as LiveEventInput
from apps.test_router import send_test_live_event


@pytest.mark.asyncio
async def test_control_api_emits_standard_event_through_test_platform():
    runtime = LivePlatformRuntime()
    reset_live_runtime(runtime)
    envelopes = []

    async def capture(envelope):
        envelopes.append(envelope)

    runtime.set_event_handler(capture)
    await runtime.start(LivePlatform.TEST, "ignored")

    response = await send_test_live_event(
        LiveEventInput(
            type=LiveEventType.GIFT,
            user="viewer",
            user_id="42",
            gift_name="flower",
            gift_count=2,
            value_minor=300,
        )
    )
    await asyncio.sleep(0)

    assert response["accepted"] is True
    assert response["context"]["platform"] == "test"
    assert len(envelopes) == 1
    event = envelopes[0].event
    assert event.user and event.user.user_id == "test:42"
    assert event.gift and event.gift.value.value_minor == 300
    assert event.metadata["simulated"] is True

    await runtime.stop()
    reset_live_runtime()


@pytest.mark.asyncio
async def test_control_api_rejects_events_without_active_test_platform():
    reset_live_runtime()

    with pytest.raises(HTTPException) as error:
        await send_test_live_event(LiveEventInput(type=LiveEventType.DANMAKU))

    assert error.value.status_code == 409
    reset_live_runtime()
