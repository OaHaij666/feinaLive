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


@router.get("/sessdata/verify")
async def verify_sessdata():
    from apps.config import config
    sessdata = config.bilibili_sessdata
    if not sessdata:
        return {"valid": False, "error": "SESSDATA未填写"}
    try:
        from bilibili_api import Credential
        credential = Credential(sessdata=sessdata)
        user_info = await credential.get_self_info()
        return {
            "valid": True,
            "mid": user_info.get("mid"),
            "uname": user_info.get("uname"),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


@router.post("/sessdata/update")
async def update_sessdata(new_sessdata: str):
    from pathlib import Path
    import yaml
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        data.setdefault("bilibili", {})["sessdata"] = new_sessdata
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True)
        from apps.config import Config
        Config._instance = None
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
