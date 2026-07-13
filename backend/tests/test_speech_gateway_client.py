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
