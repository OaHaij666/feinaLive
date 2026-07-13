"""Volcano Engine voice-cloning TTS adapter."""

from __future__ import annotations

import base64
import uuid

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

_MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "pcm": "audio/L16",
    "ogg_opus": "audio/ogg",
}


class VolcanoSpeechProvider:
    name = "volcano"

    def __init__(self, settings: ProviderConfig) -> None:
        self.name = settings.name
        self.settings = settings
        appid_env = str(settings.options.get("appid_env", "VOLCANO_APPID"))
        token_env = str(settings.options.get("access_token_env", "VOLCANO_ACCESS_TOKEN"))
        import os

        self.appid = os.getenv(appid_env, "").strip() or str(settings.options.get("appid", ""))
        self.access_token = (
            os.getenv(token_env, "").strip() or settings.secrets.get("access_token", "")
        )
        self.default_voice = settings.default_voice
        self.cluster = str(settings.options.get("cluster", "volcano_icl"))
        self._client = httpx.AsyncClient(
            base_url="https://openspeech.bytedance.com",
            timeout=httpx.Timeout(settings.timeout_seconds),
            headers={"Accept-Encoding": "identity"},
        )

    @property
    def available(self) -> bool:
        return bool(self.appid and self.access_token and self.default_voice)

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            formats=tuple(_MEDIA_TYPES),
            streaming=False,
            speed=True,
            pitch=True,
            emotion=False,
            word_timings=False,
            voice_listing=False,
        )

    async def voices(self) -> list[dict]:
        if not self.default_voice:
            return []
        return [{"id": self.default_voice, "name": self.default_voice, "provider": self.name}]

    async def synthesize(self, request: SpeechRequest, model: str) -> SpeechArtifact:
        if not self.available:
            raise ProviderUnavailableError("Volcano credentials or default voice are missing")
        if request.response_format not in _MEDIA_TYPES:
            raise UnsupportedCapabilityError(
                f"Volcano does not support format '{request.response_format}'"
            )
        if request.extensions.get("emotion"):
            raise UnsupportedCapabilityError("This Volcano adapter does not map emotion presets")
        if request.extensions.get("return_word_timings"):
            raise UnsupportedCapabilityError("Volcano word timings are not available on this endpoint")

        voice = request.voice or self.default_voice
        payload = {
            "app": {"appid": self.appid, "token": "access_token", "cluster": self.cluster},
            "user": {"uid": "speech_gateway"},
            "audio": {
                "voice_type": voice,
                "encoding": request.response_format,
                "speed_ratio": request.speed,
                "volume_ratio": float(request.extensions.get("volume", 1.0)),
                "pitch_ratio": float(request.extensions.get("pitch", 1.0)),
            },
            "request": {
                "reqid": uuid.uuid4().hex,
                "text": request.input,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson",
            },
        }
        try:
            response = await self._client.post(
                "/api/v1/tts",
                json=payload,
                headers={"Authorization": f"Bearer;{self.access_token}"},
            )
        except httpx.HTTPError as exc:
            raise SynthesisError("Volcano TTS network request failed") from exc
        if response.status_code != 200:
            if response.status_code in {401, 403}:
                raise UpstreamAuthenticationError("Volcano rejected its configured credentials")
            if response.status_code == 429:
                raise UpstreamRateLimitError("Volcano rate limit exceeded")
            if 400 <= response.status_code < 500:
                raise InvalidSpeechRequestError(
                    f"Volcano rejected the speech request with HTTP {response.status_code}"
                )
            raise SynthesisError(f"Volcano returned HTTP {response.status_code}: {response.text[:300]}")
        try:
            result = response.json()
        except ValueError as exc:
            raise SynthesisError("Volcano returned malformed JSON") from exc
        encoded = result.get("data")
        if not encoded:
            raise SynthesisError(result.get("message") or "Volcano returned no audio")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise SynthesisError("Volcano returned invalid base64 audio") from exc
        return SpeechArtifact(
            audio=audio,
            media_type=_MEDIA_TYPES[request.response_format],
            provider=self.name,
            model=model or "volcano-tts",
            voice=voice,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        if not self.available:
            return False
        try:
            await self.synthesize(
                SpeechRequest(
                    model=f"{self.name}/volcano-tts",
                    input="测试",
                    voice=self.default_voice,
                    response_format="mp3",
                ),
                "volcano-tts",
            )
            return True
        except Exception:
            return False
