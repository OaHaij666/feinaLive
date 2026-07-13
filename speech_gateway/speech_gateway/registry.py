"""Configured routing, classified fallback, circuit breaking, and metrics."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from speech_gateway.audio import duration_ms
from speech_gateway.config import GatewayConfig, ProviderConfig, config
from speech_gateway.errors import (
    CircuitOpenError,
    InvalidSpeechRequestError,
    ProviderNotFoundError,
    ProviderUnavailableError,
    SpeechGatewayError,
)
from speech_gateway.metrics import MetricsStore
from speech_gateway.models import SpeechArtifact, SpeechRequest
from speech_gateway.providers.base import SpeechProvider
from speech_gateway.providers.edge import EdgeSpeechProvider
from speech_gateway.providers.openai_compatible import OpenAICompatibleSpeechProvider
from speech_gateway.providers.volcano import VolcanoSpeechProvider

logger = logging.getLogger(__name__)


@dataclass
class CircuitState:
    consecutive_failures: int = 0
    open_until: float = 0.0

    def status(self, now: float) -> str:
        if self.open_until > now:
            return "open"
        if self.open_until:
            return "half_open"
        return "closed"


def build_provider(settings: ProviderConfig) -> SpeechProvider:
    if settings.type == "edge":
        return EdgeSpeechProvider(settings)
    if settings.type == "volcano":
        return VolcanoSpeechProvider(settings)
    if settings.type == "openai_compatible":
        return OpenAICompatibleSpeechProvider(settings)
    raise ValueError(f"Unknown speech provider type '{settings.type}' for '{settings.name}'")


class SpeechProviderRegistry:
    def __init__(
        self,
        providers: list[SpeechProvider] | None = None,
        settings: GatewayConfig = config,
    ) -> None:
        values = providers if providers is not None else [
            build_provider(provider)
            for provider in settings.providers.values()
            if provider.enabled
        ]
        self.providers = {provider.name: provider for provider in values}
        self.settings = settings
        self.metrics = MetricsStore(settings.metrics_sample_size)
        self.circuits = {name: CircuitState() for name in self.providers}

    def resolve_route(self, model: str) -> tuple[str, ...]:
        if model in self.settings.routes:
            route = self.settings.routes[model]
            if not route.primary:
                raise InvalidSpeechRequestError(f"Speech route '{model}' has no primary target")
            return (route.primary, *route.fallback)
        if "/" in model:
            return (model,)
        return (f"{self.settings.default_provider}/{model}",)

    @staticmethod
    def split_target(target: str) -> tuple[str, str]:
        if "/" not in target:
            raise InvalidSpeechRequestError(
                f"Speech target '{target}' must use provider/model format"
            )
        provider_name, provider_model = target.split("/", 1)
        if not provider_name or not provider_model:
            raise InvalidSpeechRequestError(f"Invalid speech target '{target}'")
        return provider_name, provider_model

    def get(self, name: str) -> SpeechProvider:
        provider = self.providers.get(name)
        if provider is None:
            if name in self.settings.providers:
                raise ProviderUnavailableError(f"Speech provider '{name}' is disabled")
            raise ProviderNotFoundError(f"Unknown speech provider '{name}'")
        if not provider.available:
            raise ProviderUnavailableError(f"Speech provider '{name}' is not configured")
        state = self.circuits[name]
        now = time.monotonic()
        if state.open_until > now:
            remaining = state.open_until - now
            raise CircuitOpenError(
                f"Speech provider '{name}' circuit is open for another {remaining:.1f}s"
            )
        return provider

    async def synthesize(self, request: SpeechRequest) -> SpeechArtifact:
        targets = self.resolve_route(request.model)
        attempts: list[str] = []
        last_error: SpeechGatewayError | None = None
        for index, target in enumerate(dict.fromkeys(targets)):
            provider_name, provider_model = self.split_target(target)
            attempts.append(target)
            metrics = self.metrics.provider(provider_name)
            metrics.requests += 1
            started = time.perf_counter()
            try:
                provider = self.get(provider_name)
                provider_request = (
                    request.model_copy(update={"voice": ""}) if index > 0 else request
                )
                artifact = await provider.synthesize(provider_request, provider_model)
            except SpeechGatewayError as exc:
                elapsed = (time.perf_counter() - started) * 1000
                metrics.failures += 1
                metrics.latency_ms.append(elapsed)
                metrics.errors[exc.code] += 1
                if exc.retryable and not isinstance(exc, CircuitOpenError):
                    self._record_retryable_failure(provider_name)
                last_error = exc
                logger.warning("Speech target %s failed: %s", target, exc)
                if not exc.retryable:
                    raise
                continue

            elapsed = (time.perf_counter() - started) * 1000
            self._record_success(provider_name)
            metrics.successes += 1
            metrics.latency_ms.append(elapsed)
            measured_duration = artifact.duration_ms or duration_ms(artifact.audio)
            rtf = elapsed / measured_duration if measured_duration else None
            if rtf is not None:
                metrics.rtf.append(rtf)
            if index > 0:
                metrics.fallbacks += 1
            return replace(
                artifact,
                duration_ms=measured_duration,
                synthesis_ms=round(elapsed),
                rtf=round(rtf, 4) if rtf is not None else None,
                fallback_from=targets[0] if index > 0 else "",
                attempts=tuple(attempts),
            )

        if last_error is not None:
            raise last_error
        raise ProviderUnavailableError("No speech provider is available")

    def _record_retryable_failure(self, provider_name: str) -> None:
        state = self.circuits.get(provider_name)
        if state is None:
            return
        state.consecutive_failures += 1
        if state.consecutive_failures >= self.settings.circuit_failure_threshold:
            state.open_until = time.monotonic() + self.settings.circuit_recovery_seconds

    def _record_success(self, provider_name: str) -> None:
        state = self.circuits.get(provider_name)
        if state is not None:
            state.consecutive_failures = 0
            state.open_until = 0.0

    async def probe(self, provider_name: str) -> bool:
        provider = self.providers.get(provider_name)
        if provider is None:
            raise ProviderNotFoundError(f"Unknown speech provider '{provider_name}'")
        healthy = await provider.health()
        if healthy:
            self._record_success(provider_name)
        return healthy

    def status(self) -> dict:
        now = time.monotonic()
        metrics = self.metrics.snapshot()
        return {
            "providers": {
                name: {
                    "type": self.settings.providers.get(name).type
                    if name in self.settings.providers
                    else "test",
                    "configured": provider.available,
                    "circuit": self.circuits[name].status(now),
                    "consecutive_failures": self.circuits[name].consecutive_failures,
                    "retry_after_seconds": round(max(0.0, self.circuits[name].open_until - now), 2),
                    "metrics": metrics.get(name, {}),
                }
                for name, provider in self.providers.items()
            },
            "routes": {
                name: {"primary": route.primary, "fallback": list(route.fallback)}
                for name, route in self.settings.routes.items()
            },
        }

    async def close(self) -> None:
        for provider in self.providers.values():
            await provider.close()
