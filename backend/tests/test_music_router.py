import pytest
from fastapi import HTTPException

from apps.music.router import _validate_proxy_target, router


def test_music_router_exposes_state_machine_endpoints():
    paths = {route.path for route in router.routes}
    assert {
        "/music/state",
        "/music/providers",
        "/music/requests",
        "/music/commands/skip",
        "/music/commands/pause",
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
