"""HTTP client for the independently deployed Feina Speech Gateway."""

from __future__ import annotations

import json
import logging

import httpx

from apps.config import config
from apps.speech.models import SpeechArtifact

logger = logging.getLogger(__name__)


def _optional_int(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


class SpeechGatewayClient:
    def __init__(
        self,
        gateway_url: str = "",
        api_key: str = "",
        model: str = "",
        voice: str = "",
        response_format: str = "",
        speed: float | None = None,
        timeout_seconds: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        base_url = (gateway_url or config.tts_gateway_url).rstrip("/") + "/"
        self.gateway_url = base_url
        self.health_url = base_url.removesuffix("v1/") + "health"
        self.api_key = api_key or config.tts_api_key or ""
        self.model = model or config.tts_model
        self.voice = voice or config.tts_voice
        self.response_format = response_format or config.tts_response_format
        self.speed = speed if speed is not None else config.tts_speed
        timeout = timeout_seconds if timeout_seconds is not None else config.tts_timeout_seconds
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout),
            transport=transport,
        )

    @property
    def available(self) -> bool:
        return bool(self.gateway_url and self.model and self.voice)

    async def synthesize(self, text: str) -> SpeechArtifact | None:
        text = text.strip()
        if not text or not self.available:
            return None
        try:
            response = await self._client.post(
                "audio/speech",
                json={
                    "model": self.model,
                    "input": text,
                    "voice": self.voice,
                    "response_format": self.response_format,
                    "speed": self.speed,
                },
            )
            response.raise_for_status()
            if not response.content:
                logger.error("Speech Gateway returned an empty audio response")
                return None
            timings: list[dict] = []
            if encoded_timings := response.headers.get("X-Speech-Timings"):
                try:
                    parsed = json.loads(encoded_timings)
                    if isinstance(parsed, list):
                        timings = parsed
                except json.JSONDecodeError:
                    logger.warning("Speech Gateway returned malformed timing metadata")
            return SpeechArtifact(
                audio_data=response.content,
                text=text,
                media_type=response.headers.get("content-type", "application/octet-stream").split(";", 1)[0],
                provider=response.headers.get("X-Speech-Provider", ""),
                model=response.headers.get("X-Speech-Model", self.model),
                voice=response.headers.get("X-Speech-Voice", self.voice),
                sample_rate=_optional_int(response.headers.get("X-Speech-Sample-Rate")),
                duration_ms=_optional_int(response.headers.get("X-Speech-Duration-Ms")),
                timings=timings,
            )
        except httpx.HTTPStatusError as exc:
            logger.error(
                "Speech Gateway rejected synthesis with HTTP %s: %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
        except httpx.HTTPError:
            logger.exception("Speech Gateway request failed")
        return None

    async def health(self) -> bool:
        try:
            response = await self._client.get(self.health_url)
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self._client.aclose()


_speech_gateway_client: SpeechGatewayClient | None = None


def get_speech_gateway_client() -> SpeechGatewayClient:
    global _speech_gateway_client
    if _speech_gateway_client is None:
        _speech_gateway_client = SpeechGatewayClient()
    return _speech_gateway_client
