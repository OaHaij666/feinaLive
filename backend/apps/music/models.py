from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClassificationVerdict(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    REVIEW = "review"


class DecisionSource(str, Enum):
    CACHE = "cache"
    RULES = "rules"
    LLM = "llm"
    PROVIDER = "provider"


class QueueEntryStatus(str, Enum):
    PENDING = "pending"
    PLAYING = "playing"
    PAUSED = "paused"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlaybackEventType(str, Enum):
    STARTED = "started"
    PAUSED = "paused"
    RESUMED = "resumed"
    ENDED = "ended"
    FAILED = "failed"


class Evidence(BaseModel):
    code: str
    weight: int
    value: str = ""


class ClassificationDecision(BaseModel):
    verdict: ClassificationVerdict
    rule_score: int = 0
    has_conflict: bool = False
    confidence: float | None = None
    source: DecisionSource = DecisionSource.RULES
    reviewed_by_llm: bool = False
    title: str = ""
    artists: list[str] = Field(default_factory=list)
    reason: str = ""
    evidence: list[Evidence] = Field(default_factory=list)


class Track(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    provider: str
    source_id: str
    title: str
    artists: list[str] = Field(default_factory=list)
    duration_seconds: int
    cover_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueueEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    track: Track
    requested_by: str
    request_id: str = ""
    status: QueueEntryStatus = QueueEntryStatus.PENDING
    requested_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    failure_reason: str = ""


class MusicState(BaseModel):
    revision: int
    current: QueueEntry | None
    queue: list[QueueEntry]
    paused: bool
    volume: float
    ducking_factor: float
    ducking_enabled: bool
    effective_volume: float
    playback_owner_id: str | None = None


class MusicRequest(BaseModel):
    query: str
    requested_by: str
    provider: str = "auto"
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    direct_source_id: str | None = None


class MusicRequestResult(BaseModel):
    accepted: bool
    intercepted: bool = True
    entry: QueueEntry | None = None
    error_code: str = ""
    error: str = ""
    classification: ClassificationDecision | None = None


class ProviderSearchResult(BaseModel):
    source_id: str
    title: str
    artist: str = ""
    duration_seconds: int = 0
    cover_url: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudioStream(BaseModel):
    url: str = ""
    local_path: str = ""
    media_type: str = "audio/mp4"
    headers: dict[str, str] = Field(default_factory=dict)
    allowed_host_suffixes: list[str] = Field(default_factory=list)
