"""AI主播对话路由"""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from apps.ai.host_brain import get_host_brain
from apps.config import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])


class ReplyRequest(BaseModel):
    user: str = "user"
    content: str = ""


@router.post("/reply")
async def reply(request: ReplyRequest):
    """流式返回AI主播回复

    使用 Server-Sent Events (SSE) 格式返回流式数据
    """
    user = request.user
    content = request.content

    if not content:
        return {"error": "内容不能为空"}

    brain = get_host_brain(config.default_room_id)

    async def generate():
        try:
            async for chunk in brain.stream_reply(user, content):
                data = chunk.to_dict()
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.error(f"Stream reply error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'text': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/status")
async def get_status():
    """获取AI主播状态"""
    brain = get_host_brain(config.default_room_id)
    return {
        "is_replying": brain.is_replying,
        "buffer_size": brain.buffer_size,
        "unanswered_count": brain.unanswered_count,
    }
