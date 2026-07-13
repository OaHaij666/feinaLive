import asyncio

import pytest
from fastapi import HTTPException

from apps.music.manager import MusicManager
from apps.music.models import MusicState
from apps.music.router import _validate_proxy_target, router


def test_music_router_exposes_state_machine_endpoints():
    paths = {route.path for route in router.routes}
    assert {
        "/music/state",
        "/music/providers",
        "/music/requests",
        "/music/commands/skip",
        "/music/commands/pause",
        "/music/commands/ducking",
        "/music/providers/{provider}/search",
        "/music/library",
        "/music/player/claim",
        "/music/playback/events",
        "/music/stream/{entry_id}",
    } <= paths


def test_stream_proxy_rejects_untrusted_and_local_urls():
    _validate_proxy_target("https://cdn.bilivideo.com/audio.m4s", ["bilivideo.com"])
    with pytest.raises(HTTPException):
        _validate_proxy_target("http://127.0.0.1:8000/private", ["bilivideo.com"])
    with pytest.raises(HTTPException):
        _validate_proxy_target("https://bilivideo.com.evil.example/audio", ["bilivideo.com"])


@pytest.mark.asyncio
async def test_fallback_lookup_does_not_reenter_manager_initialization():
    class EmptyRepository:
        async def list_library(self):
            return []

    manager = MusicManager()
    manager._repository = EmptyRepository()

    async def recursive_public_api():
        raise AssertionError("fallback lookup re-entered the public initialization API")

    manager.list_library = recursive_public_api
    state = MusicState(
        revision=0,
        current=None,
        queue=[],
        paused=False,
        volume=1.0,
        ducking_factor=1.0,
        ducking_enabled=True,
        effective_volume=1.0,
    )

    assert await asyncio.wait_for(manager._ensure_fallback(state), timeout=0.2) is state
