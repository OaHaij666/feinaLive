from __future__ import annotations

import asyncio
import logging
import random

from apps.audio_focus import get_audio_focus_coordinator
from apps.config import config
from apps.music.classification.llm import LLMMusicClassifier
from apps.music.classification.pipeline import MusicClassificationPipeline
from apps.music.classification.rules import RuleMusicClassifier
from apps.music.models import (
    MusicRequest,
    MusicRequestResult,
    MusicState,
    PlaybackEventType,
    QueueEntry,
    Track,
)
from apps.music.persistence.repository import MusicRepository
from apps.music.providers.base import ProviderTrustPolicy
from apps.music.providers.bilibili import BilibiliMusicProvider
from apps.music.providers.local import LocalMusicProvider
from apps.music.providers.registry import MusicProviderRegistry
from apps.music.requests.service import MusicRequestService
from apps.music.runtime import MusicRuntime

logger = logging.getLogger(__name__)


class MusicManager:
    def __init__(self) -> None:
        self._repository = MusicRepository()
        self._providers = MusicProviderRegistry()
        self._runtime: MusicRuntime | None = None
        self._requests: MusicRequestService | None = None
        self._initialized = False
        self._init_lock = asyncio.Lock()

    @property
    def runtime(self) -> MusicRuntime:
        if self._runtime is None:
            raise RuntimeError("MusicManager is not initialized")
        return self._runtime

    async def initialize(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            await self._repository.initialize()
            self._providers.register(BilibiliMusicProvider())
            self._providers.register(LocalMusicProvider(config.music_local_directories))
            self._runtime = MusicRuntime(
                self._repository,
                queue_capacity=config.music_queue_capacity,
                per_user_limit=config.music_per_user_limit,
                ducking_enabled=config.music_ducking_enabled,
            )
            await self._runtime.initialize()
            self._runtime.set_state_callback(self._broadcast_state)
            get_audio_focus_coordinator().register(self.set_ducking)
            classifier = MusicClassificationPipeline(
                self._repository,
                RuleMusicClassifier(
                    accept_score=config.music_accept_score,
                    reject_score=config.music_reject_score,
                ),
                LLMMusicClassifier(min_confidence=config.music_llm_min_confidence),
            )
            self._requests = MusicRequestService(
                self._providers,
                classifier,
                self._runtime,
                self._repository,
                min_duration_seconds=config.music_min_duration_seconds,
                max_duration_seconds=config.music_max_duration_seconds,
                search_candidates=config.music_search_candidates,
            )
            await self._ensure_fallback(await self._runtime.snapshot())
            self._initialized = True
            logger.info("MusicManager initialized with providers=%s", self._providers.list_ids())

    async def shutdown(self) -> None:
        if not self._initialized:
            return
        state = await self.runtime.snapshot()
        await self._repository.replace_runtime_state(
            state.current,
            state.queue,
            state.paused,
            state.volume,
            state.ducking_enabled,
        )

    async def submit(self, request: MusicRequest) -> MusicRequestResult:
        await self.initialize()
        assert self._requests is not None
        return await self._requests.submit(request)

    async def state(self) -> MusicState:
        await self.initialize()
        return await self.runtime.snapshot()

    async def list_providers(self) -> list[str]:
        await self.initialize()
        return self._providers.list_ids()

    async def search_provider(self, provider_id: str, query: str, limit: int = 20):
        await self.initialize()
        return await self._providers.get(provider_id).search(query, limit=limit)

    async def skip(self, *, remove_from_library: bool = False) -> MusicState:
        await self.initialize()
        state = await self.runtime.snapshot()
        if remove_from_library and state.current:
            await self._repository.set_library_enabled(state.current.track.id, False)
        state = await self.runtime.skip()
        return await self._ensure_fallback(state)

    async def set_paused(self, paused: bool) -> MusicState:
        await self.initialize()
        return await self.runtime.set_paused(paused)

    async def set_volume(self, volume: float) -> MusicState:
        await self.initialize()
        return await self.runtime.set_volume(volume)

    async def set_ducking(self, active: bool) -> MusicState:
        await self.initialize()
        factor = config.music_ducking_factor if active else 1.0
        return await self.runtime.set_ducking(factor)

    async def set_ducking_enabled(self, enabled: bool) -> MusicState:
        await self.initialize()
        return await self.runtime.set_ducking_enabled(enabled)

    async def playback_event(
        self,
        *,
        player_id: str,
        entry_id: str,
        event: PlaybackEventType,
        reason: str = "",
    ) -> MusicState:
        await self.initialize()
        state = await self.runtime.playback_event(
            player_id=player_id,
            entry_id=entry_id,
            event=event,
            reason=reason,
        )
        if event in {PlaybackEventType.ENDED, PlaybackEventType.FAILED}:
            return await self._ensure_fallback(state)
        return state

    async def resolve_current_stream(self, entry_id: str, player_id: str):
        await self.initialize()
        if not await self.runtime.validate_player(player_id):
            raise PermissionError("Not the active music playback owner")
        state = await self.runtime.snapshot()
        if state.current is None or state.current.id != entry_id:
            raise LookupError("Queue entry is not current")
        provider = self._providers.get(state.current.track.provider)
        return await provider.resolve_stream(state.current.track.source_id)

    async def add_library(self, provider_id: str, source_id: str) -> Track:
        await self.initialize()
        assert self._requests is not None
        track, _ = await self._requests.add_to_catalog(provider_id, source_id)
        return track

    async def list_library(self) -> list[Track]:
        await self.initialize()
        tracks = await self._repository.list_library()
        trusted: list[Track] = []
        for track in tracks:
            provider = self._providers.get(track.provider)
            if provider.trust_policy == ProviderTrustPolicy.NATIVE_MUSIC:
                trusted.append(track)
                continue
            decision = await self._repository.get_classification(track)
            if decision and decision.reviewed_by_llm:
                trusted.append(track)
        return trusted

    async def history(self, limit: int = 100) -> list[QueueEntry]:
        await self.initialize()
        return await self._repository.load_history(limit=limit)

    async def set_library_enabled(self, track_id: str, enabled: bool) -> bool:
        await self.initialize()
        return await self._repository.set_library_enabled(track_id, enabled)

    async def remove_queue_entry(self, entry_id: str) -> bool:
        await self.initialize()
        return await self.runtime.remove(entry_id)

    async def clear_queue(self) -> int:
        await self.initialize()
        return await self.runtime.clear()

    async def _ensure_fallback(self, state: MusicState) -> MusicState:
        if state.current is not None or state.queue:
            return state
        library = await self.list_library()
        if not library:
            return state
        fallback = random.choice(library)
        try:
            await self.runtime.enqueue(fallback, requested_by="system")
        except Exception:
            logger.warning("Unable to enqueue fallback music", exc_info=True)
        return await self.runtime.snapshot()

    @staticmethod
    async def _broadcast_state(state: MusicState) -> None:
        from apps.live.runtime import get_live_runtime
        from core.websocket import manager as websocket_manager

        context = get_live_runtime().active_context
        if context is None:
            return
        await websocket_manager.send_message(
            context.routing_key,
            {
                "type": "music_state",
                "data": state.model_dump(mode="json"),
                "context": context.to_dict(),
            },
        )


_manager: MusicManager | None = None


def get_music_manager() -> MusicManager:
    global _manager
    if _manager is None:
        _manager = MusicManager()
    return _manager
