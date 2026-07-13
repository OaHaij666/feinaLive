from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from main import app, shutdown


def make_request(host: str = "127.0.0.1", origin: str = "") -> Request:
    headers = [(b"origin", origin.encode())] if origin else []
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/system/shutdown",
            "headers": headers,
            "client": (host, 54321),
            "app": app,
        }
    )


async def test_local_launcher_can_request_graceful_shutdown(monkeypatch):
    server = SimpleNamespace(should_exit=False)
    monkeypatch.setattr(app.state, "uvicorn_server", server, raising=False)

    response = await shutdown(make_request())

    assert response == {"status": "shutting_down"}
    assert server.should_exit is True


@pytest.mark.parametrize(
    ("host", "origin"),
    [
        ("192.0.2.10", ""),
        ("127.0.0.1", "http://127.0.0.1:8088"),
    ],
)
async def test_shutdown_rejects_remote_or_browser_requests(host, origin):
    with pytest.raises(HTTPException) as error:
        await shutdown(make_request(host, origin))

    assert error.value.status_code == 403
