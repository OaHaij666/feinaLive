import base64

import httpx
import pytest

from speech_gateway import main
from speech_gateway.config import GatewayConfig
from speech_gateway.errors import SynthesisError, UnsupportedCapabilityError
from speech_gateway.models import ProviderCapabilities, SpeechArtifact, SpeechRequest
from speech_gateway.providers.volcano import VolcanoSpeechProvider
from speech_gateway.registry import SpeechProviderRegistry


class FakeProvider:
    def __init__(self, name: str, *, error: Exception | None = None):
        self.name = name
        self.error = error
        self.requests = []

    @property
    def available(self):
        return True

    def capabilities(self):
        return ProviderCapabilities(self.name, ("mp3",), False, True, False, False, False, False)

    async def voices(self):
        return []

    async def synthesize(self, request, model):
        self.requests.append((request, model))
        if self.error:
            raise self.error
        return SpeechArtifact(b"audio", "audio/mpeg", self.name, model, request.voice)

    async def close(self):
        return None


class FakeRegistry:
    providers = {}

    async def synthesize(self, request):
        return SpeechArtifact(
            audio=b"audio",
            media_type="audio/mpeg",
            provider="edge",
            model=request.model,
            voice=request.voice,
            duration_ms=900,
        )


@pytest.mark.asyncio
async def test_registry_routes_prefixed_model_to_provider():
    edge = FakeProvider("edge")
    registry = SpeechProviderRegistry(
        [edge], GatewayConfig(default_provider="edge", fallback_providers=())
    )
    request = SpeechRequest(model="edge/edge-tts", input="hello", voice="voice")

    result = await registry.synthesize(request)

    assert result.provider == "edge"
    assert edge.requests[0][1] == "edge-tts"


@pytest.mark.asyncio
async def test_openai_compatible_speech_endpoint_returns_artifact_headers(monkeypatch):
    monkeypatch.setattr(main, "registry", FakeRegistry())
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://gateway") as client:
        response = await client.post(
            "/v1/audio/speech",
            json={
                "model": "edge/edge-tts",
                "input": "hello",
                "voice": "voice",
                "response_format": "mp3",
            },
        )

    assert response.status_code == 200
    assert response.content == b"audio"
    assert response.headers["X-Speech-Provider"] == "edge"
    assert response.headers["X-Speech-Duration-Ms"] == "900"


@pytest.mark.asyncio
async def test_registry_uses_explicit_fallback_after_provider_failure():
    primary = FakeProvider("primary", error=SynthesisError("failed"))
    fallback = FakeProvider("fallback")
    registry = SpeechProviderRegistry(
        [primary, fallback],
        GatewayConfig(default_provider="primary", fallback_providers=("fallback",)),
    )

    result = await registry.synthesize(
        SpeechRequest(model="primary/model", input="hello", voice="voice")
    )

    assert result.provider == "fallback"


@pytest.mark.asyncio
async def test_edge_provider_normalizes_upstream_failure(monkeypatch):
    from speech_gateway.providers.edge import EdgeSpeechProvider

    class BrokenCommunicate:
        def __init__(self, *args, **kwargs):
            pass

        async def stream(self):
            raise RuntimeError("upstream unavailable")
            yield

    monkeypatch.setattr("speech_gateway.providers.edge.edge_tts.Communicate", BrokenCommunicate)
    provider = EdgeSpeechProvider()
    with pytest.raises(SynthesisError, match="Edge TTS synthesis request failed"):
        await provider.synthesize(
            SpeechRequest(model="edge/edge-tts", input="hello", voice="voice"),
            "edge-tts",
        )


@pytest.mark.asyncio
async def test_volcano_adapter_returns_normalized_artifact(monkeypatch):
    monkeypatch.setenv("VOLCANO_APPID", "appid")
    monkeypatch.setenv("VOLCANO_ACCESS_TOKEN", "token")
    monkeypatch.setenv("VOLCANO_DEFAULT_VOICE", "voice")
    provider = VolcanoSpeechProvider()

    async def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer;token"
        return httpx.Response(200, json={"data": base64.b64encode(b"wav-data").decode()})

    await provider._client.aclose()
    provider._client = httpx.AsyncClient(
        base_url="https://openspeech.bytedance.com",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.synthesize(
        SpeechRequest(
            model="volcano/voice-clone",
            input="你好",
            voice="voice",
            response_format="wav",
        ),
        "voice-clone",
    )

    assert result.audio == b"wav-data"
    assert result.media_type == "audio/wav"
    await provider.close()


@pytest.mark.asyncio
async def test_volcano_rejects_unsupported_format_before_network(monkeypatch):
    monkeypatch.setenv("VOLCANO_APPID", "appid")
    monkeypatch.setenv("VOLCANO_ACCESS_TOKEN", "token")
    monkeypatch.setenv("VOLCANO_DEFAULT_VOICE", "voice")
    provider = VolcanoSpeechProvider()
    with pytest.raises(UnsupportedCapabilityError):
        await provider.synthesize(
            SpeechRequest(model="volcano/model", input="hello", response_format="flac"),
            "model",
        )
    await provider.close()
