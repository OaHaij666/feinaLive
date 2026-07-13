import httpx
import pytest

from apps.speech.client import SpeechGatewayClient


@pytest.mark.asyncio
async def test_speech_gateway_client_normalizes_audio_metadata():
    async def handler(request: httpx.Request):
        assert request.url.path == "/v1/audio/speech"
        assert request.headers["Authorization"] == "Bearer gateway-secret"
        return httpx.Response(
            200,
            content=b"audio",
            headers={
                "content-type": "audio/mpeg",
                "X-Speech-Provider": "edge",
                "X-Speech-Model": "edge-tts",
                "X-Speech-Voice": "voice",
                "X-Speech-Duration-Ms": "1200",
            },
        )

    client = SpeechGatewayClient(
        gateway_url="http://gateway/v1",
        api_key="gateway-secret",
        model="edge/edge-tts",
        voice="voice",
        transport=httpx.MockTransport(handler),
    )

    result = await client.synthesize(" hello ")

    assert result is not None
    assert result.audio_data == b"audio"
    assert result.media_type == "audio/mpeg"
    assert result.provider == "edge"
    assert result.duration_ms == 1200
    await client.close()


@pytest.mark.asyncio
async def test_speech_gateway_client_returns_none_on_explicit_gateway_error():
    async def handler(_: httpx.Request):
        return httpx.Response(
            422,
            json={"error": {"code": "unsupported_capability", "message": "no wav"}},
        )

    client = SpeechGatewayClient(
        gateway_url="http://gateway/v1",
        model="edge/edge-tts",
        voice="voice",
        transport=httpx.MockTransport(handler),
    )

    assert await client.synthesize("hello") is None
    await client.close()


@pytest.mark.asyncio
async def test_speech_gateway_admin_contract_uses_same_authenticated_connection():
    async def handler(request: httpx.Request):
        assert request.headers["Authorization"] == "Bearer gateway-secret"
        if request.method == "GET" and request.url.path == "/v1/admin/provider-schemas":
            return httpx.Response(200, json={"data": [{"type": "edge", "fields": []}]})
        if request.method == "PUT" and request.url.path == "/v1/admin/providers/edge":
            return httpx.Response(200, json={"ok": True})
        if request.method == "PUT" and request.url.path == "/v1/admin/routes/host_voice":
            return httpx.Response(200, json={"ok": True})
        if request.method == "POST" and request.url.path == "/v1/providers/edge/probe":
            return httpx.Response(200, json={"provider": "edge", "healthy": True})
        return httpx.Response(404)

    client = SpeechGatewayClient(
        gateway_url="http://gateway/v1",
        api_key="gateway-secret",
        model="host_voice",
        voice="",
        transport=httpx.MockTransport(handler),
    )

    schemas = await client.get_provider_schemas()
    updated = await client.update_provider(
        "edge", {"type": "edge", "enabled": True, "values": {}}
    )
    route = await client.update_route(
        "host_voice", {"primary": "edge/edge-tts", "fallback": []}
    )
    probe = await client.probe_provider("edge")

    assert schemas["data"][0]["type"] == "edge"
    assert updated["ok"] is True
    assert route["ok"] is True
    assert probe["healthy"] is True
    await client.close()
