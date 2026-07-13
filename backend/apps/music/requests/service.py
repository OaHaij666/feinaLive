from __future__ import annotations

import logging

from apps.music.classification.pipeline import MusicClassificationPipeline
from apps.music.models import (
    ClassificationDecision,
    ClassificationVerdict,
    MusicRequest,
    MusicRequestResult,
    Track,
)
from apps.music.persistence.repository import MusicRepository
from apps.music.providers.registry import MusicProviderRegistry
from apps.music.runtime import MusicQueueError, MusicRuntime

logger = logging.getLogger(__name__)


class MusicRequestService:
    def __init__(
        self,
        providers: MusicProviderRegistry,
        classifier: MusicClassificationPipeline,
        runtime: MusicRuntime,
        repository: MusicRepository,
        *,
        min_duration_seconds: int,
        max_duration_seconds: int,
        search_candidates: int = 5,
    ) -> None:
        self._providers = providers
        self._classifier = classifier
        self._runtime = runtime
        self._repository = repository
        self._min_duration = min_duration_seconds
        self._max_duration = max_duration_seconds
        self._search_candidates = search_candidates

    async def submit(self, request: MusicRequest) -> MusicRequestResult:
        provider = self._providers.get(request.provider)
        source_ids: list[str]
        if request.direct_source_id:
            source_ids = [request.direct_source_id]
        else:
            candidates = await provider.search(request.query, limit=self._search_candidates)
            source_ids = [candidate.source_id for candidate in candidates]
        if not source_ids:
            return await self._reject(request, "NO_MATCH", "没有找到匹配的歌曲")

        last_decision: ClassificationDecision | None = None
        last_error = "无法确认搜索结果是歌曲"
        reviews: list[tuple[Track, ClassificationDecision]] = []
        for source_id in source_ids:
            try:
                track = await provider.inspect(source_id)
                hard_error = self._hard_validation(track)
                if hard_error:
                    last_error = hard_error
                    continue
                track = await self._repository.save_track(track)
                decision = await self._classifier.classify(
                    track,
                    query=request.query,
                    bypass_review=request.bypass_review,
                    allow_llm=bool(request.direct_source_id),
                )
                last_decision = decision
                if decision.verdict == ClassificationVerdict.REVIEW:
                    reviews.append((track, decision))
                    last_error = decision.reason or last_error
                    continue
                if decision.verdict != ClassificationVerdict.ACCEPT:
                    last_error = decision.reason or "该视频不是可播放歌曲"
                    continue
                return await self._accept(request, track, decision)
            except MusicQueueError as exc:
                return await self._reject(request, exc.code, str(exc), last_decision)
            except Exception as exc:
                logger.warning("Music candidate failed %s/%s: %s", request.provider, source_id, exc)
                last_error = "获取或审核音乐失败"
        if not request.direct_source_id and reviews:
            track, _ = max(reviews, key=lambda item: item[1].rule_score)
            decision = await self._classifier.classify(
                track,
                query=request.query,
                bypass_review=request.bypass_review,
                allow_llm=True,
            )
            last_decision = decision
            if decision.verdict == ClassificationVerdict.ACCEPT:
                return await self._accept(request, track, decision)
            last_error = decision.reason or last_error
        return await self._reject(request, "TRACK_REJECTED", last_error, last_decision)

    async def _accept(
        self,
        request: MusicRequest,
        track: Track,
        decision: ClassificationDecision,
    ) -> MusicRequestResult:
        if decision.title:
            track.title = decision.title
        if decision.artists:
            track.artists = decision.artists
        track = await self._repository.save_track(track)
        try:
            entry = await self._runtime.enqueue(
                track,
                requested_by=request.requested_by,
                request_id=request.request_id,
            )
        except MusicQueueError as exc:
            return await self._reject(request, exc.code, str(exc), decision)
        await self._repository.save_request(
            request_id=request.request_id,
            requested_by=request.requested_by,
            query=request.query,
            provider=request.provider,
            source_id=track.source_id,
            track_id=track.id,
            status="accepted",
        )
        return MusicRequestResult(
            accepted=True,
            entry=entry,
            classification=decision,
        )

    def _hard_validation(self, track: Track) -> str:
        if track.duration_seconds < self._min_duration:
            return f"歌曲时长不能少于 {self._min_duration} 秒"
        if track.duration_seconds > self._max_duration:
            return f"歌曲时长不能超过 {self._max_duration} 秒"
        pages = track.metadata.get("pages")
        if isinstance(pages, list) and len(pages) > 1:
            return "暂不接受没有指定分P的多P视频"
        return ""

    async def _reject(
        self,
        request: MusicRequest,
        code: str,
        error: str,
        classification: ClassificationDecision | None = None,
    ) -> MusicRequestResult:
        await self._repository.save_request(
            request_id=request.request_id,
            requested_by=request.requested_by,
            query=request.query,
            provider=request.provider,
            source_id=request.direct_source_id or "",
            track_id=None,
            status="rejected",
            error_code=code,
        )
        return MusicRequestResult(
            accepted=False,
            error_code=code,
            error=error,
            classification=classification,
        )
