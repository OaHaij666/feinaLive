"""游戏集成路由 - 手动控制 GameGraph 启停"""

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.ai.game_manager import get_game_manager
from apps.ai.mcp.games.registry import create_mcp_game, list_registered_games
from apps.ai.memory.engine import get_memory_engine
from apps.ai.memory.game_memory import GameMemoryPolicy
from apps.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game", tags=["game"])


class GameStartRequest(BaseModel):
    mcp_url: str = ""
    game_id: str = ""
    game_config: dict[str, Any] = Field(default_factory=dict)


class GameScopeRequest(BaseModel):
    game_id: str


class GameSessionOpenRequest(BaseModel):
    external_session_id: str | None = None
    policy: dict[str, Any] | None = None


class GameEventRequest(BaseModel):
    event_type: str = "mcp_event"
    tool_name: str = "external"
    arguments: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    success: bool = True
    external_event_id: str | None = None


class WorkingMemoryRequest(BaseModel):
    layer: Literal["core", "important", "recent"]
    content: str
    source: str = "external"


class CheckpointRequest(BaseModel):
    force: bool = False


class GameSessionCloseRequest(BaseModel):
    reason: str = "external"
    final_event: dict[str, Any] | None = None


@router.get("/status")
async def get_game_status():
    manager = get_game_manager()
    return manager.get_game_status()


@router.get("/catalog")
async def get_game_catalog():
    return {"selected_game_id": config.game_id, "games": list_registered_games()}


@router.get("/health")
async def check_mcp_health():
    url = config.game_mcp_url
    try:
        adapter = create_mcp_game(
            config.game_id,
            mcp_url=url,
            game_config=config.game_config,
        )
        healthy = await adapter.health_check()
        return {
            "mcp_url": url,
            "healthy": healthy,
        }
    except Exception as e:
        return {
            "mcp_url": url,
            "healthy": False,
            "error": str(e),
        }


@router.post("/start")
async def start_game(request: GameStartRequest | None = None):
    manager = get_game_manager()

    if manager.is_running:
        return {"success": False, "message": "游戏已在运行中", "status": manager.get_game_status()}

    mcp_url = request.mcp_url if request and request.mcp_url else config.game_mcp_url

    game_id = request.game_id if request and request.game_id else config.game_id
    game_config = (
        request.game_config
        if request and request.game_config
        else config.game_config
    )
    try:
        adapter = create_mcp_game(
            game_id,
            mcp_url=mcp_url,
            game_config=game_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    healthy = await adapter.health_check()
    if not healthy:
        return {
            "success": False,
            "message": f"MCP 服务不可用: {mcp_url}",
            "status": manager.get_game_status(),
        }

    manager.configure_single_game(adapter)
    await manager.start()
    return {"success": True, "message": "游戏集成已启动", "status": manager.get_game_status()}


@router.post("/stop")
async def stop_game():
    manager = get_game_manager()
    if not manager.is_running:
        return {"success": False, "message": "游戏未在运行"}
    await manager.stop()
    return {"success": True, "message": "游戏集成已停止", "status": manager.get_game_status()}


@router.get("/context")
async def get_shared_context():
    from apps.ai.shared_context import get_shared_context

    ctx = get_shared_context()
    return await ctx.get_context_summary()


@router.get("/memory/scopes")
async def list_game_memory_scopes():
    engine = get_memory_engine()
    return {
        "selected_game_id": engine.selected_game_id,
        "games": await engine.list_game_scopes(),
    }


@router.post("/memory/select")
async def select_game_memory_scope(request: GameScopeRequest):
    return await get_memory_engine().select_game(request.game_id)


@router.post("/memory/{game_id}/sessions/open")
async def open_game_memory_session(game_id: str, request: GameSessionOpenRequest):
    try:
        policy = GameMemoryPolicy(**request.policy) if request.policy else None
        return await get_memory_engine().open_game_session(
            game_id,
            external_session_id=request.external_session_id,
            policy=policy,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/memory/{game_id}/events")
async def record_game_memory_event(game_id: str, request: GameEventRequest):
    event = await get_memory_engine().record_mcp_event(
        game_id,
        event_type=request.event_type,
        tool_name=request.tool_name,
        arguments=request.arguments,
        result=request.result,
        success=request.success,
        external_event_id=request.external_event_id,
    )
    return {"success": True, "event_id": event.event_id if event else None}


@router.put("/memory/{game_id}/working-memory")
async def update_game_working_memory(game_id: str, request: WorkingMemoryRequest):
    await get_memory_engine().update_working_memory(
        game_id,
        request.layer,
        request.content,
        source=request.source,
    )
    return {"success": True}


@router.get("/memory/{game_id}/context")
async def get_game_memory_context(game_id: str, query: str = ""):
    return (await get_memory_engine().get_game_memory_context(game_id, query)).to_dict()


@router.get("/memory/{game_id}/status")
async def get_game_memory_status(game_id: str):
    return await get_memory_engine().get_game_session_status(game_id)


@router.post("/memory/{game_id}/checkpoint")
async def checkpoint_game_memory(game_id: str, request: CheckpointRequest):
    summarized = await get_memory_engine().summarize_session_memory(
        game_id=game_id,
        force=request.force,
    )
    return {"success": True, "summarized": summarized}


@router.post("/memory/{game_id}/sessions/close")
async def close_game_memory_session(game_id: str, request: GameSessionCloseRequest):
    return await get_memory_engine().close_game_session(
        game_id,
        reason=request.reason,
        final_event=request.final_event,
    )


@router.post("/mute")
async def mute_queue():
    manager = get_game_manager()
    manager.mute()
    return {"success": True, "muted": True}


@router.post("/unmute")
async def unmute_queue():
    manager = get_game_manager()
    manager.unmute()
    return {"success": True, "muted": False}


@router.get("/queue")
async def get_queue_stats():
    from apps.ai.messaging.queue import get_message_queue

    queue = get_message_queue()
    return queue.get_stats()
