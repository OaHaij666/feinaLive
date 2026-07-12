"""AI主播状态与管理员控制路由。"""

from fastapi import APIRouter
from pydantic import BaseModel

from apps.ai.admin_commands import get_admin_handler
from apps.ai.host_brain import get_host_brain
from apps.config import config

router = APIRouter(prefix="/ai", tags=["ai"])


class AdminCommandRequest(BaseModel):
    command: str = ""


@router.get("/status")
async def get_status():
    """获取弹幕缓冲与待消费状态。"""
    brain = get_host_brain(config.default_room_id)
    return {
        "buffer_size": brain.buffer_size,
        "unanswered_count": brain.unanswered_count,
    }


@router.post("/admin/command")
async def send_admin_command(request: AdminCommandRequest):
    """发送管理员指令（用于测试）"""
    handler = get_admin_handler()
    result = await handler.handle(
        uid=config.admin_uid,
        username=config.admin_username,
        content=request.command
    )
    if result:
        return {
            "success": result.success,
            "message": result.message,
            "command": result.command,
            "state": result.new_state,
        }
    return {"success": False, "message": "非管理员或无效指令"}
