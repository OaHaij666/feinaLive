"""虚拟形象输入控制路由"""

import asyncio
import logging
import uuid

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.ai.playback import get_playback_coordinator

from . import get_easyvtuber_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/avatar/speaking")
async def set_speaking(speaking: bool):
    manager = get_easyvtuber_manager()
    manager.set_speaking(speaking)
    return {"success": True}


@router.post("/avatar/start")
async def start_avatar():
    manager = get_easyvtuber_manager()
    await manager.start()
    return {"success": True, "running": manager.is_running}


@router.post("/avatar/stop")
async def stop_avatar():
    manager = get_easyvtuber_manager()
    await manager.stop()
    return {"success": True, "running": manager.is_running}


@router.get("/avatar/status")
async def get_avatar_status():
    manager = get_easyvtuber_manager()
    return {"running": manager.is_running}


@router.post("/avatar/audio-level")
async def set_audio_level(level: float, speaking: bool = True):
    manager = get_easyvtuber_manager()
    manager.set_audio_level(level)
    manager.set_speaking(speaking)
    return {"success": True}


@router.websocket("/avatar/input")
async def avatar_input_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("Avatar input WebSocket 连接成功")

    manager = get_easyvtuber_manager()
    playback = get_playback_coordinator()
    client_id = uuid.uuid4().hex
    send_lock = asyncio.Lock()

    async def send_message(message: dict) -> None:
        async with send_lock:
            await websocket.send_json(message)

    await playback.register(client_id, send_message)

    try:
        while True:
            data = await websocket.receive_json()

            msg_type = data.get("type")

            if msg_type == "mouse":
                x = data.get("x", 0.5)
                y = data.get("y", 0.5)
                manager.set_mouse_position(x, y)

            elif msg_type == "playback_ready":
                await playback.set_ready(client_id, bool(data.get("ready", False)))

            elif msg_type == "playback_ack":
                await playback.acknowledge(
                    client_id,
                    str(data.get("reply_id", "")),
                    str(data.get("status", "")),
                    str(data.get("error", "")),
                )

            elif msg_type == "audio":
                if playback.owner_id != client_id:
                    continue
                level = data.get("level", 0.0)
                speaking = data.get("speaking", False)
                logger.debug(f"收到音频数据: level={level:.3f}, speaking={speaking}")
                manager.set_audio_level(level)
                manager.set_speaking(speaking)

            elif msg_type == "speaking":
                if playback.owner_id != client_id:
                    continue
                speaking = data.get("speaking", False)
                logger.debug(f"收到speaking状态: {speaking}")
                manager.set_speaking(speaking)

    except WebSocketDisconnect:
        logger.info("Avatar input WebSocket 断开")
    except Exception as e:
        logger.error(f"Avatar input WebSocket 错误: {e}")
    finally:
        await playback.disconnect(client_id)
        if playback.owner_id is None:
            manager.set_audio_level(0.0)
            manager.set_speaking(False)
