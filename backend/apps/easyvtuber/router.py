"""虚拟形象输入控制路由"""

import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from . import get_easyvtuber_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/avatar/input")
async def avatar_input_websocket(websocket: WebSocket):
    await websocket.accept()
    logger.info("Avatar input WebSocket 连接成功")
    
    manager = get_easyvtuber_manager()
    
    try:
        while True:
            data = await websocket.receive_json()
            
            msg_type = data.get("type")
            
            if msg_type == "mouse":
                x = data.get("x", 0.5)
                y = data.get("y", 0.5)
                manager.set_mouse_position(x, y)
            
            elif msg_type == "audio":
                level = data.get("level", 0.0)
                speaking = data.get("speaking", False)
                logger.debug(f"收到音频数据: level={level:.3f}, speaking={speaking}")
                manager.set_audio_level(level)
                manager.set_speaking(speaking)
            
            elif msg_type == "speaking":
                speaking = data.get("speaking", False)
                logger.debug(f"收到speaking状态: {speaking}")
                manager.set_speaking(speaking)
    
    except WebSocketDisconnect:
        logger.info("Avatar input WebSocket 断开")
    except Exception as e:
        logger.error(f"Avatar input WebSocket 错误: {e}")
