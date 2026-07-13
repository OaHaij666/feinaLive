"""Generic adapter for any OpenAI-compatible `/v1/audio/speech` service."""

from __future__ import annotations

import json

import httpx

from speech_gateway.config import ProviderConfig
from speech_gateway.errors import (
    InvalidSpeechRequestError,
    ProviderUnavailableError,
    SynthesisError,
    UnsupportedCapabilityError,
    UpstreamAuthenticationError,
    UpstreamRateLimitError,
)
from speech_gateway.models import ProviderCapabilities, SpeechArtifact, SpeechRequest


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


class OpenAICompatibleSpeechProvider:
    def __init__(
        self,
        settings: ProviderConfig,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.name = settings.name
        self.settings = settings
        headers = {"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {}
        self._client = httpx.AsyncClient(
            base_url=settings.base_url.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(settings.timeout_seconds),
            transport=transport,
        )

    @property
    def available(self) -> bool:
        return bool(self.settings.enabled and self.settings.base_url)

    def capabilities(self) -> ProviderCapabilities:
        options = self.settings.options
        return ProviderCapabilities(
            provider=self.name,
            formats=self.settings.formats,
            streaming=bool(options.get("streaming", False)),
            speed=bool(options.get("speed", True)),
            pitch=bool(options.get("pitch", False)),
            emotion=bool(options.get("emotion", False)),
            word_timings=bool(options.get("word_timings", False)),
            voice_listing=bool(options.get("voice_listing", False)),
        )

    async def voices(self) -> list[dict]:
        if not self.capabilities().voice_listing:
            return []
        path = str(self.settings.options.get("voices_path", "voices")).lstrip("/")
        response = await self._request("GET", path)
        payload = response.json()
        values = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise SynthesisError(f"Provider '{self.name}' returned an invalid voice list")
        return [dict(item, provider=self.name) for item in values if isinstance(item, dict)]

    async def synthesize(self, request: SpeechRequest, model: str) -> SpeechArtifact:
        if not self.available:
            raise ProviderUnavailableError(f"Provider '{self.name}' has no base_url")
        capabilities = self.capabilities()
        if request.response_format not in capabilities.formats:
            raise UnsupportedCapabilityError(
                f"Provider '{self.name}' does not support '{request.response_format}'"
            )
        if request.speed != 1.0 and not capabilities.speed:
            raise UnsupportedCapabilityError(f"Provider '{self.name}' does not support speed")
        capability_fields = {
            "pitch": capabilities.pitch,
            "emotion": capabilities.emotion,
            "return_word_timings": capabilities.word_timings,
        }
        for field, supported in capability_fields.items():
            if request.extensions.get(field) and not supported:
                raise UnsupportedCapabilityError(
                    f"Provider '{self.name}' does not support '{field}'"
                )
        payload = {
            "model": model,
            "input": request.input,
            "voice": request.voice or self.settings.default_voice,
            "response_format": request.response_format,
            "speed": request.speed,
        }
        payload.update(
            {key: value for key, value in request.extensions.items() if key not in payload}
        )
        response = await self._request("POST", "audio/speech", json=payload)
        if not response.content:
            raise SynthesisError(f"Provider '{self.name}' returned no audio")
        timings = []
        if encoded := response.headers.get("X-Speech-Timings"):
            try:
                decoded = json.loads(encoded)
                timings = decoded if isinstance(decoded, list) else []
            except json.JSONDecodeError:
                pass
        return SpeechArtifact(
            audio=response.content,
            media_type=response.headers.get("content-type", "application/octet-stream").split(";", 1)[0],
            provider=self.name,
            model=response.headers.get("X-Speech-Model", model),
            voice=response.headers.get("X-Speech-Voice", payload["voice"]),
            sample_rate=_optional_int(response.headers.get("X-Speech-Sample-Rate")),
            duration_ms=_optional_int(response.headers.get("X-Speech-Duration-Ms")),
            timings=timings,
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise SynthesisError(f"Provider '{self.name}' network request failed") from exc
        if response.status_code in {401, 403}:
            raise UpstreamAuthenticationError(
                f"Provider '{self.name}' rejected its configured credentials"
            )
        if response.status_code == 429:
            raise UpstreamRateLimitError(f"Provider '{self.name}' rate limit exceeded")
        if 400 <= response.status_code < 500:
            raise InvalidSpeechRequestError(
                f"Provider '{self.name}' rejected the request with HTTP {response.status_code}"
            )
        if response.status_code >= 500:
            raise SynthesisError(
                f"Provider '{self.name}' failed with HTTP {response.status_code}"
            )
        return response

    async def health(self) -> bool:
        if not self.available:
            return False
        path = self.settings.health_path or "models"
        try:
            await self._request("GET", path.lstrip("/"))
            return True
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
