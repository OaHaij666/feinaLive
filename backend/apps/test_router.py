"""弹幕测试路由 - 用于测试环境模拟弹幕"""

import asyncio
import base64
import logging
import time
from datetime import datetime

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

from apps.ai.host_brain import get_host_brain
from apps.ai.admin_commands import get_admin_handler
from apps.config import config
from core.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/test", tags=["test"])

TEST_ROOM = "test_room"


class TestDanmakuInput(BaseModel):
    user: str
    content: str
    uid: int = 0


class TestAdminCommandInput(BaseModel):
    command: str


def _target_room_ids() -> set[str]:
    room_ids = {TEST_ROOM}
    if config.bilibili_room_id > 0:
        room_ids.add(str(config.bilibili_room_id))
    if config.default_room_id > 0:
        room_ids.add(str(config.default_room_id))
    return room_ids


async def _broadcast_message(message: dict):
    for room_id in _target_room_ids():
        try:
            await manager.send_message(room_id, message)
        except Exception as e:
            logger.debug(f"前端WebSocket未连接(room={room_id}): {e}")


async def _process_ai_reply():
    brain = get_host_brain(config.default_room_id)
    reply = await brain.try_reply()
    if reply:
        await _broadcast_message({"type": "start", "data": {}})

        await _broadcast_message({
            "type": "text",
            "data": {"text": reply.text}
        })

        if reply.audio and reply.audio.audio_data:
            audio_base64 = base64.b64encode(reply.audio.audio_data).decode("utf-8")
            await _broadcast_message({
                "type": "audio",
                "data": {
                    "audio": audio_base64,
                    "text": reply.text,
                    "sentence_index": 0,
                    "char_offset": 0,
                    "char_length": len(reply.text)
                }
            })

        await _broadcast_message({
            "type": "end",
            "data": {"text": reply.text}
        })


@router.post("/danmaku")
async def send_test_danmaku(danmaku: TestDanmakuInput):
    """发送测试弹幕 - 与真实弹幕走同一路线"""
    brain = get_host_brain(config.default_room_id)

    msg_id = f"test_{int(time.time() * 1000)}"
    accepted = brain.push_danmaku(
        msg_id=msg_id, user=danmaku.user, content=danmaku.content, uid=danmaku.uid
    )

    logger.info(f"[测试弹幕] {danmaku.user} ({danmaku.uid}): {danmaku.content}")

    message = {
        "type": "danmaku",
        "data": {
            "id": msg_id,
            "uid": danmaku.uid,
            "user": danmaku.user,
            "uname": danmaku.user,
            "content": danmaku.content,
            "msg": danmaku.content,
            "timestamp": int(time.time()),
        }
    }
    await _broadcast_message(message)

    if accepted:
        asyncio.create_task(_process_ai_reply())

    return {
        "success": True,
        "accepted": accepted,
        "msg_id": msg_id,
        "user": danmaku.user,
        "content": danmaku.content,
        "uid": danmaku.uid,
        "timestamp": datetime.now().isoformat(),
    }


@router.post("/admin/command")
async def send_admin_command(cmd: TestAdminCommandInput):
    """发送管理员指令"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content=cmd.command
    )

    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "非管理员或无效指令"}


@router.get("/admin/state")
async def get_admin_state():
    """获取管理员状态"""
    handler = get_admin_handler()
    return handler.get_state_dict()


@router.get("/ai/status")
async def get_ai_status():
    """获取AI主播状态"""
    brain = get_host_brain(config.default_room_id)
    return {
        "is_replying": brain.is_replying,
        "buffer_size": brain.buffer_size,
        "unanswered_count": brain.unanswered_count,
    }


@router.get("/ai/buffer")
async def get_buffer():
    """获取当前弹幕缓冲区"""
    brain = get_host_brain(config.default_room_id)
    return {
        "buffer": [d.to_dict() for d in brain._danmaku_buffer],
        "size": len(brain._danmaku_buffer),
    }


@router.post("/music/sound/{level}")
async def test_set_volume(level: int):
    """测试音量设置 /sound 0-10"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content=f"/sound {level}"
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "指令执行失败"}


@router.post("/music/next")
async def test_music_next():
    """测试下一首 /next"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content="/next"
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "指令执行失败"}


@router.post("/music/pause/{action}")
async def test_music_pause(action: int):
    """测试暂停/恢复 /pause 1|0"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content=f"/pause {action}"
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "指令执行失败"}


@router.post("/music/rm")
async def test_music_rm():
    """测试移除当前歌曲 /rm"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content="/rm"
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "指令执行失败"}


@router.post("/music/add/{bvid}")
async def test_add_music(bvid: str):
    """测试添加音乐 /add_music BV号"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content=f"/add_music {bvid}"
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "指令执行失败"}


@router.websocket("/ws/test")
async def test_ws_danmaku(websocket: WebSocket):
    """测试用WebSocket - 接收测试弹幕和AI回复"""
    await manager.connect(websocket, TEST_ROOM)

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Test WS received: {data}")
    except Exception:
        pass
    finally:
        await manager.disconnect(TEST_ROOM)
