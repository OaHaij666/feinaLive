"""Streaming host speech output: LLM -> sentence TTS -> room-scoped broadcast."""

from __future__ import annotations

import asyncio
import base64
import logging
import re
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.playback import PlaybackCoordinator, get_playback_coordinator
from apps.ai.tts import get_tts_client
from apps.config import config
from apps.live.room_session import RoomSessionContext, get_room_session_manager

logger = logging.getLogger(__name__)

ChunkBroadcaster = Callable[[RoomSessionContext, dict[str, Any]], Awaitable[None]]
PlaybackStartedCallback = Callable[[str], Awaitable[None]]


@dataclass
class SpeechChunk:
    type: str
    text: str = ""
    audio_data: bytes | None = None
    sentence_index: int = 0
    char_offset: int = 0
    is_final: bool = False

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"type": self.type, "is_final": self.is_final}
        if self.text:
            result["text"] = self.text
        if self.audio_data:
            result["audio"] = base64.b64encode(self.audio_data).decode("utf-8")
            result["sentence_index"] = self.sentence_index
            result["char_offset"] = self.char_offset
            result["char_length"] = len(self.text)
        return result


@dataclass(frozen=True)
class SpeechResult:
    text: str
    reply_id: str
    playback_status: str
    playback_error: str = ""

    @property
    def played(self) -> bool:
        return self.playback_status == "finished"


class SentenceBuffer:
    """Split streamed model output into complete spoken sentences."""

    _END_PATTERN = re.compile(r"[。！？!?~]+")

    def __init__(self) -> None:
        self.buffer = ""

    def add(self, text: str) -> list[str]:
        self.buffer += text
        sentences: list[str] = []
        while match := self._END_PATTERN.search(self.buffer):
            sentence = self.buffer[: match.end()].strip()
            if sentence:
                sentences.append(sentence)
            self.buffer = self.buffer[match.end() :]
        return sentences

    def flush(self) -> str:
        remaining = self.buffer.strip()
        self.buffer = ""
        return remaining


