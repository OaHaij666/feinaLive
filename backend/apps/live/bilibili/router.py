"""Bilibili live event and WebSocket routes."""

import asyncio
import logging
import time
import uuid
from pathlib import Path

import httpx
import yaml
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from apps.ai.messaging.dynamic_priority import get_priority_manager
from apps.ai.messaging.queue import Message, get_message_queue
from apps.config import config
from apps.live.danmaku_handler import DanmakuData as ProcessDanmakuData
from apps.live.danmaku_handler import process_danmaku
from apps.live.room_session import RoomSessionContext, get_room_session_manager
from core.websocket import manager

logger = logging.getLogger(__name__)
router = APIRouter()


class SessdataUpdateRequest(BaseModel):
    sessdata: str


class SessdataVerifyResponse(BaseModel):
    valid: bool
    uname: str = ""
    error: str = ""


@router.get("/sessdata/verify", response_model=SessdataVerifyResponse)
async def verify_sessdata():
    sessdata = config.bilibili_sessdata
    if not sessdata:
        return SessdataVerifyResponse(valid=False, error="未配置 SESSDATA")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 "
                        "Safari/537.36"
                    ),
                    "Referer": "https://www.bilibili.com",
                },
                cookies={"SESSDATA": sessdata},
                timeout=10.0,
            )
            data = response.json()
            if data.get("code") == 0:
                return SessdataVerifyResponse(
                    valid=True,
                    uname=data.get("data", {}).get("uname", ""),
                )
            return SessdataVerifyResponse(
                valid=False,
                error=data.get("message", "验证失败"),
            )
    except Exception as exc:
        logger.error("SESSDATA verification failed: %s", exc)
        return SessdataVerifyResponse(valid=False, error=str(exc))


@router.post("/sessdata/update")
async def update_sessdata(request: SessdataUpdateRequest):
    config_file = Path(__file__).parent.parent.parent.parent / "config.yaml"
    try:
        with open(config_file, "r", encoding="utf-8") as handle:
            config_data = yaml.safe_load(handle) or {}
        config_data.setdefault("bilibili", {})["sessdata"] = request.sessdata
        with open(config_file, "w", encoding="utf-8") as handle:
            yaml.dump(config_data, handle, allow_unicode=True, default_flow_style=False)
        config._data = config_data
        return {"success": True}
    except Exception as exc:
        logger.error("SESSDATA update failed: %s", exc)
        return {"success": False, "error": str(exc)}


async def _handle_room_event(context: RoomSessionContext, msg_type: str, data) -> None:
    """Route a current-session event to the UI and downstream consumer queue."""

    room_sessions = get_room_session_manager()
    if not room_sessions.is_current(context):
        return

    message = {
        "type": msg_type,
        "data": data.to_dict() if hasattr(data, "to_dict") else data,
        "context": context.to_dict(),
    }
    if msg_type != "danmaku":
        await manager.send_message(context.room_id, message)

    if msg_type == "danmaku" and hasattr(data, "content"):
        await process_danmaku(
            ProcessDanmakuData(
                msg_id=f"bilibili_{context.session_id}_{uuid.uuid4().hex}",
                user=data.user,
                content=data.content,
                uid=data.uid or 0,
                timestamp=int(time.time()),
            ),
            context=context,
        )
    elif msg_type == "gift" and hasattr(data, "gift_name"):
        gift_info = f"{data.uname} 赠送了 {data.gift_name}x{data.num}"
        total_coin = getattr(data, "total_coin", 0) or 0
        priority = get_priority_manager().get_gift_priority(total_coin)
        await get_message_queue().put(Message(
            priority=priority,
            source="gift",
            msg_type="gift_thanks",
            content=gift_info,
            data={
                "gift_info": gift_info,
                "user": data.uname,
                "uid": data.uid,
                "gift_name": data.gift_name,
                "num": data.num,
                "total_coin": total_coin,
            },
            context=context.to_dict(),
            user_id=str(data.uid or ""),
            expire_at=time.time() + 60,
            allow_skip=True,
        ))


get_room_session_manager().set_event_handler(_handle_room_event)


@router.websocket("/ws/{room_id}")
async def danmaku_websocket(websocket: WebSocket, room_id: str):
    configured_room_id = str(config.bilibili_room_id)
    if config.bilibili_room_id <= 0 or room_id != configured_room_id:
        await websocket.close(code=1008, reason="room is not the configured active room")
        logger.warning(
            "Rejected WebSocket subscription for room %s; configured room is %s",
            room_id,
            configured_room_id,
        )
        return

    connection_id = await manager.connect(websocket, room_id)
    try:
        context = await get_room_session_manager().activate(configured_room_id)
        await manager.disconnect_other_rooms(context.room_id)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for room %s", room_id)
    except Exception as exc:
        logger.error("WebSocket error for room %s: %s", room_id, exc)
    finally:
        await manager.disconnect(room_id, connection_id)


@router.websocket("/ws/test/{room_id}")
async def test_danmaku_websocket(websocket: WebSocket, room_id: str):
    """Legacy test socket, isolated from real room routing."""

    connection_id = await manager.connect(websocket, "test_room")

    async def receive_test_messages():
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            logger.info("Legacy test WebSocket disconnected")

    receive_task = asyncio.create_task(receive_test_messages())
    try:
        await receive_task
    finally:
        receive_task.cancel()
        await manager.disconnect("test_room", connection_id)
