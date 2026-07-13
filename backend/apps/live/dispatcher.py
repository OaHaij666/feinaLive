from __future__ import annotations

import logging
import time
from collections import deque

from apps.ai.admin_commands import get_admin_handler
from apps.ai.messaging.dynamic_priority import (
    PRIORITY_DISPOSABLE,
    get_priority_manager,
)
from apps.ai.messaging.queue import Message, get_message_queue
from apps.live.danmaku_handler import DanmakuData, process_danmaku
from apps.live.models import LiveEventEnvelope, LiveEventType
from apps.live.runtime import get_live_runtime
from core.websocket import manager as websocket_manager

logger = logging.getLogger(__name__)
_recent_ids: deque[str] = deque(maxlen=5000)
_recent_id_set: set[str] = set()


async def dispatch_live_event(envelope: LiveEventEnvelope):
    """The only boundary from platform events into application consumers."""

    runtime = get_live_runtime()
    if not runtime.is_current(envelope.context):
        return None
    event = envelope.event
    if _is_duplicate(event.event_id):
        logger.debug("Dropped duplicate live event %s", event.event_id)
        return None

    if event.user is not None:
        event.user.is_admin = get_admin_handler().is_admin(
            event.user.user_id, event.user.display_name
        )

    await websocket_manager.send_message(
        envelope.context.routing_key,
        {
            "type": "live_event",
            "data": event.model_dump(mode="json"),
            "context": envelope.context.to_dict(),
        },
    )

    if event.type is LiveEventType.DANMAKU and event.user is not None:
        return await process_danmaku(
            DanmakuData(
                msg_id=event.event_id,
                user_id=event.user.user_id,
                user=event.user.display_name,
                content=event.content,
                timestamp=event.timestamp,
                is_admin=event.user.is_admin,
            ),
            context=envelope.context,
        )

    if event.type in {
        LiveEventType.GIFT,
        LiveEventType.SUPER_CHAT,
        LiveEventType.MEMBERSHIP,
    }:
        await _enqueue_support_event(envelope)
    elif event.type is LiveEventType.FOLLOW and event.user is not None:
        await get_message_queue().put(
            Message(
                priority=PRIORITY_DISPOSABLE,
                source="live_event",
                msg_type="live_notice",
                content=f"{event.user.display_name} 关注了主播",
                data={
                    "event_type": event.type.value,
                    "user": event.user.display_name,
                    "user_id": event.user.user_id,
                },
                context=envelope.context.to_dict(),
                user_id=event.user.user_id,
                expire_at=time.time() + 20,
                allow_skip=True,
            )
        )
    return None


async def _enqueue_support_event(envelope: LiveEventEnvelope) -> None:
    event = envelope.event
    if event.user is None or event.gift is None:
        return
    gift = event.gift
    value_minor = gift.value.value_minor
    detail = f"{event.user.display_name} 送出了 {gift.name} x{gift.count}"
    if value_minor:
        detail += f"（约 {gift.value.value_cny:.2f} 元）"
    if event.content:
        detail += f"，留言：{event.content}"
    await get_message_queue().put(
        Message(
            priority=get_priority_manager().get_gift_priority(value_minor),
            source="gift",
            msg_type="gift_thanks",
            content=detail,
            data={
                "event_type": event.type.value,
                "gift_info": detail,
                "user": event.user.display_name,
                "user_id": event.user.user_id,
                "gift": gift.model_dump(mode="json"),
                "value_minor": value_minor,
            },
            context=envelope.context.to_dict(),
            user_id=event.user.user_id,
            expire_at=time.time() + 60,
            allow_skip=True,
        )
    )


def _is_duplicate(event_id: str) -> bool:
    if event_id in _recent_id_set:
        return True
    if len(_recent_ids) == _recent_ids.maxlen:
        removed = _recent_ids.popleft()
        _recent_id_set.discard(removed)
    _recent_ids.append(event_id)
    _recent_id_set.add(event_id)
    return False