class SpeechPipeline:
    """Own one room-scoped streaming reply and all of its output side effects."""

    def __init__(
        self,
        broadcaster: ChunkBroadcaster | None = None,
        playback: PlaybackCoordinator | None = None,
    ) -> None:
        self._broadcaster = broadcaster or self._default_broadcast
        self._playback = playback or get_playback_coordinator()

    async def stream_reply(
        self,
        system_content: str,
        user_content: str,
        context: RoomSessionContext | None,
    ) -> SpeechResult | None:
        if context is None or not self._is_current(context):
            logger.debug("Skipped reply generation without a current room session")
            return None

        ai = get_ai_client()
        if not ai.available:
            logger.warning("AI 不可用，跳过话术生成")
            return None

        request = ChatRequest(
            messages=[
                ChatMessage(role="system", content=system_content),
                ChatMessage(role="user", content=user_content),
            ],
            model=config.host_model,
            temperature=config.host_temperature,
            top_p=config.host_top_p,
            max_tokens=config.host_max_tokens,
            disable_thinking=config.llm_disable_thinking,
            stream=True,
        )

        sentence_buffer = SentenceBuffer()
        full_response = ""
        sentence_index = 0
        char_offset = 0
        audio_chunks = 0
        tts_tasks: list[asyncio.Task[SpeechChunk | None]] = []
        reply_id = uuid.uuid4().hex
        chunk_seq = 0
        playback_session = await self._playback.begin(reply_id)
        playback_delivery_failed = False

        async def emit(chunk: dict[str, Any]) -> None:
            nonlocal chunk_seq, playback_delivery_failed
            chunk["reply_id"] = reply_id
            chunk["chunk_seq"] = chunk_seq
            chunk.setdefault("context", context.to_dict())
            chunk_seq += 1
            # Room subscribers observe an ordered metadata stream. Only the
            # elected playback client receives the base64 audio payload.
            if playback_session is not None and not playback_delivery_failed:
                playback_delivery_failed = not await self._playback.send_chunk(
                    reply_id,
                    dict(chunk),
                )
            observer_chunk = dict(chunk)
            if observer_chunk.get("type") == "audio":
                observer_chunk.pop("audio", None)
                observer_chunk["observer_only"] = True
            await self._broadcast(observer_chunk, context)

        await emit({
            "type": "start",
            "is_final": False,
            "playback_expected": playback_session is not None,
        })

        try:
            stream: AsyncIterator[str] = ai.chat_stream(request)
            async for chunk in stream:
                if not self._is_current(context):
                    logger.info("Cancelled reply because the active room session changed")
                    await self._playback.abort(reply_id, "room session changed")
                    return None

                remaining_chars = config.host_max_reply_length - len(full_response)
                if remaining_chars <= 0:
                    break
                accepted = chunk[:remaining_chars]
                full_response += accepted

                for sentence in sentence_buffer.add(accepted):
                    await emit(
                        {"type": "text", "text": sentence, "is_final": False},
                    )
                    tts_tasks.append(
                        asyncio.create_task(
                            self._synthesize_sentence(sentence, sentence_index, char_offset)
                        )
                    )
                    sentence_index += 1
                    char_offset += len(sentence)

                if len(accepted) < len(chunk):
                    break

            remaining = sentence_buffer.flush()
            if remaining:
                await emit(
                    {"type": "text", "text": remaining, "is_final": False},
                )
                tts_tasks.append(
                    asyncio.create_task(
                        self._synthesize_sentence(remaining, sentence_index, char_offset)
                    )
                )

            for task in tts_tasks:
                if not self._is_current(context):
                    await self._playback.abort(reply_id, "room session changed")
                    return None
                result = await task
                if result:
                    await emit(result.to_dict())
                    audio_chunks += 1

            if not self._is_current(context):
                await self._playback.abort(reply_id, "room session changed")
                return None

            await emit({
                "type": "end",
                "text": full_response,
                "is_final": True,
                "audio_chunks": audio_chunks,
            })

            if not full_response:
                await self._playback.abort(reply_id, "empty model response")
                return None
            if playback_session is None:
                return SpeechResult(
                    text=full_response,
                    reply_id=reply_id,
                    playback_status="no_owner",
                    playback_error="no ready playback owner",
                )
            if playback_delivery_failed:
                return SpeechResult(
                    text=full_response,
                    reply_id=reply_id,
                    playback_status="failed",
                    playback_error="playback channel disconnected during delivery",
                )
            if audio_chunks == 0:
                failed = await self._playback.abort(reply_id, "TTS produced no playable audio")
                return SpeechResult(
                    text=full_response,
                    reply_id=reply_id,
                    playback_status="failed",
                    playback_error=(failed.error if failed else "TTS produced no playable audio"),
                )

            completed = await self._playback.wait_for_completion(
                reply_id,
                timeout=config.host_playback_timeout_seconds,
            )
            return SpeechResult(
                text=full_response,
                reply_id=reply_id,
                playback_status=completed.status,
                playback_error=completed.error,
            )
        except asyncio.CancelledError:
            await self._playback.abort(reply_id, "reply generation cancelled")
            raise
        except Exception:
            await self._playback.abort(reply_id, "reply generation failed")
            raise
        finally:
            await self._cancel_pending(tts_tasks)

    async def speak_text(
        self,
        text: str,
        context: RoomSessionContext | None,
        *,
        on_playback_started: PlaybackStartedCallback | None = None,
    ) -> SpeechResult | None:
        """Speak already-final text without another LLM call.

        This is the Agent commentary entry point. The caller owns wording; this
        pipeline only performs sentence TTS, ordered delivery, and real browser
        playback acknowledgement.
        """

        final_text = text.strip()[: config.host_max_reply_length]
        if not final_text or context is None or not self._is_current(context):
            return None

        reply_id = uuid.uuid4().hex
        playback_session = await self._playback.begin(reply_id)
        chunk_seq = 0
        delivery_failed = False
        audio_chunks = 0
        started_task: asyncio.Task[None] | None = None

        async def emit(chunk: dict[str, Any]) -> None:
            nonlocal chunk_seq, delivery_failed
            chunk["reply_id"] = reply_id
            chunk["chunk_seq"] = chunk_seq
            chunk.setdefault("context", context.to_dict())
            chunk_seq += 1
            if playback_session is not None and not delivery_failed:
                delivery_failed = not await self._playback.send_chunk(reply_id, dict(chunk))
            observer_chunk = dict(chunk)
            if observer_chunk.get("type") == "audio":
                observer_chunk.pop("audio", None)
                observer_chunk["observer_only"] = True
            await self._broadcast(observer_chunk, context)

        async def notify_started() -> None:
            if await self._playback.wait_for_started(
                reply_id,
                timeout=config.host_playback_timeout_seconds,
            ) and on_playback_started:
                await on_playback_started(reply_id)

        await emit({"type": "start", "is_final": False, "playback_expected": playback_session is not None})
        if playback_session is not None and on_playback_started is not None:
            started_task = asyncio.create_task(notify_started())

        try:
            buffer = SentenceBuffer()
            sentences = buffer.add(final_text)
            remaining = buffer.flush()
            if remaining:
                sentences.append(remaining)

            char_offset = 0
            for sentence_index, sentence in enumerate(sentences):
                if not self._is_current(context):
                    await self._playback.abort(reply_id, "room session changed")
                    return None
                await emit({"type": "text", "text": sentence, "is_final": False})
                audio = await self._synthesize_sentence(sentence, sentence_index, char_offset)
                char_offset += len(sentence)
                if audio:
                    await emit(audio.to_dict())
                    audio_chunks += 1

            await emit({"type": "end", "text": final_text, "is_final": True, "audio_chunks": audio_chunks})
            if playback_session is None:
                return SpeechResult(final_text, reply_id, "no_owner", "no ready playback owner")
            if delivery_failed:
                await self._playback.abort(reply_id, "playback channel disconnected during delivery")
                return SpeechResult(final_text, reply_id, "failed", "playback channel disconnected during delivery")
            if audio_chunks == 0:
                await self._playback.abort(reply_id, "TTS produced no playable audio")
                return SpeechResult(final_text, reply_id, "failed", "TTS produced no playable audio")
            completed = await self._playback.wait_for_completion(
                reply_id,
                timeout=config.host_playback_timeout_seconds,
            )
            return SpeechResult(final_text, reply_id, completed.status, completed.error)
        except asyncio.CancelledError:
            await self._playback.abort(reply_id, "speech cancelled")
            raise
        except Exception:
            await self._playback.abort(reply_id, "speech delivery failed")
            raise
        finally:
            if started_task and not started_task.done():
                started_task.cancel()
                await asyncio.gather(started_task, return_exceptions=True)

    async def _synthesize_sentence(
        self,
        sentence: str,
        sentence_index: int,
        char_offset: int,
    ) -> SpeechChunk | None:
        try:
            result = await get_tts_client().synthesize(sentence)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TTS synthesis failed for sentence %s", sentence_index)
            return None
        if not result:
            return None
        return SpeechChunk(
            type="audio",
            text=sentence,
            audio_data=result.audio_data,
            sentence_index=sentence_index,
            char_offset=char_offset,
        )

    async def _broadcast(
        self,
        chunk: dict[str, Any],
        context: RoomSessionContext,
    ) -> None:
        if not self._is_current(context):
            logger.debug("Dropped reply chunk outside the current room session")
            return
        chunk.setdefault("context", context.to_dict())
        await self._broadcaster(context, chunk)

    @staticmethod
    async def _default_broadcast(
        context: RoomSessionContext,
        chunk: dict[str, Any],
    ) -> None:
        from core.websocket import manager as ws_manager

        await ws_manager.send_message(context.room_id, chunk)

    @staticmethod
    async def _cancel_pending(tasks: list[asyncio.Task[SpeechChunk | None]]) -> None:
        pending = [task for task in tasks if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    @staticmethod
    def _is_current(context: RoomSessionContext) -> bool:
        return get_room_session_manager().is_current(context)
