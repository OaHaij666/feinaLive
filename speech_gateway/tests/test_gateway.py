import base64
import json

import httpx
import pytest

from speech_gateway import main
from speech_gateway.admin import public_config, update_provider, update_route
from speech_gateway.config import GatewayConfig, ProviderConfig, RouteConfig, load_config
from speech_gateway.errors import (
    CircuitOpenError,
    InvalidSpeechRequestError,
    SynthesisError,
    UnsupportedCapabilityError,
)
from speech_gateway.models import ProviderCapabilities, SpeechArtifact, SpeechRequest
from speech_gateway.providers.openai_compatible import OpenAICompatibleSpeechProvider
from speech_gateway.providers.volcano import VolcanoSpeechProvider
from speech_gateway.registry import SpeechProviderRegistry
from speech_gateway.schemas import schema_for


def provider_config(name: str, provider_type: str = "test", **kwargs) -> ProviderConfig:
    return ProviderConfig(name=name, type=provider_type, **kwargs)


def test_volcano_schema_exposes_v3_credentials_and_bounded_resource_choices():
    schema = schema_for("volcano")
    fields = {field["key"]: field for field in schema["fields"]}

    assert fields["api_key"]["type"] == "secret"
    assert "appid" not in fields
    assert "access_token" not in fields
    assert fields["resource_id"]["type"] == "select"
    assert "seed-icl-2.0" in fields["resource_id"]["options"]
    assert fields["sample_rate"]["options"] == [
        8000,
        16000,
        22050,
        24000,
        32000,
        44100,
        48000,
    ]


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

    async def health(self):
        return True

    async def synthesize(self, request, model):
        self.requests.append((request, model))
        if self.error:
            raise self.error
        return SpeechArtifact(b"audio", "audio/mpeg", self.name, model, request.voice)

    async def close(self):
        return None


class FakeRegistry:
    providers = {}

    def __init__(self):
        self.closed = False

    async def synthesize(self, request):
        return SpeechArtifact(
            audio=b"audio",
            media_type="audio/mpeg",
            provider="edge",
            model=request.model,
            voice=request.voice,
            duration_ms=900,
            synthesis_ms=100,
            rtf=0.1111,
            attempts=(request.model,),
        )

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_registry_routes_prefixed_model_to_provider():
    edge = FakeProvider("edge")
    registry = SpeechProviderRegistry([edge], GatewayConfig(default_provider="edge"))
    request = SpeechRequest(model="edge/edge-tts", input="hello", voice="voice")

    result = await registry.synthesize(request)

    assert result.provider == "edge"
    assert edge.requests[0][1] == "edge-tts"
    assert result.attempts == ("edge/edge-tts",)


@pytest.mark.asyncio
async def test_openai_compatible_speech_endpoint_returns_performance_headers(monkeypatch):
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
    assert response.headers["X-Speech-Synthesis-Ms"] == "100"
    assert response.headers["X-Speech-RTF"] == "0.1111"


@pytest.mark.asyncio
async def test_registry_hot_swap_waits_for_in_flight_request(monkeypatch):
    old = FakeRegistry()
    new = FakeRegistry()
    monkeypatch.setattr(main, "registry", old)
    main.registry_users.clear()
    main.retired_registries.clear()

    acquired = await main.acquire_registry()
    await main.swap_registry(new)

    assert acquired is old
    assert old.closed is False
    assert main.registry is new

    await main.release_registry(acquired)
    assert old.closed is True


@pytest.mark.asyncio
async def test_named_route_uses_retryable_fallback():
    primary = FakeProvider("primary", error=SynthesisError("failed"))
    fallback = FakeProvider("fallback")
    settings = GatewayConfig(
        providers={
            "primary": provider_config("primary"),
            "fallback": provider_config("fallback"),
        },
        routes={
            "host_voice": RouteConfig(
                "host_voice", "primary/model", ("fallback/model",)
            )
        },
    )
    registry = SpeechProviderRegistry([primary, fallback], settings)

    result = await registry.synthesize(
        SpeechRequest(model="host_voice", input="hello", voice="voice")
    )

    assert result.provider == "fallback"
    assert result.fallback_from == "primary/model"
    assert result.attempts == ("primary/model", "fallback/model")


