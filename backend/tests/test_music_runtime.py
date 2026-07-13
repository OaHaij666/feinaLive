from __future__ import annotations

import pytest

from apps.music.classification.pipeline import MusicClassificationPipeline
from apps.music.classification.rules import RuleMusicClassifier
from apps.music.models import (
    AudioStream,
    ClassificationDecision,
    ClassificationVerdict,
    DecisionSource,
    MusicRequest,
    PlaybackEventType,
    ProviderSearchResult,
    Track,
)
from apps.music.persistence.repository import MusicRepository
from apps.music.providers.base import ProviderTrustPolicy
from apps.music.providers.registry import MusicProviderRegistry
from apps.music.requests.service import MusicRequestService
from apps.music.runtime import MusicQueueError, MusicRuntime


class FakeRepository:
    def __init__(self) -> None:
        self.current = None
        self.queue = []
        self.paused = False
        self.volume = 1.0
        self.history = []
        self.cached = None

    async def load_runtime_state(self, *, default_ducking_enabled=True):
        return self.current, self.queue, self.paused, self.volume, default_ducking_enabled

    async def load_history(self, limit=100):
        return self.history[-limit:]

    async def replace_runtime_state(self, current, queue, paused, volume, ducking_enabled):
        self.current = current
        self.queue = queue
        self.paused = paused
        self.volume = volume
        self.ducking_enabled = ducking_enabled

    async def save_track(self, track):
        return track

    async def append_history(self, entry):
        if all(item.id != entry.id for item in self.history):
            self.history.append(entry)

    async def is_library_track(self, _track):
        return False

    async def get_classification(self, _track):
        return self.cached

    async def save_classification(self, _track, decision):
        self.cached = decision

    async def save_request(self, **values):
        self.saved_request = values

    async def add_library(self, track):
        self.library_track = track

    async def search_library(self, query, **kwargs):
        return [self.library_track] if getattr(self, "library_track", None) else []


def track(source_id: str, **metadata) -> Track:
    return Track(
        provider=metadata.pop("provider", "test"),
        source_id=source_id,
        title=metadata.pop("title", source_id),
        artists=["artist"],
        duration_seconds=180,
        metadata=metadata,
    )


def test_classification_fingerprint_ignores_volatile_provider_counters():
    earlier = track("same", view_count=1, like_count=2)
    later = track("same", view_count=999, like_count=888)
    assert MusicRepository.fingerprint(earlier) == MusicRepository.fingerprint(later)


@pytest.mark.asyncio
async def test_playback_end_advances_exactly_one_entry():
    repository = FakeRepository()
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    first = await runtime.enqueue(track("one"), requested_by="a")
    second = await runtime.enqueue(track("two"), requested_by="b")
    third = await runtime.enqueue(track("three"), requested_by="c")
    assert await runtime.claim_player("player-one")

    state = await runtime.playback_event(
        player_id="player-one",
        entry_id=first.id,
        event=PlaybackEventType.ENDED,
    )
    assert state.current and state.current.id == second.id
    assert [entry.id for entry in state.queue] == [third.id]

    duplicate = await runtime.playback_event(
        player_id="player-one",
        entry_id=first.id,
        event=PlaybackEventType.ENDED,
    )
    assert duplicate.current and duplicate.current.id == second.id
    assert [entry.id for entry in duplicate.queue] == [third.id]


