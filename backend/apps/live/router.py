from __future__ import annotations

import logging
import re

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.config import config
from apps.live.dispatcher import dispatch_live_event
from apps.live.models import LivePlatform
from apps.live.runtime import get_live_runtime
from core.websocket import manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/live", tags=["live"])
get_live_runtime().set_event_handler(dispatch_live_event)


@router.get("/state")
async def live_state():
    runtime = get_live_runtime()
    return {
        "running": runtime.is_running,
        "context": runtime.active_context.to_dict() if runtime.active_context else None,
        "platforms": [platform.value for platform in LivePlatform],
    }


@router.get("/platforms/bilibili/verify")
async def verify_bilibili_credentials():
    if not config.bilibili_sessdata:
        return {"valid": False, "error": "未配置 SESSDATA"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com"},
                cookies={"SESSDATA": config.bilibili_sessdata},
            )
        payload = response.json()
        if payload.get("code") == 0:
            return {"valid": True, "username": payload.get("data", {}).get("uname", "")}
        return {"valid": False, "error": payload.get("message", "验证失败")}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


@router.get("/platforms/douyin/verify")
async def verify_douyin_credentials():
    if not config.douyin_web_rid:
        return {"valid": False, "error": "未配置抖音 web_rid"}
    headers = {"User-Agent": "Mozilla/5.0"}
    if config.douyin_cookie:
        headers["Cookie"] = config.douyin_cookie
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            response = await client.get(
                f"https://live.douyin.com/{config.douyin_web_rid}", headers=headers
            )
        response.raise_for_status()
        room_id = re.search(r'roomId\\?"\s*:\s*\\?"(\d+)\\?"', response.text)
        return {
            "valid": room_id is not None,
            "room_id": room_id.group(1) if room_id else "",
            "error": "" if room_id else "直播间不存在、未开播或 Cookie 已失效",
        }
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


@router.websocket("/ws")
async def live_websocket(websocket: WebSocket):
    context = get_live_runtime().active_context
    if context is None:
        await websocket.close(code=1008, reason="live platform is not active")
        return
    connection_id = await manager.connect(websocket, context.routing_key)
    try:
        await websocket.send_json(
            {"type": "live_session", "data": context.to_dict(), "context": context.to_dict()}
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(context.routing_key, connection_id)
