"""OpenAI-compatible Speech Gateway HTTP service."""

from __future__ import annotations

import json
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import Response

from speech_gateway.config import config
from speech_gateway.errors import SpeechGatewayError
from speech_gateway.models import SpeechRequest
from speech_gateway.registry import SpeechProviderRegistry

registry = SpeechProviderRegistry()


async def authenticate(authorization: str | None = Header(default=None)) -> None:
    if not config.api_key:
        return
    expected = f"Bearer {config.api_key}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid gateway API key")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await registry.close()


app = FastAPI(title="Feina Speech Gateway", version="0.1.0", lifespan=lifespan)


@app.exception_handler(SpeechGatewayError)
async def speech_error_handler(_, exc: SpeechGatewayError):
    return Response(
        content=json.dumps({"error": {"code": exc.code, "message": str(exc)}}),
        status_code=exc.status_code,
        media_type="application/json",
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "providers": {
            name: {"configured": provider.available}
            for name, provider in registry.providers.items()
        },
    }


@app.get("/v1/capabilities", dependencies=[Depends(authenticate)])
async def capabilities():
    return {
        "providers": [provider.capabilities().to_dict() for provider in registry.providers.values()]
    }


@app.get("/v1/models", dependencies=[Depends(authenticate)])
async def models():
    return {
        "object": "list",
        "data": [
            {
                "id": f"{name}/{name}-tts",
                "object": "model",
                "owned_by": name,
                "configured": provider.available,
            }
            for name, provider in registry.providers.items()
        ],
    }


@app.get("/v1/voices", dependencies=[Depends(authenticate)])
async def voices(provider: str | None = Query(default=None)):
    providers = [registry.get(provider)] if provider else [
        value for value in registry.providers.values() if value.available
    ]
    result = []
    for item in providers:
        result.extend(await item.voices())
    return {"data": result}


@app.post("/v1/audio/speech", dependencies=[Depends(authenticate)])
async def create_speech(request: SpeechRequest):
    artifact = await registry.synthesize(request)
    headers = {
        "X-Speech-Provider": artifact.provider,
        "X-Speech-Model": artifact.model,
        "X-Speech-Voice": artifact.voice,
    }
    if artifact.sample_rate is not None:
        headers["X-Speech-Sample-Rate"] = str(artifact.sample_rate)
    if artifact.duration_ms is not None:
        headers["X-Speech-Duration-Ms"] = str(artifact.duration_ms)
    if artifact.timings:
        headers["X-Speech-Timings"] = json.dumps(artifact.timings, ensure_ascii=True)
    return Response(content=artifact.audio, media_type=artifact.media_type, headers=headers)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8091)