@pytest.mark.asyncio
async def test_only_playback_owner_can_acknowledge():
    runtime = MusicRuntime(FakeRepository(), queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    entry = await runtime.enqueue(track("one"), requested_by="a")
    assert await runtime.claim_player("owner-one")
    assert not await runtime.claim_player("owner-two")

    with pytest.raises(MusicQueueError) as error:
        await runtime.playback_event(
            player_id="owner-two",
            entry_id=entry.id,
            event=PlaybackEventType.ENDED,
        )
    assert error.value.code == "NOT_PLAYBACK_OWNER"


@pytest.mark.asyncio
async def test_ducking_preserves_user_volume_and_only_changes_effective_volume():
    runtime = MusicRuntime(FakeRepository(), queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    await runtime.set_volume(0.8)
    ducked = await runtime.set_ducking(0.25)
    assert ducked.volume == 0.8
    assert ducked.effective_volume == pytest.approx(0.2)
    disabled = await runtime.set_ducking_enabled(False)
    assert not disabled.ducking_enabled
    assert disabled.effective_volume == pytest.approx(0.8)
    await runtime.set_ducking_enabled(True)
    restored = await runtime.set_ducking(1.0)
    assert restored.volume == 0.8
    assert restored.effective_volume == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_queue_rejects_duplicates_and_user_overflow_without_dropping_entries():
    runtime = MusicRuntime(FakeRepository(), queue_capacity=3, per_user_limit=1)
    await runtime.initialize()
    await runtime.enqueue(track("one"), requested_by="a")
    with pytest.raises(MusicQueueError) as duplicate:
        await runtime.enqueue(track("one"), requested_by="b")
    assert duplicate.value.code == "DUPLICATE_REQUEST"
    with pytest.raises(MusicQueueError) as user_limit:
        await runtime.enqueue(track("two"), requested_by="a")
    assert user_limit.value.code == "USER_LIMIT_REACHED"
    await runtime.enqueue(track("two"), requested_by="b")
    await runtime.enqueue(track("three"), requested_by="c")
    with pytest.raises(MusicQueueError) as full:
        await runtime.enqueue(track("four"), requested_by="d")
    assert full.value.code == "QUEUE_FULL"
    state = await runtime.snapshot()
    assert state.current and state.current.track.source_id == "one"
    assert [item.track.source_id for item in state.queue] == ["two", "three"]


def test_rule_classifier_accepts_rejects_and_escalates_conflicts():
    classifier = RuleMusicClassifier()
    accepted = classifier.classify(
        track(
            "song",
            title="【原创曲】星海 Official MV",
            tname="原创音乐",
            tags=["原创音乐", "MV"],
        )
    )
    assert accepted.verdict == ClassificationVerdict.ACCEPT
    assert accepted.rule_score >= 60

    rejected = classifier.classify(
        track(
            "tutorial",
            title="如何制作一首流行歌：完整教程",
            tname="知识",
            tags=["教程"],
            description="本期教程教你如何编曲",
        )
    )
    assert rejected.verdict == ClassificationVerdict.REJECT
    assert rejected.rule_score <= -50

    review = classifier.classify(
        track(
            "conflict",
            title="三分钟学会这首歌：完整演奏",
            tname="音乐",
            tags=["演奏"],
        )
    )
    assert review.verdict == ClassificationVerdict.REVIEW
    assert review.has_conflict


class StubRules:
    def __init__(self, verdict: ClassificationVerdict) -> None:
        self.verdict = verdict

    def classify(self, track, query=""):
        return ClassificationDecision(
            verdict=self.verdict,
            source=DecisionSource.RULES,
            title=track.title,
            artists=track.artists,
        )


class CountingLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def classify(self, track, query, rule_decision):
        self.calls += 1
        return ClassificationDecision(
            verdict=ClassificationVerdict.ACCEPT,
            source=DecisionSource.LLM,
            reviewed_by_llm=True,
            confidence=0.9,
            title=track.title,
            artists=track.artists,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("rule_verdict", "expected_calls"),
    [
        (ClassificationVerdict.ACCEPT, 0),
        (ClassificationVerdict.REJECT, 0),
        (ClassificationVerdict.REVIEW, 1),
    ],
)
async def test_llm_is_only_called_for_rule_review(rule_verdict, expected_calls):
    repository = FakeRepository()
    llm = CountingLLM()
    pipeline = MusicClassificationPipeline(repository, StubRules(rule_verdict), llm)
    decision = await pipeline.classify(track("candidate"))
    assert llm.calls == expected_calls
    assert decision.verdict in {ClassificationVerdict.ACCEPT, ClassificationVerdict.REJECT}


@pytest.mark.asyncio
async def test_review_required_admission_calls_llm_even_when_rules_accept():
    repository = FakeRepository()
    llm = CountingLLM()
    pipeline = MusicClassificationPipeline(
        repository,
        StubRules(ClassificationVerdict.ACCEPT),
        llm,
    )
    decision = await pipeline.classify(track("candidate"), require_llm=True)
    assert llm.calls == 1
    assert decision.reviewed_by_llm


class SearchProvider:
    id = "search-test"
    trust_policy = ProviderTrustPolicy.NATIVE_MUSIC

    async def search(self, query, limit=10):
        return [ProviderSearchResult(source_id=f"candidate-{index}", title=query) for index in range(3)]

    async def inspect(self, source_id):
        return track(source_id, provider=self.id, title=f"模糊候选 {source_id}")

    async def resolve_stream(self, source_id):
        return AudioStream(url="https://example.invalid/audio")


class MixedContentProvider(SearchProvider):
    id = "mixed-test"
    trust_policy = ProviderTrustPolicy.REVIEW_REQUIRED

    async def search(self, query, limit=10):
        raise AssertionError("mixed-content native search must not be used for ordinary requests")


class ApprovingClassifier:
    def __init__(self):
        self.calls = []

    async def classify(self, candidate, **kwargs):
        self.calls.append(kwargs)
        return ClassificationDecision(
            verdict=ClassificationVerdict.ACCEPT,
            source=DecisionSource.LLM,
            reviewed_by_llm=True,
            confidence=0.9,
            title=candidate.title,
            artists=candidate.artists,
        )


class FailingClassifier:
    def __init__(self):
        self.calls = 0

    async def classify(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("native music providers must not invoke the content classifier")


class RejectingClassifier:
    async def classify(self, candidate, **kwargs):
        return ClassificationDecision(
            verdict=ClassificationVerdict.REJECT,
            source=DecisionSource.LLM,
            reviewed_by_llm=True,
            confidence=0.99,
            title=candidate.title,
            artists=candidate.artists,
            reason="不是歌曲",
        )


@pytest.mark.asyncio
async def test_native_music_provider_search_does_not_invoke_llm():
    repository = FakeRepository()
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    providers = MusicProviderRegistry()
    providers.register(SearchProvider())
    classifier = FailingClassifier()
    service = MusicRequestService(
        providers,
        classifier,
        runtime,
        repository,
        min_duration_seconds=60,
        max_duration_seconds=480,
    )
    result = await service.submit(
        MusicRequest(query="某首歌", requested_by="viewer", provider="search-test")
    )
    assert result.accepted
    assert classifier.calls == 0
    assert result.entry and result.entry.track.source_id == "candidate-0"


@pytest.mark.asyncio
async def test_empty_music_request_is_rejected_without_searching_or_classifying():
    repository = FakeRepository()
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    providers = MusicProviderRegistry()
    providers.register(SearchProvider())
    classifier = FailingClassifier()
    service = MusicRequestService(
        providers,
        classifier,
        runtime,
        repository,
        min_duration_seconds=60,
        max_duration_seconds=480,
    )
    result = await service.submit(
        MusicRequest(query="  ", requested_by="viewer", provider="search-test")
    )
    assert not result.accepted
    assert result.error_code == "MISSING_QUERY"
    assert classifier.calls == 0


@pytest.mark.asyncio
async def test_mixed_content_direct_source_requires_llm_before_catalog_and_queue():
    repository = FakeRepository()
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    providers = MusicProviderRegistry()
    providers.register(MixedContentProvider())
    classifier = ApprovingClassifier()
    service = MusicRequestService(
        providers,
        classifier,
        runtime,
        repository,
        min_duration_seconds=60,
        max_duration_seconds=480,
    )
    result = await service.submit(
        MusicRequest(
            query="候选歌曲",
            requested_by="viewer",
            provider="mixed-test",
            direct_source_id="candidate-1",
        )
    )
    assert result.accepted
    assert classifier.calls == [{"query": "候选歌曲", "allow_llm": True, "require_llm": True}]
    assert repository.library_track.source_id == "candidate-1"
    assert repository.cached is not None and repository.cached.reviewed_by_llm


@pytest.mark.asyncio
async def test_mixed_content_rejected_by_llm_never_enters_trusted_catalog():
    repository = FakeRepository()
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    providers = MusicProviderRegistry()
    providers.register(MixedContentProvider())
    service = MusicRequestService(
        providers,
        RejectingClassifier(),
        runtime,
        repository,
        min_duration_seconds=60,
        max_duration_seconds=480,
    )

    result = await service.submit(
        MusicRequest(
            query="看起来像歌",
            requested_by="viewer",
            provider="mixed-test",
            direct_source_id="candidate-1",
        )
    )
    assert not result.accepted
    assert result.error_code == "LLM_REVIEW_REJECTED"
    assert not hasattr(repository, "library_track")


@pytest.mark.asyncio
async def test_mixed_content_name_search_only_uses_llm_reviewed_catalog():
    repository = FakeRepository()
    repository.library_track = track(
        "trusted-song", provider="mixed-test", title="可信歌曲"
    )
    repository.cached = ClassificationDecision(
        verdict=ClassificationVerdict.ACCEPT,
        source=DecisionSource.LLM,
        reviewed_by_llm=True,
        title="可信歌曲",
        artists=["artist"],
    )
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    providers = MusicProviderRegistry()
    providers.register(MixedContentProvider())
    classifier = FailingClassifier()
    service = MusicRequestService(
        providers,
        classifier,
        runtime,
        repository,
        min_duration_seconds=60,
        max_duration_seconds=480,
    )

    result = await service.submit(
        MusicRequest(query="可信歌曲", requested_by="viewer", provider="mixed-test")
    )
    assert result.accepted
    assert result.entry and result.entry.track.source_id == "trusted-song"
    assert result.classification and result.classification.reviewed_by_llm
    assert classifier.calls == 0
