"""Microsoft Edge online TTS adapter using the maintained edge-tts client."""

from __future__ import annotations

import edge_tts

from speech_gateway.config import ProviderConfig
from speech_gateway.errors import SynthesisError, UnsupportedCapabilityError
from speech_gateway.models import ProviderCapabilities, SpeechArtifact, SpeechRequest


class EdgeSpeechProvider:
    name = "edge"

    def __init__(self, settings: ProviderConfig) -> None:
        self.name = settings.name
        self.settings = settings
        self.default_voice = settings.default_voice or "zh-CN-XiaoxiaoNeural"

    @property
    def available(self) -> bool:
        return True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider=self.name,
            formats=("mp3",),
            streaming=False,
            speed=True,
            pitch=True,
            emotion=False,
            word_timings=False,
            voice_listing=True,
        )

    async def voices(self) -> list[dict]:
        try:
            return [
                {
                    "id": voice["ShortName"],
                    "name": voice.get("FriendlyName", voice["ShortName"]),
                    "locale": voice.get("Locale", ""),
                    "gender": voice.get("Gender", ""),
                    "provider": self.name,
                }
                for voice in await edge_tts.list_voices()
            ]
        except Exception as exc:
            raise SynthesisError("Unable to list Edge TTS voices") from exc

    async def synthesize(self, request: SpeechRequest, model: str) -> SpeechArtifact:
        if request.response_format not in {"mp3", "mpeg"}:
            raise UnsupportedCapabilityError("Edge TTS only returns MP3 audio")
        if request.extensions.get("emotion"):
            raise UnsupportedCapabilityError("Edge TTS does not expose a stable emotion API")
        if request.extensions.get("return_word_timings"):
            raise UnsupportedCapabilityError("Edge TTS word timings are not enabled")

        voice = request.voice or self.default_voice
        rate = round((request.speed - 1.0) * 100)
        pitch_ratio = float(request.extensions.get("pitch", 1.0))
        pitch = round((pitch_ratio - 1.0) * 100)
        try:
            communicate = edge_tts.Communicate(
                request.input,
                voice,
                rate=f"{rate:+d}%",
                pitch=f"{pitch:+d}Hz",
            )
            audio = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    audio.extend(chunk.get("data", b""))
        except Exception as exc:
            raise SynthesisError("Edge TTS synthesis request failed") from exc
        if not audio:
            raise SynthesisError("Edge TTS returned no audio")
        return SpeechArtifact(
            audio=bytes(audio),
            media_type="audio/mpeg",
            provider=self.name,
            model=model or "edge-tts",
            voice=voice,
        )

    async def close(self) -> None:
        return None

    async def health(self) -> bool:
        if not self.available:
            return False
        try:
            await self.synthesize(
                SpeechRequest(
                    model=f"{self.name}/edge-tts",
                    input="测试",
                    voice=self.default_voice,
                    response_format="mp3",
                ),
                "edge-tts",
            )
            return True
        except Exception:
            return False
