"""B站弹幕 WebSocket 路由"""

import asyncio
import logging
import time

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from apps.live.bilibili.client import BilibiliClient
from apps.config import config
from apps.live.danmaku_handler import DanmakuData as ProcessDanmakuData, process_danmaku
from core.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()

_bilibili_clients: dict[str, BilibiliClient] = {}


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
        return SessdataVerifyResponse(valid=False, error="未配置SESSDATA")
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.bilibili.com/x/web-interface/nav",
                cookies={"SESSDATA": sessdata},
                timeout=10.0,
            )
            data = resp.json()
            if data.get("code") == 0:
                uname = data.get("data", {}).get("uname", "")
                return SessdataVerifyResponse(valid=True, uname=uname)
            else:
                return SessdataVerifyResponse(valid=False, error=data.get("message", "验证失败"))
    except Exception as e:
        logger.error(f"SESSDATA验证失败: {e}")
        return SessdataVerifyResponse(valid=False, error=str(e))


@router.post("/sessdata/update")
async def update_sessdata(request: SessdataUpdateRequest):
    import yaml
    from pathlib import Path
    
    config_file = Path(__file__).parent.parent.parent / "config.yaml"
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config_data = yaml.safe_load(f) or {}
        
        if "bilibili" not in config_data:
            config_data["bilibili"] = {}
        config_data["bilibili"]["sessdata"] = request.sessdata
        
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(config_data, f, allow_unicode=True, default_flow_style=False)
        
        config._data = config_data
        
        return {"success": True}
    except Exception as e:
        logger.error(f"更新SESSDATA失败: {e}")
        return {"success": False, "error": str(e)}


@router.websocket("/ws/{room_id}")
async def danmaku_websocket(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)

    if room_id not in _bilibili_clients:
        client = BilibiliClient(room_id=int(room_id))

        async def on_message(msg_type: str, data):
            message = {
                "type": msg_type,
                "data": data.to_dict() if hasattr(data, "to_dict") else data,
            }
            try:
                await manager.send_message(room_id, message)
            except Exception as e:
                logger.error(f"Failed to send danmaku: {e}")

            if msg_type == "danmaku" and hasattr(data, "content"):
                await process_danmaku(
                    ProcessDanmakuData(
                        msg_id=f"bilibili_{data.uid}_{int(time.time())}",
                        user=data.user,
                        content=data.content,
                        uid=data.uid or 0,
                        timestamp=int(time.time()),
                    ),
                    room_ids=[room_id],
                )

        client.set_callback(on_message)
        await client.connect()
        _bilibili_clients[room_id] = client
        logger.info(f"Started bilibili client for room {room_id}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(f"Received from client: {data}")
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for room {room_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(room_id)


@router.websocket("/ws/test/{room_id}")
async def test_danmaku_websocket(websocket: WebSocket, room_id: str):
    await manager.connect(websocket, room_id)

    async def receive_test_messages():
        try:
            while True:
                data = await websocket.receive_text()
                logger.debug(f"Received test message: {data}")
        except WebSocketDisconnect:
            logger.info(f"Test WebSocket disconnected for room {room_id}")

    asyncio.create_task(receive_test_messages())

    try:
        while True:
            await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"Test WebSocket error: {e}")
    finally:
        await manager.disconnect(room_id)
