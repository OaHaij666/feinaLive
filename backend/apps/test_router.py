"""弹幕测试路由 - 用于测试环境模拟弹幕"""

import logging
import time
from datetime import datetime

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

from apps.ai.admin_commands import get_admin_handler
from apps.config import config
from apps.live.danmaku_handler import DanmakuData, process_danmaku
from apps.live.room_session import RoomSessionContext
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


@router.post("/danmaku")
async def send_test_danmaku(danmaku: TestDanmakuInput):
    """发送测试弹幕 - 与真实弹幕走同一路线"""
    from apps.ai.admin_commands import get_admin_handler as get_admin

    if not get_admin().get_state().is_test_room_enabled:
        return {
            "success": False,
            "accepted": False,
            "msg_id": "",
            "user": danmaku.user,
            "content": danmaku.content,
            "uid": danmaku.uid,
            "music_intercepted": False,
            "timestamp": datetime.now().isoformat(),
            "error": "测试房间未启用，请先启用测试房间",
        }

    msg_id = f"test_{int(time.time() * 1000)}"

    logger.info(f"[测试弹幕] {danmaku.user} ({danmaku.uid}): {danmaku.content}")

    result = await process_danmaku(
        DanmakuData(
            msg_id=msg_id,
            user=danmaku.user,
            content=danmaku.content,
            uid=danmaku.uid,
            timestamp=int(time.time()),
        ),
        context=RoomSessionContext.test_room(),
    )

    return {
        "success": result.success,
        "accepted": result.accepted,
        "msg_id": msg_id,
        "user": danmaku.user,
        "content": danmaku.content,
        "uid": danmaku.uid,
        "music_intercepted": result.intercepted,
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
    from apps.ai.host_brain import get_host_brain
    brain = get_host_brain()
    return {
        "buffer_size": brain.buffer_size,
        "unanswered_count": brain.unanswered_count,
    }


@router.get("/ai/buffer")
async def get_buffer():
    """获取当前弹幕缓冲区"""
    from apps.ai.host_brain import get_host_brain
    brain = get_host_brain()
    return {
        "buffer": [d.to_dict() for d in brain._danmaku_buffer],
        "size": len(brain._danmaku_buffer),
    }


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
    connection_id = await manager.connect(websocket, TEST_ROOM)

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Test WS received: {data}")
    except Exception:
        pass
    finally:
        await manager.disconnect(TEST_ROOM, connection_id)
