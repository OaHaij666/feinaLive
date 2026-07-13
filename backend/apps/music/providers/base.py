from __future__ import annotations

from enum import Enum
from typing import Protocol

from apps.music.models import AudioStream, ProviderSearchResult, Track


class ProviderTrustPolicy(str, Enum):
    """Whether a provider's native catalog is inherently music-only."""

    NATIVE_MUSIC = "native_music"
    REVIEW_REQUIRED = "review_required"


class MusicProvider(Protocol):
    id: str
    trust_policy: ProviderTrustPolicy

    async def search(self, query: str, limit: int = 10) -> list[ProviderSearchResult]: ...

    async def inspect(self, source_id: str) -> Track: ...

    async def resolve_stream(self, source_id: str) -> AudioStream: ...
