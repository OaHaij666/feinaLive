import asyncio
from types import SimpleNamespace

import pytest

from apps.ai import speech_pipeline as speech_module
from apps.ai.host_brain import AIHostBrain, DanmakuInput
from apps.ai.host_messages import HostMessageProcessor
from apps.ai.host_runtime import HostRuntime, HostRuntimeState
from apps.ai.messaging.queue import Message, PriorityMessageQueue
from apps.ai.playback import PlaybackCoordinator
from apps.ai.shared_context import SharedContext
from apps.ai.speech_pipeline import SpeechPipeline
from apps.live.room_session import RoomSessionContext


class FakeBrain:
    def __init__(self):
        self.started = 0
        self.stopped = 0

    async def start_polling(self):
        self.started += 1

    async def stop_polling(self):
        self.stopped += 1


class FakeQueue:
    def __init__(self):
        self.messages = asyncio.Queue()
        self.override_count = 0

    def apply_priority_override(self):
        self.override_count += 1

    async def get(self):
        return await self.messages.get()


class FakeProcessor:
    def __init__(self):
        self.processed: list[str] = []
        self.failures: list[str] = []
        self.ready = asyncio.Event()

    async def handle_commentary(self, message):
        self.processed.append(message.id)
        self.ready.set()

    async def handle_danmaku(self, message):
        self.processed.append(message.id)
        self.ready.set()

    async def handle_gift(self, message):
        self.processed.append(message.id)
        self.ready.set()

    async def fail(self, message, error):
        self.failures.append(message.id)


