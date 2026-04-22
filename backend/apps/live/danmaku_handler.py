"""弹幕处理逻辑 - 被真实弹幕和测试弹幕共用"""

import asyncio
import base64
import logging
from dataclasses import dataclass
from typing import Optional, Callable, Awaitable

from apps.ai.host_brain import get_host_brain
from apps.ai.admin_commands import get_admin_handler
from apps.config import config
from apps.live.music.service import get_danmaku_service
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
    room_ids: list[str],
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> DanmakuProcessResult:
    admin_handler = get_admin_handler()

    is_admin = admin_handler.is_admin(danmaku.uid) or admin_handler.is_admin_by_username(danmaku.user)
    is_admin_command = admin_handler.is_admin_command(danmaku.content)

    if is_admin and is_admin_command:
        logger.info(f"[管理员指令] {danmaku.user}: {danmaku.content}")
        asyncio.create_task(admin_handler.handle(danmaku.uid, danmaku.user, danmaku.content))
        return DanmakuProcessResult(success=True, intercepted=True)

    if is_admin and not is_admin_command and admin_handler.should_filter_admin_danmaku(danmaku.uid, danmaku.user):
        logger.info(f"[弹幕过滤] 管理员已开启隐藏模式，跳过: {danmaku.user}: {danmaku.content}")
        return DanmakuProcessResult(success=True, intercepted=True)

    music_service = get_danmaku_service()
    music_result = await music_service.process_danmaku(danmaku.content, danmaku.user)

    if music_result.isMusicRequest:
        logger.info(f"[弹幕拦截] 点歌请求: {danmaku.user}: {danmaku.content}")
        if music_result.musicItem:
            music_msg = {
                "type": "music_added",
                "data": {
                    "user": danmaku.user,
                    "title": music_result.musicItem.title,
                    "artist": music_result.musicItem.upName,
                }
            }
            await _broadcast_to_rooms(room_ids, music_msg, broadcast_fn)
        elif music_result.error:
            error_msg = {
                "type": "music_error",
                "data": {
                    "user": danmaku.user,
                    "content": danmaku.content,
                    "error": music_result.error,
                }
            }
            await _broadcast_to_rooms(room_ids, error_msg, broadcast_fn)
        return DanmakuProcessResult(
            success=True,
            intercepted=True,
            music_item=music_result.musicItem.model_dump() if music_result.musicItem else None,
            music_error=music_result.error,
        )

    danmaku_msg = {
        "type": "danmaku",
        "data": {
            "id": danmaku.msg_id,
            "uid": danmaku.uid,
            "user": danmaku.user,
            "uname": danmaku.user,
            "content": danmaku.content,
            "msg": danmaku.content,
            "timestamp": danmaku.timestamp or 0,
        }
    }
    await _broadcast_to_rooms(room_ids, danmaku_msg, broadcast_fn)

    brain = get_host_brain(config.default_room_id)
    accepted = brain.push_danmaku(
        msg_id=danmaku.msg_id,
        user=danmaku.user,
        content=danmaku.content,
        uid=danmaku.uid
    )

    if accepted:
        asyncio.create_task(_process_ai_reply(room_ids, broadcast_fn))

    return DanmakuProcessResult(
        success=True,
        intercepted=False,
        accepted=accepted,
    )


async def _broadcast_to_rooms(
    room_ids: list[str],
    message: dict,
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
):
    if broadcast_fn:
        await broadcast_fn(message)
    else:
        for room_id in room_ids:
            try:
                await manager.send_message(room_id, message)
            except Exception as e:
                logger.debug(f"WebSocket发送失败(room={room_id}): {e}")


async def _process_ai_reply(
    room_ids: list[str],
    broadcast_fn: Optional[Callable[[dict], Awaitable[None]]] = None,
):
    brain = get_host_brain(config.default_room_id)
    reply = await brain.try_reply()
    if reply:
        await _broadcast_to_rooms(room_ids, {"type": "start", "data": {}}, broadcast_fn)

        await _broadcast_to_rooms(room_ids, {
            "type": "text",
            "data": {"text": reply.text}
        }, broadcast_fn)

        if reply.audio and reply.audio.audio_data:
            audio_base64 = base64.b64encode(reply.audio.audio_data).decode("utf-8")
            await _broadcast_to_rooms(room_ids, {
                "type": "audio",
                "data": {
                    "audio": audio_base64,
                    "text": reply.text,
                    "sentence_index": 0,
                    "char_offset": 0,
                    "char_length": len(reply.text),
                }
            }, broadcast_fn)

        await _broadcast_to_rooms(room_ids, {
            "type": "end",
            "data": {"text": reply.text}
        }, broadcast_fn)
