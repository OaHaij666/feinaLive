"""B站弹幕 WebSocket 路由"""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.bilibili.client import BilibiliClient
from core.websocket import manager

logger = logging.getLogger(__name__)

router = APIRouter()

_bilibili_clients: dict[str, BilibiliClient] = {}


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


@router.post("/room/{room_id}/close")
async def close_room(room_id: str):
    if room_id in _bilibili_clients:
        client = _bilibili_clients[room_id]
        await client.close()
        del _bilibili_clients[room_id]
        logger.info(f"Closed bilibili client for room {room_id}")
        return {"status": "closed"}
    return {"status": "not_running"}


@router.get("/room/{room_id}/status")
async def get_room_status(room_id: str):
    if room_id in _bilibili_clients:
        client = _bilibili_clients[room_id]
        return {"room_id": room_id, "status": "running", "connected": client.is_running}
    return {"room_id": room_id, "status": "not_running", "connected": False}
