"""WebSocket 连接管理器"""

import asyncio
import logging
import uuid
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, dict[str, WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, room_id: str) -> str:
        await websocket.accept()
        connection_id = uuid.uuid4().hex
        async with self._lock:
            self._connections.setdefault(room_id, {})[connection_id] = websocket
        logger.info("Client %s connected to room %s", connection_id, room_id)
        return connection_id

    async def disconnect(self, room_id: str, connection_id: str):
        async with self._lock:
            room_connections = self._connections.get(room_id)
            if room_connections is not None:
                room_connections.pop(connection_id, None)
                if not room_connections:
                    self._connections.pop(room_id, None)
        logger.info("Client %s disconnected from room %s", connection_id, room_id)

    async def disconnect_other_rooms(self, active_room_id: str) -> None:
        async with self._lock:
            stale = [
                (room_id, connection_id, websocket)
                for room_id, connections in self._connections.items()
                if room_id not in {active_room_id, "test_room"}
                for connection_id, websocket in connections.items()
            ]
            for room_id, connection_id, _ in stale:
                self._connections[room_id].pop(connection_id, None)
                if not self._connections[room_id]:
                    self._connections.pop(room_id, None)
        for room_id, connection_id, websocket in stale:
            try:
                await websocket.close(code=1000, reason="active room changed")
            except Exception:
                pass
            logger.info("Closed stale client %s for room %s", connection_id, room_id)

    async def send_message(self, room_id: str, message: dict[str, Any]):
        async with self._lock:
            connections = list(self._connections.get(room_id, {}).items())

        failed: list[str] = []
        for connection_id, websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    "Failed to send message to room=%s connection=%s: %s",
                    room_id,
                    connection_id,
                    e,
                )
                failed.append(connection_id)

        for connection_id in failed:
            await self.disconnect(room_id, connection_id)

    async def broadcast(self, room_id: str, message: dict[str, Any]):
        await self.send_message(room_id, message)

    async def connection_count(self, room_id: str) -> int:
        async with self._lock:
            return len(self._connections.get(room_id, {}))


manager = ConnectionManager()