class AllowAllRateLimiter:
    def allow(self, source: str, msg_type: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_host_runtime_owns_brain_and_single_consumer_lifecycle():
    brain = FakeBrain()
    queue = FakeQueue()
    processor = FakeProcessor()
    runtime = HostRuntime(brain=brain, queue=queue, processor=processor)

    await runtime.start()
    await queue.messages.put(Message(id="one", msg_type="danmaku"))
    await asyncio.wait_for(processor.ready.wait(), timeout=1)
    await runtime.stop()

    assert runtime.state is HostRuntimeState.STOPPED
    assert processor.processed == ["one"]
    assert brain.started == 1
    assert brain.stopped == 1


@pytest.mark.asyncio
async def test_host_runtime_start_is_idempotent():
    brain = FakeBrain()
    runtime = HostRuntime(brain=brain, queue=FakeQueue(), processor=FakeProcessor())

    await runtime.start()
    await runtime.start()
    await runtime.stop()

    assert brain.started == 1
    assert brain.stopped == 1


@pytest.mark.asyncio
async def test_host_brain_marks_messages_answered_only_after_queue_accepts(monkeypatch):
    context = RoomSessionContext.test_room()
    brain = AIHostBrain()
    danmaku = DanmakuInput(context=context, msg_id="m1", user="viewer", content="hello")
    marked: list[list[str]] = []

    class History:
        def mark_answered_batch(self, message_ids):
            marked.append(message_ids)

    class Queue:
        accepted = False

        async def put(self, message):
            return self.accepted

    queue = Queue()
    monkeypatch.setattr("apps.ai.host_brain.get_message_queue", lambda: queue)
    monkeypatch.setattr("apps.ai.host_brain.get_session", lambda session_id: History())

    assert await brain._enqueue_danmaku([danmaku]) is False
    assert marked == []

    queue.accepted = True
    assert await brain._enqueue_danmaku([danmaku]) is True
    assert marked == [["m1"]]


@pytest.mark.asyncio
async def test_queue_rejects_missing_or_malformed_room_context():
    queue = PriorityMessageQueue(rate_limiter=AllowAllRateLimiter(), max_size=10)

    assert not await queue.put(Message(source="danmaku", msg_type="danmaku"))
    assert not await queue.put(
        Message(
            source="game",
            msg_type="commentary_request",
            context={"room_id": "broken"},
        )
    )


def test_message_processor_does_not_fallback_from_malformed_context():
    message = Message(
        source="danmaku",
        msg_type="danmaku",
        context={"room_id": "broken"},
    )

    assert HostMessageProcessor.context_for(message) is None


@pytest.mark.asyncio
async def test_released_commentary_ack_is_not_recreated_by_late_signal():
    shared = SharedContext()
    await shared.register_commentary_request("request")
    await shared.signal_commentary_status("request", "timeout")
    await shared.release_commentary_request("request")

    await shared.signal_commentary_status("request", "spoken")

    assert "request" not in shared._commentary_acks


@pytest.mark.asyncio
async def test_speech_pipeline_enforces_reply_limit_before_tts(monkeypatch):
    broadcasts = []
    synthesized = []

    class AI:
        available = True

        async def chat_stream(self, request):
            yield "123456789"

    class TTSResult:
        audio_data = b"audio"

    class TTS:
        async def synthesize(self, text):
            synthesized.append(text)
            return TTSResult()

    class Playback:
        chunks = []

        async def begin(self, reply_id):
            return SimpleNamespace(reply_id=reply_id, owner_id="owner")

        async def send_chunk(self, reply_id, chunk):
            self.chunks.append(chunk)
            return True

        async def wait_for_completion(self, reply_id, timeout):
            return SimpleNamespace(status="finished", error="")

        async def abort(self, reply_id, error):
            return None

    async def broadcast(context, chunk):
        broadcasts.append(chunk)

    monkeypatch.setattr("apps.ai.speech_pipeline.get_ai_client", lambda: AI())
    monkeypatch.setattr("apps.ai.speech_pipeline.get_tts_client", lambda: TTS())
    monkeypatch.setattr(
        type(speech_module.config),
        "host_max_reply_length",
        property(lambda self: 5),
    )

    playback = Playback()
    result = await SpeechPipeline(broadcaster=broadcast, playback=playback).stream_reply(
        "system",
        "user",
        RoomSessionContext.test_room(),
    )

    assert result is not None
    assert result.text == "12345"
    assert result.played
    assert synthesized == ["12345"]
    assert [chunk["chunk_seq"] for chunk in playback.chunks] == list(
        range(len(playback.chunks))
    )
    assert len({chunk["reply_id"] for chunk in playback.chunks}) == 1
    observer_audio = next(chunk for chunk in broadcasts if chunk["type"] == "audio")
    assert "audio" not in observer_audio
    assert observer_audio["observer_only"] is True
    assert broadcasts[-1]["type"] == "end"
    assert broadcasts[-1]["text"] == "12345"


@pytest.mark.asyncio
async def test_playback_coordinator_elects_one_owner_and_waits_for_real_finish():
    coordinator = PlaybackCoordinator()
    messages_a = []
    messages_b = []

    async def notify_a(message):
        messages_a.append(message)

    async def notify_b(message):
        messages_b.append(message)

    await coordinator.register("a", notify_a)
    await coordinator.register("b", notify_b)
    assert await coordinator.set_ready("a", True)
    assert not await coordinator.set_ready("b", True)

    session = await coordinator.begin("reply")
    assert session is not None
    assert session.owner_id == "a"
    assert await coordinator.send_chunk("reply", {"type": "audio"})
    assert messages_a[-1] == {"type": "audio"}
    assert messages_b[-1]["type"] == "playback_role"
    assert not await coordinator.acknowledge("b", "reply", "finished")
    assert await coordinator.acknowledge("a", "reply", "started")
    assert await coordinator.acknowledge("a", "reply", "finished")

    completed = await coordinator.wait_for_completion("reply", timeout=0.1)
    assert completed.status == "finished"
    assert any(message.get("is_owner") is True for message in messages_a)
    assert messages_b[-1]["is_owner"] is False


@pytest.mark.asyncio
async def test_playback_owner_disconnect_fails_active_reply_and_promotes_backup():
    coordinator = PlaybackCoordinator()

    async def notify(message):
        return None

    await coordinator.register("a", notify)
    await coordinator.register("b", notify)
    await coordinator.set_ready("a", True)
    await coordinator.set_ready("b", True)
    await coordinator.begin("reply")

    await coordinator.disconnect("a")
    completed = await coordinator.wait_for_completion("reply", timeout=0.1)

    assert completed.status == "failed"
    assert coordinator.owner_id == "b"
