"""B站弹幕 WebSocket 路由"""

import asyncio
import base64
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.bilibili.client import BilibiliClient
from apps.ai.host_brain import get_host_brain
from apps.config import config
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

            if msg_type == "danmaku" and hasattr(data, "content"):
                from apps.music.service import get_danmaku_service
                music_service = get_danmaku_service()
                music_result = await music_service.process_danmaku(data.content, data.user)
                if music_result.isMusicRequest:
                    if music_result.musicItem:
                        try:
                            await manager.send_message(room_id, {
                                "type": "music_added",
                                "data": {
                                    "user": data.user,
                                    "title": music_result.musicItem.title,
                                    "artist": music_result.musicItem.upName,
                                }
                            })
                        except Exception as e:
                            logger.error(f"Failed to send music added: {e}")
                    elif music_result.error:
                        try:
                            await manager.send_message(room_id, {
                                "type": "music_error",
                                "data": {
                                    "user": data.user,
                                    "content": data.content,
                                    "error": music_result.error,
                                }
                            })
                        except Exception as e:
                            logger.error(f"Failed to send music error: {e}")
                    return

                brain = get_host_brain(config.default_room_id)
                accepted = brain.push_danmaku(
                    msg_id=str(data.id) if hasattr(data, "id") else f"bilibili_{data.uid}_{data.timestamp}",
                    user=data.user,
                    content=data.content,
                    uid=data.uid or 0
                )
                if accepted:
                    asyncio.create_task(_process_ai_reply(room_id))

        async def _process_ai_reply(room_id: str):
            brain = get_host_brain(config.default_room_id)
            reply = await brain.try_reply()
            if reply:
                try:
                    await manager.send_message(room_id, {
                        "type": "start",
                        "data": {}
                    })
                    await manager.send_message(room_id, {
                        "type": "text",
                        "data": {"text": reply.text}
                    })
                    if reply.audio and reply.audio.audio_data:
                        audio_base64 = base64.b64encode(reply.audio.audio_data).decode("utf-8")
                        await manager.send_message(room_id, {
                            "type": "audio",
                            "data": {
                                "audio": audio_base64,
                                "text": reply.text,
                                "sentence_index": 0,
                                "char_offset": 0,
                                "char_length": len(reply.text),
                            }
                        })
                    await manager.send_message(room_id, {
                        "type": "end",
                        "data": {"text": reply.text}
                    })
                except Exception as e:
                    logger.error(f"Failed to send AI reply: {e}")

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