@pytest.mark.asyncio
async def test_non_retryable_capability_error_does_not_fallback():
    primary = FakeProvider("primary", error=UnsupportedCapabilityError("no wav"))
    fallback = FakeProvider("fallback")
    settings = GatewayConfig(
        providers={
            "primary": provider_config("primary"),
            "fallback": provider_config("fallback"),
        },
        routes={
            "host_voice": RouteConfig(
                "host_voice", "primary/model", ("fallback/model",)
            )
        },
    )
    registry = SpeechProviderRegistry([primary, fallback], settings)

    with pytest.raises(UnsupportedCapabilityError):
        await registry.synthesize(
            SpeechRequest(model="host_voice", input="hello", voice="voice")
        )
    assert fallback.requests == []


@pytest.mark.asyncio
async def test_circuit_opens_after_retryable_failure_threshold():
    primary = FakeProvider("primary", error=SynthesisError("failed"))
    settings = GatewayConfig(
        providers={"primary": provider_config("primary")},
        circuit_failure_threshold=2,
        circuit_recovery_seconds=60,
    )
    registry = SpeechProviderRegistry([primary], settings)
    request = SpeechRequest(model="primary/model", input="hello", voice="voice")

    for _ in range(2):
        with pytest.raises(SynthesisError):
            await registry.synthesize(request)
    with pytest.raises(CircuitOpenError):
        await registry.synthesize(request)

    assert len(primary.requests) == 2
    assert registry.status()["providers"]["primary"]["circuit"] == "open"

    assert await registry.probe("primary") is True
    assert registry.status()["providers"]["primary"]["circuit"] == "closed"


@pytest.mark.asyncio
async def test_generic_openai_compatible_provider_forwards_standard_contract():
    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/audio/speech"
        assert request.headers["Authorization"] == "Bearer secret"
        payload = __import__("json").loads(request.content)
        assert payload["model"] == "kokoro"
        return httpx.Response(
            200,
            content=b"mp3-data",
            headers={"content-type": "audio/mpeg", "X-Speech-Voice": "local"},
        )

    import os

    os.environ["TEST_LOCAL_TTS_KEY"] = "secret"
    settings = provider_config(
        "local",
        "openai_compatible",
        base_url="http://local/v1",
        api_key_env="TEST_LOCAL_TTS_KEY",
        default_voice="local",
    )
    provider = OpenAICompatibleSpeechProvider(settings, httpx.MockTransport(handler))

    artifact = await provider.synthesize(
        SpeechRequest(model="local/kokoro", input="hello", voice="local"), "kokoro"
    )

    assert artifact.audio == b"mp3-data"
    assert artifact.provider == "local"
    await provider.close()


def test_yaml_config_loads_routes_and_environment_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_KEY", "secret")
    path = tmp_path / "speech.yaml"
    path.write_text(
        """
gateway:
  default_provider: local
providers:
  local:
    type: openai_compatible
    base_url: http://127.0.0.1:8000/v1
    api_key_env: LOCAL_KEY
routes:
  host_voice:
    primary: local/kokoro
    fallback: [edge/edge-tts]
""",
        encoding="utf-8",
    )

    settings = load_config(path)

    assert settings.providers["local"].api_key == "secret"
    assert settings.routes["host_voice"].fallback == ("edge/edge-tts",)


