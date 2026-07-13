"""Speech artifacts consumed by the live playback pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SpeechArtifact:
    audio_data: bytes
    text: str
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
