from __future__ import annotations

from urllib.parse import urljoin, urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from apps.config import config
from apps.music.manager import get_music_manager
from apps.music.models import MusicRequest, MusicRequestResult, MusicState, PlaybackEventType
from apps.music.runtime import MusicQueueError

router = APIRouter(prefix="/music", tags=["music"])


class SubmitRequest(BaseModel):
    query: str
    requested_by: str = "admin"
    provider: str | None = None
    source_id: str | None = None


class PauseRequest(BaseModel):
    paused: bool


class VolumeRequest(BaseModel):
    volume: float = Field(ge=0.0, le=1.0)


class PlayerRequest(BaseModel):
    player_id: str = Field(min_length=8, max_length=100)


class PlaybackEventRequest(PlayerRequest):
    entry_id: str
    event: PlaybackEventType
    reason: str = ""


@router.get("/state", response_model=MusicState)
async def get_state() -> MusicState:
    return await get_music_manager().state()


@router.get("/providers")
async def providers() -> dict[str, list[str]]:
    return {"providers": await get_music_manager().list_providers()}


@router.post("/requests", response_model=MusicRequestResult)
async def submit_request(body: SubmitRequest) -> MusicRequestResult:
    return await get_music_manager().submit(
        MusicRequest(
            query=body.query,
            requested_by=body.requested_by,
            provider=body.provider or config.music_default_provider,
            direct_source_id=body.source_id,
        )
    )


@router.post("/commands/skip", response_model=MusicState)
async def skip(remove_from_library: bool = False) -> MusicState:
    return await get_music_manager().skip(remove_from_library=remove_from_library)


@router.post("/commands/pause", response_model=MusicState)
async def pause(body: PauseRequest) -> MusicState:
    return await get_music_manager().set_paused(body.paused)


@router.post("/commands/volume", response_model=MusicState)
async def volume(body: VolumeRequest) -> MusicState:
    return await get_music_manager().set_volume(body.volume)


@router.delete("/queue/{entry_id}")
async def remove_queue_entry(entry_id: str) -> dict[str, bool]:
    removed = await get_music_manager().remove_queue_entry(entry_id)
    if not removed:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    return {"removed": True}


@router.delete("/queue")
async def clear_queue() -> dict[str, int]:
    return {"removed": await get_music_manager().clear_queue()}


@router.get("/library")
async def library():
    return {"items": await get_music_manager().list_library()}


@router.get("/history")
async def history(limit: int = Query(default=100, ge=1, le=500)):
    return {"items": await get_music_manager().history(limit)}


@router.post("/library/{provider}/{source_id}")
async def add_library(provider: str, source_id: str):
    try:
        return await get_music_manager().add_library(provider, source_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/library/{track_id}")
async def set_library_enabled(track_id: str, enabled: bool = True):
    if not await get_music_manager().set_library_enabled(track_id, enabled):
        raise HTTPException(status_code=404, detail="Library track not found")
    return {"enabled": enabled}


@router.post("/player/claim")
async def claim_player(body: PlayerRequest) -> dict[str, bool]:
    manager = get_music_manager()
    await manager.initialize()
    return {"claimed": await manager.runtime.claim_player(body.player_id)}


@router.post("/player/heartbeat")
async def heartbeat_player(body: PlayerRequest) -> dict[str, bool]:
    manager = get_music_manager()
    await manager.initialize()
    return {"active": await manager.runtime.heartbeat_player(body.player_id)}


@router.post("/player/release", status_code=204)
async def release_player(body: PlayerRequest) -> Response:
    manager = get_music_manager()
    await manager.initialize()
    await manager.runtime.release_player(body.player_id)
    return Response(status_code=204)


@router.post("/playback/events", response_model=MusicState)
async def playback_event(body: PlaybackEventRequest) -> MusicState:
    try:
        return await get_music_manager().playback_event(
            player_id=body.player_id,
            entry_id=body.entry_id,
            event=body.event,
            reason=body.reason,
        )
    except MusicQueueError as exc:
        raise HTTPException(status_code=409, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/stream/{entry_id}")
async def stream_audio(
    entry_id: str,
    request: Request,
    player_id: str = Query(min_length=8, max_length=100),
):
    try:
        stream = await get_music_manager().resolve_current_stream(entry_id, player_id)
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = dict(stream.headers)
    if range_header := request.headers.get("range"):
        headers["Range"] = range_header
    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None), follow_redirects=False)
    upstream = None
    target_url = stream.url
    for _ in range(4):
        try:
            _validate_proxy_target(target_url, stream.allowed_host_suffixes)
        except HTTPException:
            await client.aclose()
            raise
        upstream_request = client.build_request("GET", target_url, headers=headers)
        upstream = await client.send(upstream_request, stream=True)
        if upstream.status_code not in {301, 302, 303, 307, 308}:
            break
        location = upstream.headers.get("location")
        await upstream.aclose()
        if not location:
            break
        target_url = urljoin(target_url, location)
    if upstream is None:
        await client.aclose()
        raise HTTPException(status_code=502, detail="Music source did not respond")
    if upstream.status_code in {301, 302, 303, 307, 308}:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail="Music source redirected too many times")
    if upstream.status_code >= 400:
        await upstream.aclose()
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Music source returned {upstream.status_code}")
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() in {"accept-ranges", "content-length", "content-range", "etag", "last-modified"}
    }
    response_headers["Cache-Control"] = "no-store"

    async def close_upstream() -> None:
        await upstream.aclose()
        await client.aclose()

    return StreamingResponse(
        upstream.aiter_raw(),
        status_code=upstream.status_code,
        media_type=upstream.headers.get("content-type", stream.media_type),
        headers=response_headers,
        background=BackgroundTask(close_upstream),
    )


def _validate_proxy_target(url: str, allowed_suffixes: list[str]) -> None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    allowed = any(host == suffix or host.endswith(f".{suffix}") for suffix in allowed_suffixes)
    if parsed.scheme != "https" or not allowed:
        raise HTTPException(status_code=502, detail="Music provider returned an unsafe stream URL")
