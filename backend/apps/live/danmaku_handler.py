"""Shared danmaku business pipeline for real and explicitly isolated test input."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from apps.ai.admin_commands import get_admin_handler
from apps.ai.host_brain import get_host_brain
from apps.live.models import LiveSessionContext
from apps.live.music_requests import process_music_danmaku
from apps.live.runtime import get_live_runtime
from core.websocket import manager

logger = logging.getLogger(__name__)


@dataclass
class DanmakuData:
    msg_id: str
    user_id: str
    user: str
    content: str
    timestamp: int = 0
    is_admin: bool = False


@dataclass
class DanmakuProcessResult:
    success: bool
    intercepted: bool
    music_item: Optional[dict] = None
    music_error: Optional[str] = None
    accepted: bool = False


async def process_danmaku(
    danmaku: DanmakuData,
    context: LiveSessionContext,
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> DanmakuProcessResult:
    if not get_live_runtime().is_current(context):
        logger.debug("Dropped stale danmaku before processing: %s", context)
        return DanmakuProcessResult(success=False, intercepted=True)

    admin_handler = get_admin_handler()
    is_admin = danmaku.is_admin or admin_handler.is_admin(danmaku.user_id, danmaku.user)
    is_admin_command = admin_handler.is_admin_command(danmaku.content)

    if is_admin and is_admin_command:
        logger.info("[管理员指令] %s: %s", danmaku.user, danmaku.content)
        asyncio.create_task(
            admin_handler.handle(danmaku.user_id, danmaku.user, danmaku.content)
        )
        return DanmakuProcessResult(success=True, intercepted=True)

    if (
        is_admin
        and not is_admin_command
        and admin_handler.should_filter_admin_danmaku(danmaku.user_id, danmaku.user)
    ):
        return DanmakuProcessResult(success=True, intercepted=True)

    music_result = await process_music_danmaku(
        danmaku.content,
        danmaku.user,
        request_id=danmaku.msg_id,
    )
    if not get_live_runtime().is_current(context):
        logger.debug("Dropped danmaku after slow processing because session changed: %s", context)
        return DanmakuProcessResult(success=False, intercepted=True)

    if music_result is not None:
        if music_result.accepted and music_result.entry:
            await _broadcast_to_session(context, {
                "type": "music_added",
                "data": {
                    "user": danmaku.user,
                    "title": music_result.entry.track.title,
                    "artist": ", ".join(music_result.entry.track.artists),
                },
            }, broadcast_fn)
        elif music_result.error:
            await _broadcast_to_session(context, {
                "type": "music_error",
                "data": {
                    "user": danmaku.user,
                    "content": danmaku.content,
                    "error": music_result.error,
                },
            }, broadcast_fn)
        return DanmakuProcessResult(
            success=True,
            intercepted=True,
            music_item=(
                music_result.entry.model_dump(mode="json") if music_result.entry else None
            ),
            music_error=music_result.error,
        )

    accepted = get_host_brain().push_danmaku(
        context=context,
        msg_id=danmaku.msg_id,
        user_id=danmaku.user_id,
        user=danmaku.user,
        content=danmaku.content,
    )
    return DanmakuProcessResult(
        success=True,
        intercepted=False,
        accepted=accepted,
    )


async def _broadcast_to_session(
    context: LiveSessionContext,
    message: dict,
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    if not get_live_runtime().is_current(context):
        logger.debug("Dropped stale broadcast: %s", context)
        return
    message.setdefault("context", context.to_dict())
    if broadcast_fn:
        await broadcast_fn(message)
    else:
        await manager.send_message(context.routing_key, message)
