"""AI主播状态与管理员控制路由。"""

from fastapi import APIRouter
from pydantic import BaseModel

from apps.ai.admin_commands import get_admin_handler
from apps.ai.host_brain import get_host_brain
from apps.ai.playback import get_playback_coordinator
from apps.config import config

router = APIRouter(prefix="/ai", tags=["ai"])


class AdminCommandRequest(BaseModel):
    command: str = ""


@router.get("/status")
async def get_status():
    """获取弹幕缓冲与待消费状态。"""
    brain = get_host_brain()
    return {
        "buffer_size": brain.buffer_size,
        "unanswered_count": brain.unanswered_count,
        "playback": await get_playback_coordinator().get_status(),
    }


@router.post("/admin/command")
async def send_admin_command(request: AdminCommandRequest):
    """发送管理员指令（用于测试）"""
    handler = get_admin_handler()
    raw_id = config.admin_identities.get(config.live_platform, "internal")
    result = await handler.handle(
        f"{config.live_platform}:{raw_id}", config.admin_username, request.command
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "非管理员或无效指令"}


@router.get("/admin/state")
async def get_admin_state():
    """Return the canonical runtime control state for the operator console."""

    return get_admin_handler().get_state_dict()
