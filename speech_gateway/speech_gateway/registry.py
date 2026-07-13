"""Provider routing and explicit fallback orchestration."""

from __future__ import annotations

import logging

from speech_gateway.config import GatewayConfig, config
from speech_gateway.errors import (
    ProviderNotFoundError,
    ProviderUnavailableError,
    SpeechGatewayError,
)
from speech_gateway.models import SpeechArtifact, SpeechRequest
from speech_gateway.providers.base import SpeechProvider
from speech_gateway.providers.edge import EdgeSpeechProvider
from speech_gateway.providers.volcano import VolcanoSpeechProvider

logger = logging.getLogger(__name__)


class SpeechProviderRegistry:
    def __init__(
        self,
        providers: list[SpeechProvider] | None = None,
        settings: GatewayConfig = config,
    ) -> None:
        values = providers or [EdgeSpeechProvider(), VolcanoSpeechProvider()]
        self.providers = {provider.name: provider for provider in values}
        self.settings = settings

    def resolve_model(self, model: str) -> tuple[str, str]:
        if "/" in model:
            provider_name, provider_model = model.split("/", 1)
            return provider_name, provider_model
        return self.settings.default_provider, model

    def get(self, name: str) -> SpeechProvider:
        provider = self.providers.get(name)
        if provider is None:
            raise ProviderNotFoundError(f"Unknown speech provider '{name}'")
        if not provider.available:
            raise ProviderUnavailableError(f"Speech provider '{name}' is not configured")
        return provider

    async def synthesize(self, request: SpeechRequest) -> SpeechArtifact:
        primary, model = self.resolve_model(request.model)
        route = (primary, *self.settings.fallback_providers)
        last_error: SpeechGatewayError | None = None
        for provider_name in dict.fromkeys(route):
            try:
                return await self.get(provider_name).synthesize(request, model)
            except SpeechGatewayError as exc:
                last_error = exc
                logger.warning("Speech provider %s failed: %s", provider_name, exc)
        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError("No speech provider is available")

    async def close(self) -> None:
        for provider in self.providers.values():
            await provider.close()
