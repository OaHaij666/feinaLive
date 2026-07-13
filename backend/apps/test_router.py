"""Internal control-plane endpoints, including the simulated live platform."""

import logging
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.live.models import (
    GiftValue,
    LiveEvent,
    LiveEventType,
    LiveGift,
    LivePlatform,
    LiveUser,
)
from apps.live.runtime import get_live_runtime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["test"])


class TestLiveEventInput(BaseModel):
    type: LiveEventType
    user: str = "测试观众"
    user_id: str = "viewer"
    content: str = ""
    gift_name: str = "小花花"
    gift_count: int = Field(default=1, ge=1)
    value_minor: int = Field(default=0, ge=0)
    stats: dict[str, int | float | str] = Field(default_factory=dict)


@router.post("/live/event")
async def send_test_live_event(event_input: TestLiveEventInput):
    """Emit one standard event through the active TestLiveAdapter."""
    runtime = get_live_runtime()
    context = runtime.active_context
    if context is None or context.platform is not LivePlatform.TEST:
        raise HTTPException(status_code=409, detail="当前运行平台不是测试平台，请修改配置并重启")

    user = None
    if event_input.type not in {LiveEventType.ROOM_STATS, LiveEventType.LIVE_ENDED}:
        user = LiveUser(
            platform=LivePlatform.TEST,
            platform_user_id=event_input.user_id.strip() or event_input.user.strip(),
            display_name=event_input.user.strip() or "测试观众",
        )

    gift = None
    if event_input.type in {
        LiveEventType.GIFT,
        LiveEventType.SUPER_CHAT,
        LiveEventType.MEMBERSHIP,
    }:
        gift = LiveGift(
            name=event_input.gift_name.strip() or "模拟礼物",
            count=event_input.gift_count,
            value=GiftValue(
                value_minor=event_input.value_minor,
                platform_value=event_input.value_minor,
                platform_unit="模拟人民币分",
            ),
        )

    event = LiveEvent(
        event_id=f"test_{time.time_ns()}",
        type=event_input.type,
        timestamp=int(time.time()),
        user=user,
        content=event_input.content.strip(),
        gift=gift,
        stats=event_input.stats,
        metadata={"simulated": True},
    )
    await runtime.inject_test_event(event)
    logger.info("Test platform emitted %s event=%s", event.type.value, event.event_id)
    return {
        "success": True,
        "accepted": True,
        "event": event.model_dump(mode="json"),
        "context": context.to_dict(),
    }
