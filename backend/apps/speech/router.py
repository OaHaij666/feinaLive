"""Local control-panel proxy for Speech Gateway administration."""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apps.speech.client import get_speech_gateway_client

router = APIRouter(prefix="/speech-gateway", tags=["speech-gateway"])


class ProviderUpdateRequest(BaseModel):
    type: str
    enabled: bool = True
    values: dict = Field(default_factory=dict)


class RouteUpdateRequest(BaseModel):
    primary: str
    fallback: list[str] = Field(default_factory=list)


async def _proxy(call):
    try:
        return await call
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=503, detail="Speech Gateway is unavailable") from exc


@router.get("/provider-schemas")
async def provider_schemas():
    return await _proxy(get_speech_gateway_client().get_provider_schemas())


@router.get("/config")
async def gateway_config():
    return await _proxy(get_speech_gateway_client().get_admin_config())


@router.get("/status")
async def gateway_status():
    return await _proxy(get_speech_gateway_client().get_status())


@router.put("/providers/{provider}")
async def update_provider(provider: str, request: ProviderUpdateRequest):
    return await _proxy(
        get_speech_gateway_client().update_provider(provider, request.model_dump())
    )


@router.put("/routes/{route}")
async def update_route(route: str, request: RouteUpdateRequest):
    return await _proxy(
        get_speech_gateway_client().update_route(route, request.model_dump())
    )


@router.post("/providers/{provider}/probe")
async def probe_provider(provider: str):
    return await _proxy(get_speech_gateway_client().probe_provider(provider))
