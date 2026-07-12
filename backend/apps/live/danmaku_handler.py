"""Shared danmaku business pipeline for real and explicitly isolated test input."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from apps.ai.admin_commands import get_admin_handler
from apps.ai.host_brain import get_host_brain
from apps.config import config
from apps.live.music.service import get_danmaku_service
from apps.live.room_session import RoomSessionContext, get_room_session_manager
from core.websocket import manager

logger = logging.getLogger(__name__)


@dataclass
class DanmakuData:
    msg_id: str
    user: str
    content: str
    uid: int
    timestamp: int = 0


@dataclass
class DanmakuProcessResult:
    success: bool
    intercepted: bool
    music_item: Optional[dict] = None
    music_error: Optional[str] = None
    accepted: bool = False


async def process_danmaku(
    danmaku: DanmakuData,
    context: RoomSessionContext,
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> DanmakuProcessResult:
    if not get_room_session_manager().is_current(context):
        logger.debug("Dropped stale danmaku before processing: %s", context)
        return DanmakuProcessResult(success=False, intercepted=True)

    admin_handler = get_admin_handler()
    is_admin = (
        admin_handler.is_admin(danmaku.uid)
        or admin_handler.is_admin_by_username(danmaku.user)
    )
    is_admin_command = admin_handler.is_admin_command(danmaku.content)

    if is_admin and is_admin_command:
        logger.info("[管理员指令] %s: %s", danmaku.user, danmaku.content)
        asyncio.create_task(
            admin_handler.handle(danmaku.uid, danmaku.user, danmaku.content)
        )
        return DanmakuProcessResult(success=True, intercepted=True)

    if (
        is_admin
        and not is_admin_command
        and admin_handler.should_filter_admin_danmaku(danmaku.uid, danmaku.user)
    ):
        return DanmakuProcessResult(success=True, intercepted=True)

    music_result = await get_danmaku_service().process_danmaku(
        danmaku.content,
        danmaku.user,
    )
    if not get_room_session_manager().is_current(context):
        logger.debug("Dropped danmaku after slow processing because session changed: %s", context)
        return DanmakuProcessResult(success=False, intercepted=True)

    if music_result.isMusicRequest:
        if music_result.musicItem:
            await _broadcast_to_session(context, {
                "type": "music_added",
                "data": {
                    "user": danmaku.user,
                    "title": music_result.musicItem.title,
                    "artist": music_result.musicItem.upName,
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
                music_result.musicItem.model_dump() if music_result.musicItem else None
            ),
            music_error=music_result.error,
        )

    await _broadcast_to_session(context, {
        "type": "danmaku",
        "data": {
            "id": danmaku.msg_id,
            "uid": danmaku.uid,
            "user": danmaku.user,
            "uname": danmaku.user,
            "content": danmaku.content,
            "msg": danmaku.content,
            "timestamp": danmaku.timestamp or 0,
        },
    }, broadcast_fn)

    accepted = get_host_brain(config.default_room_id).push_danmaku(
        context=context,
        msg_id=danmaku.msg_id,
        user=danmaku.user,
        content=danmaku.content,
        uid=danmaku.uid,
    )
    return DanmakuProcessResult(
        success=True,
        intercepted=False,
        accepted=accepted,
    )


async def _broadcast_to_session(
    context: RoomSessionContext,
    message: dict,
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    if not get_room_session_manager().is_current(context):
        logger.debug("Dropped stale broadcast: %s", context)
        return
    message.setdefault("context", context.to_dict())
    if broadcast_fn:
        await broadcast_fn(message)
    else:
        await manager.send_message(context.room_id, message)
