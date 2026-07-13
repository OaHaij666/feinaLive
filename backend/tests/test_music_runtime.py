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

    async def load_runtime_state(self):
        return self.current, self.queue, self.paused, self.volume

    async def load_history(self, limit=100):
        return self.history[-limit:]

    async def replace_runtime_state(self, current, queue, paused, volume):
        self.current = current
        self.queue = queue
        self.paused = paused
        self.volume = volume

    async def save_track(self, track):
        return track

    async def append_history(self, entry):
        if all(item.id != entry.id for item in self.history):
            self.history.append(entry)

    async def is_library_track(self, _track):
        return False

    async def get_classification(self, _track):
        return self.cached

    async def save_classification(self, _track, decision, *, manual=False):
        self.cached = decision

    async def save_request(self, **values):
        self.saved_request = values


def track(source_id: str, **metadata) -> Track:
    return Track(
        provider="test",
        source_id=source_id,
        title=metadata.pop("title", source_id),
        artists=["artist"],
        duration_seconds=180,
        metadata=metadata,
    )


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


class SearchProvider:
    id = "search-test"

    async def search(self, query, limit=10):
        return [ProviderSearchResult(source_id=f"candidate-{index}", title=query) for index in range(3)]

    async def inspect(self, source_id):
        return track(source_id, title=f"模糊候选 {source_id}")

    async def resolve_stream(self, source_id):
        return AudioStream(url="https://example.invalid/audio")


class ReviewThenAcceptClassifier:
    def __init__(self):
        self.llm_calls = 0

    async def classify(self, candidate, *, query="", bypass_review=False, allow_llm=True):
        if not allow_llm:
            return ClassificationDecision(
                verdict=ClassificationVerdict.REVIEW,
                source=DecisionSource.RULES,
                rule_score=int(candidate.source_id[-1]),
                title=candidate.title,
                artists=candidate.artists,
            )
        self.llm_calls += 1
        return ClassificationDecision(
            verdict=ClassificationVerdict.ACCEPT,
            source=DecisionSource.LLM,
            confidence=0.9,
            title=candidate.title,
            artists=candidate.artists,
        )


@pytest.mark.asyncio
async def test_search_sends_only_best_ambiguous_candidate_to_llm():
    repository = FakeRepository()
    runtime = MusicRuntime(repository, queue_capacity=5, per_user_limit=2)
    await runtime.initialize()
    providers = MusicProviderRegistry()
    providers.register(SearchProvider())
    classifier = ReviewThenAcceptClassifier()
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
    assert classifier.llm_calls == 1
    assert result.entry and result.entry.track.source_id == "candidate-2"
