from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Response, WebSocket, WebSocketDisconnect

from apps.ai.playback import get_playback_coordinator

from .runtime import get_avatar_runtime

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/avatar", tags=["avatar"])


@router.post("/start")
async def start_avatar():
    runtime = get_avatar_runtime()
    await runtime.start()
    return runtime.status()


@router.post("/stop")
async def stop_avatar():
    runtime = get_avatar_runtime()
    await runtime.stop()
    return runtime.status()


@router.get("/status")
async def avatar_status():
    return get_avatar_runtime().status()


@router.get("/preview/frame")
async def avatar_preview_frame():
    frame = get_avatar_runtime().latest_preview()
    if frame is None:
        return Response(status_code=503)
    return Response(
        content=frame,
        media_type="image/webp",
        headers={"Cache-Control": "no-store"},
    )


@router.websocket("/control")
async def avatar_control_websocket(websocket: WebSocket):
    await websocket.accept()
    runtime = get_avatar_runtime()
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
            msg_type = str(data.get("type", ""))
            if msg_type == "playback_ready":
                await playback.set_ready(client_id, bool(data.get("ready", False)))
            elif msg_type == "playback_ack":
                reply_id = str(data.get("reply_id", ""))
                status = str(data.get("status", ""))
                accepted = await playback.acknowledge(
                    client_id,
                    reply_id,
                    status,
                    str(data.get("error", "")),
                )
                if accepted and status == "started":
                    runtime.begin_lip_sync(reply_id)
                elif accepted and status in {"finished", "failed"}:
                    runtime.end_lip_sync(reply_id)
            elif msg_type == "mouse" and playback.owner_id == client_id:
                runtime.set_mouse_position(
                    float(data.get("x", 0.5)),
                    float(data.get("y", 0.5)),
                )
            elif msg_type == "audio" and playback.owner_id == client_id:
                runtime.update_audio(
                    str(data.get("reply_id", "")),
                    int(data.get("seq", -1)),
                    float(data.get("audio_time_ms", -1.0)),
                    float(data.get("level", 0.0)),
                    bool(data.get("speaking", False)),
                )
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("Avatar control WebSocket failed")
    finally:
        was_owner = playback.owner_id == client_id
        await playback.disconnect(client_id)
        if was_owner:
            active_reply = runtime.status()["lip_sync"]["active_reply_id"]
            if active_reply:
                runtime.end_lip_sync(active_reply)
