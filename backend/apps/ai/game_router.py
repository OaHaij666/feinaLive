"""游戏集成路由"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from apps.ai.game_manager import get_game_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/game", tags=["game"])


class GameStartRequest(BaseModel):
    game_id: str = ""
    mcp_url: str = ""


@router.get("/status")
async def get_game_status():
    manager = get_game_manager()
    return manager.get_game_status()


@router.post("/start")
async def start_game(request: GameStartRequest | None = None):
    """启动游戏集成

    需要先注册游戏适配器，示例:
        from apps.ai.mcp.adapters import MyGameAdapter
        adapter = MyGameAdapter(mcp_url="http://...")
        manager.register_game(adapter)
        await manager.start()
    """
    manager = get_game_manager()
    await manager.start()
    return {"success": True, "status": manager.get_game_status()}


@router.post("/stop")
async def stop_game():
    manager = get_game_manager()
    await manager.stop()
    return {"success": True, "status": manager.get_game_status()}


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
