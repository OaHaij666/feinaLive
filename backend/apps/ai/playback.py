"""Authoritative browser playback lease and acknowledgement coordination."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MessageSender = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class PlaybackSession:
    reply_id: str
    owner_id: str
    status: str = "buffering"
    error: str = ""
    event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class PlaybackCoordinator:
    """Elect one renderer and wait for its real audio playback completion."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._clients: dict[str, MessageSender] = {}
        self._ready: list[str] = []
        self._owner_id: str | None = None
        self._sessions: dict[str, PlaybackSession] = {}

    @property
    def owner_id(self) -> str | None:
        return self._owner_id

    async def register(self, client_id: str, send_message: MessageSender) -> None:
        async with self._lock:
            self._clients[client_id] = send_message
            is_owner = client_id == self._owner_id
        await self._safe_send(
            send_message,
            {"type": "playback_role", "is_owner": is_owner},
        )

    async def set_ready(self, client_id: str, ready: bool) -> bool:
        notifications: list[tuple[MessageSender, bool]] = []
        async with self._lock:
            if client_id not in self._clients:
                return False
            if ready:
                if client_id not in self._ready:
                    self._ready.append(client_id)
            elif client_id in self._ready:
                self._ready.remove(client_id)

            if not ready and self._owner_id == client_id:
                self._fail_owner_sessions_locked(client_id, "playback owner became unavailable")
                self._owner_id = None

            if self._owner_id is None:
                self._owner_id = next(
                    (candidate for candidate in self._ready if candidate in self._clients),
                    None,
                )

            notifications = [
                (notifier, candidate == self._owner_id)
                for candidate, notifier in self._clients.items()
            ]
            is_owner = client_id == self._owner_id

        await asyncio.gather(
            *(
                self._safe_send(
                    sender,
                    {"type": "playback_role", "is_owner": owner},
                )
                for sender, owner in notifications
            )
        )
        return is_owner

    async def disconnect(self, client_id: str) -> None:
        notifications: list[tuple[MessageSender, bool]] = []
        async with self._lock:
            self._clients.pop(client_id, None)
            if client_id in self._ready:
                self._ready.remove(client_id)
            if self._owner_id == client_id:
                self._fail_owner_sessions_locked(client_id, "playback owner disconnected")
                self._owner_id = next(
                    (candidate for candidate in self._ready if candidate in self._clients),
                    None,
                )
                notifications = [
                    (notifier, candidate == self._owner_id)
                    for candidate, notifier in self._clients.items()
                ]
        await asyncio.gather(
            *(
                self._safe_send(
                    sender,
                    {"type": "playback_role", "is_owner": owner},
                )
                for sender, owner in notifications
            )
        )

    async def begin(self, reply_id: str) -> PlaybackSession | None:
        async with self._lock:
            owner_id = self._owner_id
            if owner_id is None or owner_id not in self._clients:
                return None
            session = PlaybackSession(reply_id=reply_id, owner_id=owner_id)
            self._sessions[reply_id] = session
            return session

    async def acknowledge(
        self,
        client_id: str,
        reply_id: str,
        status: str,
        error: str = "",
    ) -> bool:
        if status not in {"started", "finished", "failed"}:
            return False
        async with self._lock:
            session = self._sessions.get(reply_id)
            if session is None or session.owner_id != client_id:
                return False
            if session.status in {"finished", "failed", "timeout"}:
                return False
            session.status = status
            session.error = error
            if status in {"finished", "failed"}:
                session.event.set()
            return True

    async def send_chunk(self, reply_id: str, chunk: dict[str, Any]) -> bool:
        async with self._lock:
            session = self._sessions.get(reply_id)
            sender = self._clients.get(session.owner_id) if session else None
        if session is None or sender is None:
            return False
        try:
            await sender(chunk)
            return True
        except Exception as exc:
            logger.warning("Playback delivery failed for reply %s: %s", reply_id, exc)
            await self.abort(reply_id, f"playback delivery failed: {exc}")
            return False

    async def wait_for_completion(self, reply_id: str, timeout: float) -> PlaybackSession:
        async with self._lock:
            session = self._sessions.get(reply_id)
            if session is None:
                return PlaybackSession(
                    reply_id=reply_id,
                    owner_id="",
                    status="no_owner",
                    error="no ready playback owner",
                )
            event = session.event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            async with self._lock:
                session.status = "timeout"
                session.error = "browser playback acknowledgement timed out"
        finally:
            async with self._lock:
                self._sessions.pop(reply_id, None)
        return session

    async def abort(self, reply_id: str, error: str) -> PlaybackSession | None:
        async with self._lock:
            session = self._sessions.pop(reply_id, None)
            if session is None:
                return None
            if session.status not in {"finished", "failed", "timeout"}:
                session.status = "failed"
                session.error = error
                session.event.set()
            return session

    def _fail_owner_sessions_locked(self, owner_id: str, error: str) -> None:
        for session in self._sessions.values():
            if session.owner_id == owner_id and session.status not in {
                "finished",
                "failed",
                "timeout",
            }:
                session.status = "failed"
                session.error = error
                session.event.set()

    @staticmethod
    async def _safe_send(sender: MessageSender, message: dict[str, Any]) -> None:
        try:
            await sender(message)
        except Exception as exc:
            logger.debug("Failed to send playback control message: %s", exc)

    async def get_status(self) -> dict[str, Any]:
        async with self._lock:
            return {
                "owner_id": self._owner_id,
                "ready_clients": len(self._ready),
                "active_replies": len(self._sessions),
            }


_playback_coordinator: PlaybackCoordinator | None = None


def get_playback_coordinator() -> PlaybackCoordinator:
    global _playback_coordinator
    if _playback_coordinator is None:
        _playback_coordinator = PlaybackCoordinator()
    return _playback_coordinator


def reset_playback_coordinator(
    coordinator: PlaybackCoordinator | None = None,
) -> PlaybackCoordinator:
    global _playback_coordinator
    _playback_coordinator = coordinator or PlaybackCoordinator()
    return _playback_coordinator
