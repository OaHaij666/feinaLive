from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable

from apps.music.models import (
    MusicState,
    PlaybackEventType,
    QueueEntry,
    QueueEntryStatus,
    Track,
    utc_now,
)
from apps.music.persistence.repository import MusicRepository

StateCallback = Callable[[MusicState], Awaitable[None]]
logger = logging.getLogger(__name__)


class MusicRuntime:
    def __init__(
        self,
        repository: MusicRepository,
        *,
        queue_capacity: int,
        per_user_limit: int,
        history_capacity: int = 100,
        owner_ttl_seconds: float = 20.0,
    ) -> None:
        self._repository = repository
        self._queue_capacity = queue_capacity
        self._per_user_limit = per_user_limit
        self._queue: deque[QueueEntry] = deque()
        self._current: QueueEntry | None = None
        self._history: deque[QueueEntry] = deque(maxlen=history_capacity)
        self._paused = False
        self._volume = 1.0
        self._ducking_factor = 1.0
        self._revision = 0
        self._lock = asyncio.Lock()
        self._callback: StateCallback | None = None
        self._owner_id: str | None = None
        self._owner_seen_at = 0.0
        self._owner_ttl_seconds = owner_ttl_seconds

    async def initialize(self) -> None:
        current, queue, paused, volume = await self._repository.load_runtime_state()
        history = await self._repository.load_history(limit=self._history.maxlen or 100)
        async with self._lock:
            self._current = current
            self._queue = deque(queue)
            self._paused = paused
            self._volume = volume
            self._history = deque(history, maxlen=self._history.maxlen)
            if self._current:
                self._current.status = (
                    QueueEntryStatus.PAUSED if paused else QueueEntryStatus.PLAYING
                )
            self._revision += 1

    def set_state_callback(self, callback: StateCallback) -> None:
        self._callback = callback

    async def enqueue(
        self, track: Track, *, requested_by: str, request_id: str = ""
    ) -> QueueEntry:
        async with self._lock:
            active = ([self._current] if self._current else []) + list(self._queue)
            if len(active) >= self._queue_capacity:
                raise MusicQueueError("QUEUE_FULL", "播放队列已满")
            user_count = sum(entry.requested_by == requested_by for entry in active)
            if user_count >= self._per_user_limit:
                raise MusicQueueError(
                    "USER_LIMIT_REACHED",
                    f"你已有 {user_count} 首歌在播放队列中",
                )
            if any(
                entry.track.provider == track.provider
                and entry.track.source_id == track.source_id
                for entry in active
            ):
                raise MusicQueueError("DUPLICATE_REQUEST", "这首歌已经在播放队列中")
            entry = QueueEntry(
                track=track,
                requested_by=requested_by,
                request_id=request_id,
            )
            if self._current is None:
                self._start_entry(entry)
                self._current = entry
            else:
                self._queue.append(entry)
            state = await self._commit_locked()
        await self._notify(state)
        return entry

    async def skip(self, *, failed: bool = False, reason: str = "") -> MusicState:
        async with self._lock:
            if self._current:
                await self._finish_current(
                    QueueEntryStatus.FAILED if failed else QueueEntryStatus.SKIPPED,
                    reason,
                )
            self._promote_next()
            state = await self._commit_locked()
        await self._notify(state)
        return state

    async def remove(self, entry_id: str) -> bool:
        async with self._lock:
            for entry in self._queue:
                if entry.id == entry_id:
                    self._queue.remove(entry)
                    entry.status = QueueEntryStatus.CANCELLED
                    entry.finished_at = utc_now()
                    self._history.append(entry)
                    await self._repository.append_history(entry)
                    state = await self._commit_locked()
                    break
            else:
                return False
        await self._notify(state)
        return True

    async def clear(self) -> int:
        async with self._lock:
            removed = len(self._queue)
            now = utc_now()
            while self._queue:
                entry = self._queue.popleft()
                entry.status = QueueEntryStatus.CANCELLED
                entry.finished_at = now
                self._history.append(entry)
                await self._repository.append_history(entry)
            state = await self._commit_locked()
        await self._notify(state)
        return removed

    async def set_paused(self, paused: bool) -> MusicState:
        async with self._lock:
            self._paused = paused
            if self._current:
                self._current.status = (
                    QueueEntryStatus.PAUSED if paused else QueueEntryStatus.PLAYING
                )
            state = await self._commit_locked()
        await self._notify(state)
        return state

    async def set_volume(self, volume: float) -> MusicState:
        async with self._lock:
            self._volume = max(0.0, min(1.0, volume))
            state = await self._commit_locked()
        await self._notify(state)
        return state

    async def set_ducking(self, factor: float) -> MusicState:
        async with self._lock:
            self._ducking_factor = max(0.0, min(1.0, factor))
            self._revision += 1
            state = self._snapshot_locked()
        await self._notify(state)
        return state

    async def claim_player(self, player_id: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            if (
                self._owner_id
                and self._owner_id != player_id
                and now - self._owner_seen_at <= self._owner_ttl_seconds
            ):
                return False
            changed = self._owner_id != player_id
            self._owner_id = player_id
            self._owner_seen_at = now
            if changed:
                self._revision += 1
            state = self._snapshot_locked()
        if changed:
            await self._notify(state)
        return True

    async def heartbeat_player(self, player_id: str) -> bool:
        async with self._lock:
            if not self._is_owner_locked(player_id):
                return False
            self._owner_seen_at = time.monotonic()
            return True

    async def release_player(self, player_id: str) -> None:
        async with self._lock:
            if self._owner_id != player_id:
                return
            self._owner_id = None
            self._owner_seen_at = 0.0
            self._revision += 1
            state = self._snapshot_locked()
        await self._notify(state)

    async def validate_player(self, player_id: str) -> bool:
        async with self._lock:
            return self._is_owner_locked(player_id)

    async def playback_event(
        self,
        *,
        player_id: str,
        entry_id: str,
        event: PlaybackEventType,
        reason: str = "",
    ) -> MusicState:
        async with self._lock:
            if not self._is_owner_locked(player_id):
                raise MusicQueueError("NOT_PLAYBACK_OWNER", "当前页面不是音乐播放端")
            self._owner_seen_at = time.monotonic()
            if self._current is None or self._current.id != entry_id:
                return self._snapshot_locked()
            if event == PlaybackEventType.STARTED:
                self._current.status = QueueEntryStatus.PLAYING
                self._current.started_at = self._current.started_at or utc_now()
            elif event == PlaybackEventType.PAUSED:
                self._current.status = QueueEntryStatus.PAUSED
            elif event == PlaybackEventType.RESUMED:
                self._current.status = QueueEntryStatus.PLAYING
            elif event in {PlaybackEventType.ENDED, PlaybackEventType.FAILED}:
                await self._finish_current(
                    QueueEntryStatus.COMPLETED
                    if event == PlaybackEventType.ENDED
                    else QueueEntryStatus.FAILED,
                    reason,
                )
                self._promote_next()
            state = await self._commit_locked()
        await self._notify(state)
        return state

    async def get_entry(self, entry_id: str) -> QueueEntry | None:
        async with self._lock:
            if self._current and self._current.id == entry_id:
                return self._current.model_copy(deep=True)
            for entry in self._queue:
                if entry.id == entry_id:
                    return entry.model_copy(deep=True)
            return None

    async def snapshot(self) -> MusicState:
        async with self._lock:
            if self._owner_id and not self._is_owner_locked(self._owner_id):
                self._owner_id = None
                self._owner_seen_at = 0.0
            return self._snapshot_locked()

    def _start_entry(self, entry: QueueEntry) -> None:
        entry.status = QueueEntryStatus.PAUSED if self._paused else QueueEntryStatus.PLAYING
        entry.started_at = utc_now()

    def _promote_next(self) -> None:
        if self._queue:
            self._current = self._queue.popleft()
            self._start_entry(self._current)
        else:
            self._current = None

    async def _finish_current(self, status: QueueEntryStatus, reason: str = "") -> None:
        if self._current is None:
            return
        self._current.status = status
        self._current.finished_at = utc_now()
        self._current.failure_reason = reason
        self._history.append(self._current)
        entry = self._current
        self._current = None
        await self._repository.append_history(entry)

    async def _commit_locked(self) -> MusicState:
        self._revision += 1
        await self._repository.replace_runtime_state(
            self._current,
            list(self._queue),
            self._paused,
            self._volume,
        )
        return self._snapshot_locked()

    def _snapshot_locked(self) -> MusicState:
        owner = self._owner_id if self._owner_id and self._is_owner_locked(self._owner_id) else None
        return MusicState(
            revision=self._revision,
            current=self._current.model_copy(deep=True) if self._current else None,
            queue=[entry.model_copy(deep=True) for entry in self._queue],
            paused=self._paused,
            volume=self._volume,
            ducking_factor=self._ducking_factor,
            effective_volume=self._volume * self._ducking_factor,
            playback_owner_id=owner,
        )

    def _is_owner_locked(self, player_id: str) -> bool:
        return bool(
            self._owner_id == player_id
            and time.monotonic() - self._owner_seen_at <= self._owner_ttl_seconds
        )

    async def _notify(self, state: MusicState) -> None:
        if self._callback:
            try:
                await self._callback(state)
            except Exception:
                logger.warning("Music state broadcast failed", exc_info=True)


class MusicQueueError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
