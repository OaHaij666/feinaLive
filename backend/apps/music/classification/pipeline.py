from __future__ import annotations

from apps.music.classification.llm import LLMMusicClassifier
from apps.music.classification.rules import RuleMusicClassifier
from apps.music.models import (
    ClassificationDecision,
    ClassificationVerdict,
    DecisionSource,
    Track,
)
from apps.music.persistence.repository import MusicRepository


class MusicClassificationPipeline:
    def __init__(
        self,
        repository: MusicRepository,
        rules: RuleMusicClassifier,
        llm: LLMMusicClassifier,
    ) -> None:
        self._repository = repository
        self._rules = rules
        self._llm = llm

    async def classify(
        self,
        track: Track,
        *,
        query: str = "",
        allow_llm: bool = True,
        require_llm: bool = False,
    ) -> ClassificationDecision:
        cached = await self._repository.get_classification(track)
        if await self._repository.is_library_track(track) and (
            not require_llm or (cached is not None and cached.reviewed_by_llm)
        ):
            return ClassificationDecision(
                verdict=ClassificationVerdict.ACCEPT,
                source=DecisionSource.CACHE,
                reviewed_by_llm=bool(cached and cached.reviewed_by_llm),
                title=track.title,
                artists=track.artists,
                reason="已在可信歌单中",
            )
        if cached is not None and (not require_llm or cached.reviewed_by_llm):
            cached.source = DecisionSource.CACHE
            return cached
        rules = self._rules.classify(track, query=query)
        decision = rules
        should_call_llm = allow_llm and (
            rules.verdict == ClassificationVerdict.REVIEW
            or (require_llm and rules.verdict == ClassificationVerdict.ACCEPT)
        )
        if should_call_llm:
            decision = await self._llm.classify(track, query, rules)
        if decision.verdict != ClassificationVerdict.REVIEW:
            await self._repository.save_classification(track, decision)
        return decision
