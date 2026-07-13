from __future__ import annotations

from apps.music.providers.base import MusicProvider


class MusicProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, MusicProvider] = {}

    def register(self, provider: MusicProvider) -> None:
        if provider.id in self._providers:
            raise ValueError(f"Music provider already registered: {provider.id}")
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> MusicProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            raise ValueError(f"Unknown music provider: {provider_id}") from exc

    def list_ids(self) -> list[str]:
        return sorted(self._providers)
