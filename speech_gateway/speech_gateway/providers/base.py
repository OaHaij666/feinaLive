"""Provider protocol."""

from __future__ import annotations

from typing import Protocol

from speech_gateway.models import ProviderCapabilities, SpeechArtifact, SpeechRequest


class SpeechProvider(Protocol):
    name: str

    @property
    def available(self) -> bool: ...

    def capabilities(self) -> ProviderCapabilities: ...

    async def voices(self) -> list[dict]: ...

    async def health(self) -> bool: ...

    async def synthesize(self, request: SpeechRequest, model: str) -> SpeechArtifact: ...

    async def close(self) -> None: ...
