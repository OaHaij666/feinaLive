"""Volcano Engine V3 streaming TTS adapter."""

from __future__ import annotations

import base64
import binascii
import json
import math
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
    "pcm": "audio/L16",
    "ogg_opus": "audio/ogg",
}
_SUCCESS_CODE = 20_000_000
_ENDPOINT = "/api/v3/tts/unidirectional/sse"


def _ratio_to_rate(value: float, name: str) -> int:
    """Map the gateway's multiplier to Volcano's documented [-50, 100] scale."""

    if not 0.5 <= value <= 2.0:
        raise InvalidSpeechRequestError(f"Volcano {name} must be between 0.5 and 2.0")
    return round((value - 1.0) * 100)


def _pitch_ratio_to_semitones(value: float) -> int:
    if not 0.5 <= value <= 2.0:
        raise InvalidSpeechRequestError("Volcano pitch must be between 0.5 and 2.0")
    return round(12 * math.log2(value))


class VolcanoSpeechProvider:
    name = "volcano"

    def __init__(self, settings: ProviderConfig) -> None:
        self.name = settings.name
        self.settings = settings
        self.api_key = settings.api_key
        self.default_voice = settings.default_voice
        self.resource_id = str(settings.options.get("resource_id", "seed-icl-2.0")).strip()
        self.sample_rate = int(settings.options.get("sample_rate", 24000))
        self._client = httpx.AsyncClient(
            base_url="https://openspeech.bytedance.com",
            timeout=httpx.Timeout(settings.timeout_seconds),
            headers={"Accept-Encoding": "identity"},
        )

    @property
    def available(self) -> bool:
        return bool(self.api_key and self.resource_id and self.default_voice)

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
            raise ProviderUnavailableError(
                "Volcano API Key, resource ID, or default speaker is missing"
            )
        if request.response_format not in _MEDIA_TYPES:
            raise UnsupportedCapabilityError(
                f"Volcano V3 does not support format '{request.response_format}'"
            )
        if request.extensions.get("emotion"):
            raise UnsupportedCapabilityError("This Volcano adapter does not map emotion presets")
        if request.extensions.get("return_word_timings"):
            raise UnsupportedCapabilityError("Volcano word timings are not enabled by this adapter")

        voice = request.voice or self.default_voice
        audio_params: dict[str, object] = {
            "format": request.response_format,
            "sample_rate": self.sample_rate,
            "speech_rate": _ratio_to_rate(request.speed, "speed"),
        }
        volume = float(request.extensions.get("volume", 1.0))
        audio_params["loudness_rate"] = _ratio_to_rate(volume, "volume")
        pitch = float(request.extensions.get("pitch", 1.0))
        additions = {"post_process": {"pitch": _pitch_ratio_to_semitones(pitch)}}
        payload = {
            "user": {"uid": "speech_gateway"},
            "req_params": {
                "text": request.input,
                "speaker": voice,
                "audio_params": audio_params,
                "additions": json.dumps(additions, ensure_ascii=False),
            },
        }
        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": str(uuid.uuid4()),
        }
        chunks: list[bytes] = []
        finished = False
        try:
            async with self._client.stream(
                "POST", _ENDPOINT, json=payload, headers=headers
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    self._raise_http_error(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if not raw:
                        continue
                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise SynthesisError("Volcano returned malformed SSE JSON") from exc
                    code = int(event.get("code", -1))
                    if code == 0 and event.get("data"):
                        try:
                            chunks.append(base64.b64decode(event["data"], validate=True))
                        except (binascii.Error, ValueError) as exc:
                            raise SynthesisError("Volcano returned invalid base64 audio") from exc
                    elif code == _SUCCESS_CODE:
                        finished = True
                    elif code != 0:
                        self._raise_event_error(code, str(event.get("message", "")))
        except httpx.HTTPError as exc:
            raise SynthesisError("Volcano TTS network request failed") from exc

        if not chunks:
            raise SynthesisError("Volcano returned no audio")
        if not finished:
            raise SynthesisError("Volcano TTS stream ended before the success event")
        return SpeechArtifact(
            audio=b"".join(chunks),
            media_type=_MEDIA_TYPES[request.response_format],
            provider=self.name,
            model=model or self.resource_id,
            voice=voice,
            sample_rate=self.sample_rate,
        )

    @staticmethod
    def _raise_http_error(response: httpx.Response) -> None:
        if response.status_code in {401, 403}:
            raise UpstreamAuthenticationError("Volcano rejected its configured API Key")
        if response.status_code == 429:
            raise UpstreamRateLimitError("Volcano rate limit exceeded")
        if 400 <= response.status_code < 500:
            raise InvalidSpeechRequestError(
                f"Volcano rejected the speech request with HTTP {response.status_code}"
            )
        raise SynthesisError(f"Volcano returned HTTP {response.status_code}")

    @staticmethod
    def _raise_event_error(code: int, message: str) -> None:
        detail = message or f"Volcano error {code}"
        lowered = detail.lower()
        if "permission" in lowered or "access denied" in lowered or "auth" in lowered:
            raise UpstreamAuthenticationError(detail)
        if "quota" in lowered or "concurrency" in lowered or "rate" in lowered:
            raise UpstreamRateLimitError(detail)
        if str(code).startswith("4"):
            raise InvalidSpeechRequestError(detail)
        raise SynthesisError(detail)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self) -> bool:
        if not self.available:
            return False
        try:
            await self.synthesize(
                SpeechRequest(
                    model=f"{self.name}/{self.resource_id}",
                    input="测试",
                    voice=self.default_voice,
                    response_format="mp3",
                ),
                self.resource_id,
            )
            return True
        except Exception:
            return False