def test_provider_admin_persists_non_secrets_and_masks_keyring_values(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    monkeypatch.setenv("SPEECH_GATEWAY_CONFIG", str(config_path))
    stored = {}
    monkeypatch.setattr(
        "speech_gateway.config.secret_store.get",
        lambda provider, field: stored.get(f"{provider}.{field}", ""),
    )
    monkeypatch.setattr(
        "speech_gateway.admin.secret_store.set",
        lambda provider, field, value: stored.__setitem__(f"{provider}.{field}", value),
    )

    update_provider(
        "local",
        "openai_compatible",
        True,
        {
            "base_url": "http://127.0.0.1:8000/v1",
            "api_key": "secret",
            "default_voice": "voice",
            "formats": ["mp3"],
            "health_path": "models",
            "timeout_seconds": 30,
        },
    )
    update_route("host_voice", "local/kokoro", ["edge/edge-tts"])

    assert "secret" not in config_path.read_text(encoding="utf-8")
    assert public_config()["providers"]["local"]["values"]["api_key"] == "****"
    assert public_config()["routes"]["host_voice"]["primary"] == "local/kokoro"


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
    provider = EdgeSpeechProvider(
        provider_config("edge", "edge", default_voice="zh-CN-XiaoxiaoNeural")
    )
    with pytest.raises(SynthesisError, match="Edge TTS synthesis request failed"):
        await provider.synthesize(
            SpeechRequest(model="edge/edge-tts", input="hello", voice="voice"),
            "edge-tts",
        )


@pytest.mark.asyncio
async def test_volcano_adapter_returns_normalized_artifact(monkeypatch):
    monkeypatch.setenv("VOLCANO_API_KEY", "api-key")
    settings = provider_config(
        "volcano",
        "volcano",
        api_key_env="VOLCANO_API_KEY",
        default_voice="S_voice",
        formats=("mp3",),
        options={"resource_id": "seed-icl-2.0", "sample_rate": 24000},
    )
    provider = VolcanoSpeechProvider(settings)

    async def handler(request: httpx.Request):
        assert request.url.path == "/api/v3/tts/unidirectional/sse"
        assert request.headers["X-Api-Key"] == "api-key"
        assert request.headers["X-Api-Resource-Id"] == "seed-icl-2.0"
        assert request.headers["X-Api-Request-Id"]
        payload = json.loads(request.content)
        assert payload["req_params"] == {
            "text": "你好",
            "speaker": "S_voice",
            "audio_params": {
                "format": "mp3",
                "sample_rate": 24000,
                "speech_rate": -20,
                "loudness_rate": 0,
            },
            "additions": '{"post_process": {"pitch": 0}}',
        }
        first = base64.b64encode(b"audio-").decode()
        second = base64.b64encode(b"data").decode()
        body = (
            f'event: 352\ndata: {{"code":0,"message":"","data":"{first}"}}\n\n'
            f'event: 352\ndata: {{"code":0,"message":"","data":"{second}"}}\n\n'
            'event: 152\ndata: {"code":20000000,"message":"ok","data":null}\n\n'
        )
        return httpx.Response(200, text=body, headers={"Content-Type": "text/event-stream"})

    await provider._client.aclose()
    provider._client = httpx.AsyncClient(
        base_url="https://openspeech.bytedance.com",
        transport=httpx.MockTransport(handler),
    )

    result = await provider.synthesize(
        SpeechRequest(
            model="volcano/seed-icl-2.0",
            input="你好",
            voice="S_voice",
            response_format="mp3",
            speed=0.8,
        ),
        "seed-icl-2.0",
    )

    assert result.audio == b"audio-data"
    assert result.media_type == "audio/mpeg"
    assert result.sample_rate == 24000
    await provider.close()


@pytest.mark.asyncio
async def test_volcano_rejects_unsupported_format_before_network(monkeypatch):
    monkeypatch.setenv("VOLCANO_API_KEY", "api-key")
    provider = VolcanoSpeechProvider(
        provider_config(
            "volcano",
            "volcano",
            api_key_env="VOLCANO_API_KEY",
            default_voice="S_voice",
            options={"resource_id": "seed-icl-2.0"},
        )
    )
    with pytest.raises(UnsupportedCapabilityError):
        await provider.synthesize(
            SpeechRequest(model="volcano/model", input="hello", response_format="flac"),
            "model",
        )
    await provider.close()


@pytest.mark.asyncio
async def test_volcano_rejects_speed_outside_documented_range(monkeypatch):
    monkeypatch.setenv("VOLCANO_API_KEY", "api-key")
    provider = VolcanoSpeechProvider(
        provider_config(
            "volcano",
            "volcano",
            api_key_env="VOLCANO_API_KEY",
            default_voice="S_voice",
            options={"resource_id": "seed-icl-2.0"},
        )
    )
    with pytest.raises(InvalidSpeechRequestError, match="speed must be between 0.5 and 2.0"):
        await provider.synthesize(
            SpeechRequest(model="volcano/model", input="hello", speed=0.25),
            "model",
        )
    await provider.close()
