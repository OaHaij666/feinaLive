"""Stable provider-neutral speech contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, Field


class SpeechRequest(BaseModel):
    model: str
    input: str = Field(min_length=1, max_length=10000)
    voice: str = ""
    response_format: str = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=4.0)
    extensions: dict[str, Any] = Field(default_factory=dict)


@dataclass(frozen=True)
class SpeechArtifact:
    audio: bytes
    media_type: str
    provider: str
    model: str
    voice: str
    sample_rate: int | None = None
    duration_ms: int | None = None
    timings: list[dict[str, Any]] = field(default_factory=list)
    synthesis_ms: int | None = None
    rtf: float | None = None
    fallback_from: str = ""
    attempts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderCapabilities:
    provider: str
    formats: tuple[str, ...]
    streaming: bool
    speed: bool
    pitch: bool
    emotion: bool
    word_timings: bool
    voice_listing: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "formats": list(self.formats),
            "streaming": self.streaming,
            "speed": self.speed,
            "pitch": self.pitch,
            "emotion": self.emotion,
            "word_timings": self.word_timings,
            "voice_listing": self.voice_listing,
        }
