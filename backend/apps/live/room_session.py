"""Owns the single active Bilibili room session for the whole application."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Protocol

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RoomSessionContext:
    """Routing identity carried from ingestion through queue consumption."""

    room_id: str
    session_id: str
    generation: int
    is_test: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "session_id": self.session_id,
            "generation": self.generation,
            "is_test": self.is_test,
        }

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> RoomSessionContext | None:
        if not value:
            return None
        try:
            return cls(
                room_id=str(value["room_id"]),
                session_id=str(value["session_id"]),
                generation=int(value["generation"]),
                is_test=bool(value.get("is_test", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @classmethod
    def test_room(cls) -> RoomSessionContext:
        return cls(room_id="test_room", session_id="test_room", generation=0, is_test=True)


class RoomClient(Protocol):
    is_running: bool

    def set_callback(self, callback: Callable[[str, Any], Awaitable[None]]) -> None: ...

    async def connect(self) -> None: ...

    async def close(self) -> None: ...


RoomEventHandler = Callable[[RoomSessionContext, str, Any], Awaitable[None]]
RoomClientFactory = Callable[[int], RoomClient]


def _default_client_factory(room_id: int) -> RoomClient:
    from apps.live.bilibili.client import BilibiliClient

    return BilibiliClient(room_id)


class LiveRoomSessionManager:
    """Serializes room switches and rejects events from superseded sessions."""

    def __init__(self, client_factory: RoomClientFactory | None = None):
        self._client_factory = client_factory or _default_client_factory
        self._lock = asyncio.Lock()
        self._active: RoomSessionContext | None = None
        self._client: RoomClient | None = None
        self._generation = 0
        self._event_handler: RoomEventHandler | None = None

    @property
    def active_context(self) -> RoomSessionContext | None:
        return self._active

    @property
    def active_room_id(self) -> str | None:
        return self._active.room_id if self._active else None

    def set_event_handler(self, handler: RoomEventHandler) -> None:
        self._event_handler = handler

    def is_current(self, context: RoomSessionContext) -> bool:
        return context.is_test or context == self._active

    async def activate(self, room_id: str | int) -> RoomSessionContext:
        normalized = str(room_id).strip()
        if not normalized.isdigit() or int(normalized) <= 0:
            raise ValueError("room_id must be a positive integer")

        async with self._lock:
            if (
                self._active is not None
                and self._active.room_id == normalized
                and self._client is not None
                and self._client.is_running
            ):
                return self._active

            old_context = self._active
            old_client = self._client
            # Invalidate first. Any callback racing with close() is now stale.
            self._active = None
            self._client = None
            if old_client is not None:
                await old_client.close()
                logger.info("Stopped superseded Bilibili room session %s", old_context)

            self._generation += 1
            context = RoomSessionContext(
                room_id=normalized,
                session_id=uuid.uuid4().hex,
                generation=self._generation,
            )
            client = self._client_factory(int(normalized))

            async def on_event(msg_type: str, data: Any) -> None:
                await self._dispatch(context, msg_type, data)

            client.set_callback(on_event)
            self._active = context
            self._client = client
            try:
                await client.connect()
            except Exception:
                self._active = None
                self._client = None
                await client.close()
                raise

            logger.info(
                "Activated Bilibili room %s (session=%s generation=%s)",
                context.room_id,
                context.session_id,
                context.generation,
            )
            return context

    async def stop(self) -> None:
        async with self._lock:
            client = self._client
            context = self._active
            self._active = None
            self._client = None
            if client is not None:
                await client.close()
            if context is not None:
                logger.info("Stopped active Bilibili room session %s", context)

    async def _dispatch(
        self,
        context: RoomSessionContext,
        msg_type: str,
        data: Any,
    ) -> None:
        if not self.is_current(context):
            logger.debug(
                "Dropped stale Bilibili event room=%s session=%s type=%s",
                context.room_id,
                context.session_id,
                msg_type,
            )
            return
        if self._event_handler is not None:
            await self._event_handler(context, msg_type, data)


_room_session_manager: LiveRoomSessionManager | None = None


def get_room_session_manager() -> LiveRoomSessionManager:
    global _room_session_manager
    if _room_session_manager is None:
        _room_session_manager = LiveRoomSessionManager()
    return _room_session_manager


def reset_room_session_manager(
    manager: LiveRoomSessionManager | None = None,
) -> LiveRoomSessionManager:
    """Replace the singleton for isolated tests."""

    global _room_session_manager
    _room_session_manager = manager or LiveRoomSessionManager()
    return _room_session_manager
