from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


class SpeechJobStatus(str, Enum):
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    DROPPED = "dropped"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class SpeechJob:
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: SpeechJobStatus = SpeechJobStatus.QUEUED
    text: str = ""
    reply_id: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    started_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    terminal_event: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    @property
    def played(self) -> bool:
        return self.status is SpeechJobStatus.FINISHED

    @property
    def terminal(self) -> bool:
        return self.status in {
            SpeechJobStatus.FINISHED,
            SpeechJobStatus.FAILED,
            SpeechJobStatus.DROPPED,
            SpeechJobStatus.CANCELLED,
        }


class SpeechJobCoordinator:
    """Correlate queued final text with real playback started/finished ACKs."""

    def __init__(self, retention_seconds: float = 300.0) -> None:
        self._jobs: dict[str, SpeechJob] = {}
        self._retention_seconds = retention_seconds
        self._lock = asyncio.Lock()

    async def create(self, text: str) -> SpeechJob:
        async with self._lock:
            self._prune_locked(time.time())
            job = SpeechJob(text=text)
            self._jobs[job.job_id] = job
            return job

    async def get(self, job_id: str) -> SpeechJob | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def started(self, job_id: str, reply_id: str) -> SpeechJob | None:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.terminal:
                return job
            job.status = SpeechJobStatus.STARTED
            job.reply_id = reply_id
            job.updated_at = time.time()
            job.started_event.set()
            return job

    async def finish(
        self,
        job_id: str,
        status: SpeechJobStatus,
        *,
        reply_id: str = "",
        error: str = "",
    ) -> SpeechJob | None:
        if status not in {
            SpeechJobStatus.FINISHED,
            SpeechJobStatus.FAILED,
            SpeechJobStatus.DROPPED,
            SpeechJobStatus.CANCELLED,
        }:
            raise ValueError(f"not a terminal speech status: {status}")
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            job.status = status
            job.reply_id = reply_id or job.reply_id
            job.error = error
            job.updated_at = time.time()
            job.terminal_event.set()
            return job

    async def wait_started(self, job: SpeechJob, timeout: float) -> bool:
        if job.status in {SpeechJobStatus.STARTED, SpeechJobStatus.FINISHED}:
            return True
        started_wait = asyncio.create_task(job.started_event.wait())
        terminal_wait = asyncio.create_task(job.terminal_event.wait())
        try:
            done, _ = await asyncio.wait(
                {started_wait, terminal_wait},
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )
            return started_wait in done and job.started_event.is_set()
        finally:
            for task in (started_wait, terminal_wait):
                if not task.done():
                    task.cancel()
            await asyncio.gather(started_wait, terminal_wait, return_exceptions=True)

    async def wait_finished(self, job: SpeechJob, timeout: float) -> SpeechJob:
        if not job.terminal:
            try:
                await asyncio.wait_for(job.terminal_event.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                await self.finish(
                    job.job_id,
                    SpeechJobStatus.FAILED,
                    error="speech queue/playback acknowledgement timed out",
                )
        return job

    def _prune_locked(self, now: float) -> None:
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if job.terminal and now - job.updated_at > self._retention_seconds
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)


_speech_jobs: SpeechJobCoordinator | None = None


def get_speech_job_coordinator() -> SpeechJobCoordinator:
    global _speech_jobs
    if _speech_jobs is None:
        _speech_jobs = SpeechJobCoordinator()
    return _speech_jobs
