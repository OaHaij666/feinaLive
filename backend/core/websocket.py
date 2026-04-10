"""WebSocket 连接管理器"""

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, WebSocket] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def get_lock(self, room_id: str) -> asyncio.Lock:
        if room_id not in self._locks:
            self._locks[room_id] = asyncio.Lock()
        return self._locks[room_id]

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        async with self.get_lock(room_id):
            self._connections[room_id] = websocket
        logger.info(f"Client connected to room {room_id}")

    async def disconnect(self, room_id: str):
        async with self.get_lock(room_id):
            if room_id in self._connections:
                del self._connections[room_id]
        logger.info(f"Client disconnected from room {room_id}")

    async def send_message(self, room_id: str, message: dict[str, Any]):
        async with self.get_lock(room_id):
            if room_id in self._connections:
                websocket = self._connections[room_id]
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Failed to send message: {e}")
                    raise

    async def broadcast(self, room_id: str, message: dict[str, Any]):
        await self.send_message(room_id, message)


manager = ConnectionManager()
