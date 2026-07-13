"""OpenAI-compatible Speech Gateway HTTP service."""

from __future__ import annotations

import asyncio
import json
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from speech_gateway.admin import provider_schemas, public_config, update_provider, update_route
from speech_gateway.config import config, load_config
from speech_gateway.errors import SpeechGatewayError
from speech_gateway.models import SpeechRequest
from speech_gateway.registry import SpeechProviderRegistry

registry = SpeechProviderRegistry()
registry_lock = asyncio.Lock()
registry_users: dict[int, int] = {}
retired_registries: dict[int, SpeechProviderRegistry] = {}


class ProviderUpdateRequest(BaseModel):
    type: str
    enabled: bool = True
    values: dict = Field(default_factory=dict)


class RouteUpdateRequest(BaseModel):
    primary: str
    fallback: list[str] = Field(default_factory=list)


async def authenticate(authorization: str | None = Header(default=None)) -> None:
    if not config.api_key:
        return
    expected = f"Bearer {config.api_key}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid gateway API key")


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    registries = [registry, *retired_registries.values()]
    for item in {id(value): value for value in registries}.values():
        await item.close()


async def acquire_registry() -> SpeechProviderRegistry:
    async with registry_lock:
        current = registry
        key = id(current)
        registry_users[key] = registry_users.get(key, 0) + 1
        return current


async def release_registry(current: SpeechProviderRegistry) -> None:
    close_target = None
    async with registry_lock:
        key = id(current)
        remaining = registry_users.get(key, 1) - 1
        if remaining <= 0:
            registry_users.pop(key, None)
            close_target = retired_registries.pop(key, None)
        else:
            registry_users[key] = remaining
    if close_target is not None:
        await close_target.close()


async def swap_registry(new_registry: SpeechProviderRegistry) -> None:
    global registry
    close_target = None
    async with registry_lock:
        old_registry = registry
        registry = new_registry
        key = id(old_registry)
        if registry_users.get(key, 0):
            retired_registries[key] = old_registry
        else:
            close_target = old_registry
    if close_target is not None:
        await close_target.close()


app = FastAPI(title="Feina Speech Gateway", version="0.1.0", lifespan=lifespan)


@app.exception_handler(SpeechGatewayError)
async def speech_error_handler(_, exc: SpeechGatewayError):
    return Response(
        content=json.dumps(
            {
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "retryable": exc.retryable,
                }
            }
        ),
        status_code=exc.status_code,
        media_type="application/json",
    )


@app.get("/health")
async def health():
    status = registry.status()
    return {"status": "ok", "providers": status["providers"]}


@app.get("/v1/status", dependencies=[Depends(authenticate)])
async def status():
    return registry.status()


@app.get("/v1/admin/provider-schemas", dependencies=[Depends(authenticate)])
async def get_provider_schemas():
    return {"data": provider_schemas()}


@app.get("/v1/admin/config", dependencies=[Depends(authenticate)])
async def get_admin_config():
    return public_config()


@app.put("/v1/admin/providers/{provider}", dependencies=[Depends(authenticate)])
async def put_provider(provider: str, request: ProviderUpdateRequest):
    try:
        update_provider(provider, request.type, request.enabled, request.values)
        new_registry = SpeechProviderRegistry(settings=load_config())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await swap_registry(new_registry)
    return {"ok": True, "provider": provider, "config": public_config()}


@app.put("/v1/admin/routes/{route}", dependencies=[Depends(authenticate)])
async def put_route(route: str, request: RouteUpdateRequest):
    try:
        update_route(route, request.primary, request.fallback)
        new_registry = SpeechProviderRegistry(settings=load_config())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await swap_registry(new_registry)
    return {"ok": True, "route": route, "config": public_config()}


@app.post("/v1/providers/{provider}/probe", dependencies=[Depends(authenticate)])
async def probe_provider(provider: str):
    return {"provider": provider, "healthy": await registry.probe(provider)}


@app.get("/metrics", dependencies=[Depends(authenticate)])
async def metrics():
    return PlainTextResponse(
        registry.metrics.prometheus(),
        media_type="text/plain; version=0.0.4",
    )


@app.get("/v1/capabilities", dependencies=[Depends(authenticate)])
async def capabilities():
    return {
        "providers": [provider.capabilities().to_dict() for provider in registry.providers.values()]
    }


@app.get("/v1/models", dependencies=[Depends(authenticate)])
async def models():
    provider_models = [
        {
            "id": f"{name}/{name}-tts",
            "object": "model",
            "owned_by": name,
            "configured": provider.available,
        }
        for name, provider in registry.providers.items()
    ]
    route_models = [
        {
            "id": name,
            "object": "model",
            "owned_by": "speech-gateway-route",
            "primary": route.primary,
            "fallback": list(route.fallback),
            "configured": True,
        }
        for name, route in registry.settings.routes.items()
    ]
    return {
        "object": "list",
        "data": [*route_models, *provider_models],
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
    current_registry = await acquire_registry()
    try:
        artifact = await current_registry.synthesize(request)
    finally:
        await release_registry(current_registry)
    headers = {
        "X-Speech-Provider": artifact.provider,
        "X-Speech-Model": artifact.model,
        "X-Speech-Voice": artifact.voice,
        "X-Speech-Attempts": ",".join(artifact.attempts),
    }
    if artifact.synthesis_ms is not None:
        headers["X-Speech-Synthesis-Ms"] = str(artifact.synthesis_ms)
    if artifact.rtf is not None:
        headers["X-Speech-RTF"] = str(artifact.rtf)
    if artifact.fallback_from:
        headers["X-Speech-Fallback-From"] = artifact.fallback_from
    if artifact.sample_rate is not None:
        headers["X-Speech-Sample-Rate"] = str(artifact.sample_rate)
    if artifact.duration_ms is not None:
        headers["X-Speech-Duration-Ms"] = str(artifact.duration_ms)
    if artifact.timings:
        encoded_timings = json.dumps(artifact.timings, ensure_ascii=True, separators=(",", ":"))
        if len(encoded_timings) <= 4096:
            headers["X-Speech-Timings"] = encoded_timings
        else:
            headers["X-Speech-Timings-Omitted"] = "header-size-limit"
    return Response(content=artifact.audio, media_type=artifact.media_type, headers=headers)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8091)
