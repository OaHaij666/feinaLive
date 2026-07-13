from __future__ import annotations

import logging

from apps.music.classification.pipeline import MusicClassificationPipeline
from apps.music.models import (
    ClassificationDecision,
    ClassificationVerdict,
    DecisionSource,
    MusicRequest,
    MusicRequestResult,
    Track,
)
from apps.music.persistence.repository import MusicRepository
from apps.music.providers.base import MusicProvider, ProviderTrustPolicy
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
        if request.direct_source_id:
            if request.provider == "auto":
                return await self._reject(
                    request,
                    "PROVIDER_REQUIRED",
                    "直接提交来源 ID 时必须指定 Provider",
                )
            try:
                track, decision = await self.add_to_catalog(
                    request.provider,
                    request.direct_source_id,
                    query=request.query,
                )
            except MusicAdmissionError as exc:
                return await self._reject(request, exc.code, str(exc), exc.decision)
            return await self._enqueue(request, track, decision)

        if not request.query.strip():
            return await self._reject(request, "MISSING_QUERY", "请提供歌名或音乐来源 ID")

        tracks = await self._search(request.query, request.provider)
        if not tracks:
            return await self._reject(request, "NO_MATCH", "没有在可用音乐源中找到匹配歌曲")
        last_error = "没有找到满足播放条件的歌曲"
        for track in tracks:
            hard_error = self._hard_validation(track)
            if hard_error:
                last_error = hard_error
                continue
            return await self._enqueue(request, track, await self._trusted_decision(track))
        return await self._reject(request, "TRACK_REJECTED", last_error)

    async def add_to_catalog(
        self,
        provider_id: str,
        source_id: str,
        *,
        query: str = "",
    ) -> tuple[Track, ClassificationDecision]:
        provider = self._providers.get(provider_id)
        try:
            track = await provider.inspect(source_id)
        except Exception as exc:
            raise MusicAdmissionError("SOURCE_UNAVAILABLE", "无法读取音乐来源") from exc
        hard_error = self._hard_validation(track)
        if hard_error:
            raise MusicAdmissionError("TRACK_REJECTED", hard_error)
        track = await self._repository.save_track(track)

        if provider.trust_policy == ProviderTrustPolicy.REVIEW_REQUIRED:
            decision = await self._classifier.classify(
                track,
                query=query,
                allow_llm=True,
                require_llm=True,
            )
            if (
                decision.verdict != ClassificationVerdict.ACCEPT
                or not decision.reviewed_by_llm
            ):
                raise MusicAdmissionError(
                    "LLM_REVIEW_REJECTED",
                    decision.reason or "LLM 未确认该内容是歌曲",
                    decision,
                )
            if decision.title:
                track.title = decision.title
            if decision.artists:
                track.artists = decision.artists
            track = await self._repository.save_track(track)
            # Normalized title/artists change the content fingerprint. Store the
            # approval against the canonical track used by trusted-library lookup.
            await self._repository.save_classification(track, decision)
        else:
            decision = ClassificationDecision(
                verdict=ClassificationVerdict.ACCEPT,
                source=DecisionSource.PROVIDER,
                title=track.title,
                artists=track.artists,
                reason="Provider 是原生音乐目录，无需内容审核",
            )

        await self._repository.add_library(track)
        return track, decision

    async def _trusted_decision(self, track: Track) -> ClassificationDecision:
        provider = self._providers.get(track.provider)
        if provider.trust_policy == ProviderTrustPolicy.REVIEW_REQUIRED:
            decision = await self._repository.get_classification(track)
            if decision is None or not decision.reviewed_by_llm:
                raise RuntimeError("混合内容来源返回了未经 LLM 审核的曲目")
            return decision
        return ClassificationDecision(
            verdict=ClassificationVerdict.ACCEPT,
            source=DecisionSource.PROVIDER,
            title=track.title,
            artists=track.artists,
            reason="来自原生音乐目录，无需内容审核",
        )

    async def _search(self, query: str, provider_id: str) -> list[Track]:
        providers = (
            self._providers.values()
            if provider_id == "auto"
            else [self._providers.get(provider_id)]
        )
        results: list[Track] = []
        for provider in providers:
            try:
                results.extend(await self._search_provider(provider, query))
            except Exception:
                logger.warning("Music provider search failed: %s", provider.id, exc_info=True)
        return _rank_tracks(results, query)[: self._search_candidates]

    async def _search_provider(self, provider: MusicProvider, query: str) -> list[Track]:
        if provider.trust_policy == ProviderTrustPolicy.REVIEW_REQUIRED:
            return await self._repository.search_library(
                query,
                provider=provider.id,
                require_llm_review=True,
                limit=self._search_candidates,
            )
        candidates = await provider.search(query, limit=self._search_candidates)
        tracks: list[Track] = []
        for candidate in candidates:
            try:
                track = await provider.inspect(candidate.source_id)
                tracks.append(await self._repository.save_track(track))
            except Exception:
                logger.debug(
                    "Music candidate inspection failed: %s/%s",
                    provider.id,
                    candidate.source_id,
                    exc_info=True,
                )
        return tracks

    async def _enqueue(
        self,
        request: MusicRequest,
        track: Track,
        decision: ClassificationDecision,
    ) -> MusicRequestResult:
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
            provider=track.provider,
            source_id=track.source_id,
            track_id=track.id,
            status="accepted",
        )
        return MusicRequestResult(accepted=True, entry=entry, classification=decision)

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


class MusicAdmissionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        decision: ClassificationDecision | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.decision = decision


def _rank_tracks(tracks: list[Track], query: str) -> list[Track]:
    terms = [value for value in query.casefold().split() if value]

    def score(track: Track) -> tuple[int, str]:
        title = track.title.casefold()
        text = f"{title} {' '.join(track.artists)}".casefold()
        value = sum(3 if term in title else 1 for term in terms if term in text)
        if track.provider == "local":
            value += 1
        return (-value, track.title.casefold())

    unique: dict[tuple[str, str], Track] = {
        (track.provider, track.source_id): track for track in tracks
    }
    return sorted(unique.values(), key=score)
