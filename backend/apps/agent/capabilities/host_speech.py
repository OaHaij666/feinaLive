from __future__ import annotations

import asyncio
import time

from apps.agent.mutual_context import MutualContext
from apps.ai.messaging.dynamic_priority import PRIORITY_HIGH
from apps.ai.messaging.queue import Message, PriorityMessageQueue, get_message_queue
from apps.ai.speech_jobs import (
    SpeechJob,
    SpeechJobCoordinator,
    SpeechJobStatus,
    get_speech_job_coordinator,
)
from apps.config import config
from apps.live.runtime import get_live_runtime


class HostSpeechCapability:
    """Final-text speech capability. It deliberately contains no LLM."""

    def __init__(
        self,
        mutual_context: MutualContext,
        queue: PriorityMessageQueue | None = None,
        jobs: SpeechJobCoordinator | None = None,
    ) -> None:
        self._mutual_context = mutual_context
        self._queue = queue or get_message_queue()
        self._jobs = jobs or get_speech_job_coordinator()

    async def speak(
        self,
        text: str,
        *,
        started: asyncio.Event | None = None,
    ) -> SpeechJob | None:
        context = get_live_runtime().active_context
        final_text = text.strip()
        if not final_text or context is None:
            return None
        job = await self._jobs.create(final_text)
        hold_seconds = config.host_playback_timeout_seconds + 60.0
        accepted = await self._queue.put(
            Message(
                priority=PRIORITY_HIGH,
                source="agent",
                msg_type="prepared_speech",
                content=final_text,
                data={"speech_job_id": job.job_id},
                context=context.to_dict(),
                expire_at=time.time() + hold_seconds,
                allow_skip=False,
                cancel_key=f"speech_{job.job_id}",
            )
        )
        if not accepted:
            await self._jobs.finish(
                job.job_id,
                SpeechJobStatus.DROPPED,
                error="prepared speech was rejected by the consumer queue",
            )
            return job

        try:
            if started is not None:
                if await self._jobs.wait_started(job, timeout=hold_seconds):
                    started.set()
            result = await self._jobs.wait_finished(job, timeout=hold_seconds)
            if result.status is SpeechJobStatus.FAILED and "timed out" in result.error:
                self._queue.cancel(f"speech_{job.job_id}")
            return result
        except asyncio.CancelledError:
            self._queue.cancel(f"speech_{job.job_id}")
            await self._jobs.finish(
                job.job_id,
                SpeechJobStatus.CANCELLED,
                error="Agent speech waiter was cancelled",
            )
            raise
