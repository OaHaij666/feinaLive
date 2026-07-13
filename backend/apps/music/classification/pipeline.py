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
        bypass_review: bool = False,
        allow_llm: bool = True,
    ) -> ClassificationDecision:
        if bypass_review or await self._repository.is_library_track(track):
            return ClassificationDecision(
                verdict=ClassificationVerdict.ACCEPT,
                source=DecisionSource.MANUAL,
                title=track.title,
                artists=track.artists,
                reason="主播曲库或管理员已批准",
            )
        cached = await self._repository.get_classification(track)
        if cached is not None:
            cached.source = DecisionSource.CACHE
            return cached
        rules = self._rules.classify(track, query=query)
        decision = rules
        if rules.verdict == ClassificationVerdict.REVIEW and allow_llm:
            decision = await self._llm.classify(track, query, rules)
        if decision.verdict != ClassificationVerdict.REVIEW:
            await self._repository.save_classification(track, decision)
        return decision
