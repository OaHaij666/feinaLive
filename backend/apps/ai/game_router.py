"""游戏集成路由 - 手动控制 GameGraph 启停"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from apps.ai.mcp.adapters.slay_the_spire import SlayTheSpireAdapter
from apps.ai.game_manager import get_game_manager
from apps.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game", tags=["game"])


class GameStartRequest(BaseModel):
    mcp_url: str = ""


@router.get("/status")
async def get_game_status():
    manager = get_game_manager()
    return manager.get_game_status()


@router.get("/health")
async def check_mcp_health():
    url = config.game_mcp_url
    try:
        adapter = SlayTheSpireAdapter(base_url=url)
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

    adapter = SlayTheSpireAdapter(base_url=mcp_url)
    healthy = await adapter.health_check()
    if not healthy:
        return {
            "success": False,
            "message": f"MCP 服务不可用: {mcp_url}",
            "status": manager.get_game_status(),
        }

    manager.register_game(adapter)
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
