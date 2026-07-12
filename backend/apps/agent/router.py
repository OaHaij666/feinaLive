"""Agent runtime, scenario catalog, and scenario-memory API."""

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.agent.manager import get_agent_manager
from apps.agent.mutual_context import get_mutual_context
from apps.agent.scenarios.registry import list_scenarios
from apps.ai.memory.engine import get_memory_engine
from apps.ai.memory.game_memory import GameMemoryPolicy
from apps.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentStartRequest(BaseModel):
    mcp_url: str = ""
    scenario_id: str = ""
    scenario_config: dict[str, Any] = Field(default_factory=dict)


class AgentEventRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    source: str = Field(default="external", min_length=1, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class GameMemoryScopeRequest(BaseModel):
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
async def get_agent_status():
    return await get_agent_manager().get_status()


@router.get("/catalog")
async def get_scenario_catalog():
    return {
        "selected_scenario_id": config.agent_scenario_id,
        "scenarios": list_scenarios(),
        "restart_required": get_agent_manager().needs_restart,
    }


@router.get("/health")
async def check_agent_health():
    manager = get_agent_manager()
    try:
        healthy = await manager.health_check()
        return {
            "mcp_url": manager.startup_config.get("mcp_url", ""),
            "healthy": healthy,
            "restart_required": manager.needs_restart,
        }
    except Exception as e:
        return {
            "mcp_url": manager.startup_config.get("mcp_url", ""),
            "healthy": False,
            "error": str(e),
        }


@router.post("/start")
async def start_agent(request: AgentStartRequest | None = None):
    manager = get_agent_manager()

    if manager.is_running:
        return {
            "success": False,
            "message": "Agent 已在运行中",
            "status": await manager.get_status(),
        }

    startup = manager.startup_config
    requested = {
        "scenario_id": request.scenario_id if request and request.scenario_id else startup.get("scenario_id"),
        "mcp_url": request.mcp_url if request and request.mcp_url else startup.get("mcp_url"),
        "scenario_config": (
            request.scenario_config
            if request and request.scenario_config
            else startup.get("scenario_config", {})
        ),
    }
    if requested != startup or manager.needs_restart:
        return {
            "success": False,
            "restart_required": True,
            "message": "场景、MCP 与能力配置只在进程启动时绑定；请重启应用后生效",
            "status": await manager.get_status(),
        }
    healthy = await manager.health_check()
    if not healthy:
        return {
            "success": False,
            "message": f"启动场景能力不可用: {startup.get('mcp_url', '')}",
            "status": await manager.get_status(),
        }

    await manager.start()
    return {"success": True, "message": "Agent 已启动", "status": await manager.get_status()}


@router.post("/stop")
async def stop_agent():
    manager = get_agent_manager()
    if not manager.is_running:
        return {"success": False, "message": "Agent 未在运行"}
    await manager.stop()
    return {"success": True, "message": "Agent 已停止", "status": await manager.get_status()}


@router.post("/events")
async def publish_agent_event(request: AgentEventRequest):
    event = await get_agent_manager().publish_event(
        request.event_type,
        request.source,
        request.payload,
    )
    return {
        "accepted": True,
        "event_id": event.event_id,
        "created_at": event.created_at,
    }


@router.get("/context")
async def get_shared_context():
    return {"mutual_context": await get_mutual_context().snapshot()}


@router.get("/memory/scopes")
async def list_game_memory_scopes():
    engine = get_memory_engine()
    return {
        "selected_game_id": engine.selected_game_id,
        "games": await engine.list_game_scopes(),
    }


@router.post("/memory/select")
async def select_game_memory_scope(request: GameMemoryScopeRequest):
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
    manager = get_agent_manager()
    manager.mute()
    return {"success": True, "muted": True}


@router.post("/unmute")
async def unmute_queue():
    manager = get_agent_manager()
    manager.unmute()
    return {"success": True, "muted": False}


@router.get("/queue")
async def get_queue_stats():
    from apps.ai.messaging.queue import get_message_queue

    queue = get_message_queue()
    return queue.get_stats()
