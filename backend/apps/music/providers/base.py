from __future__ import annotations

from typing import Protocol

from apps.music.models import AudioStream, ProviderSearchResult, Track


class MusicProvider(Protocol):
    id: str

    async def search(self, query: str, limit: int = 10) -> list[ProviderSearchResult]: ...

    async def inspect(self, source_id: str) -> Track: ...

    async def resolve_stream(self, source_id: str) -> AudioStream: ...
