import pytest

from core.local_boundary import LocalOriginBoundaryMiddleware

ALLOWED = "http://127.0.0.1:8088"


async def _receive():
    return {"type": "http.disconnect"}


async def _exercise(scope):
    downstream_calls = []
    sent = []

    async def downstream(_scope, _receive, send):
        downstream_calls.append(True)
        if _scope["type"] == "http":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

    async def capture(message):
        sent.append(message)

    middleware = LocalOriginBoundaryMiddleware(downstream, allowed_origins=[ALLOWED])
    await middleware(scope, _receive, capture)
    return downstream_calls, sent


def _scope(scope_type: str, *, origin: str | None = None, method: str = "POST"):
    headers = [] if origin is None else [(b"origin", origin.encode())]
    return {
        "type": scope_type,
        "method": method,
        "path": "/control",
        "headers": headers,
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 9191),
        "scheme": "http" if scope_type == "http" else "ws",
        "query_string": b"",
        "http_version": "1.1",
    }


@pytest.mark.asyncio
async def test_cross_origin_browser_write_is_rejected():
    calls, sent = await _exercise(_scope("http", origin="https://evil.example"))
    assert not calls
    assert sent[0]["status"] == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", [ALLOWED, None])
async def test_allowed_origin_and_originless_local_tool_are_accepted(origin):
    calls, sent = await _exercise(_scope("http", origin=origin))
    assert calls
    assert sent[0]["status"] == 200


@pytest.mark.asyncio
async def test_cross_origin_websocket_is_rejected():
    calls, sent = await _exercise(_scope("websocket", origin="https://evil.example"))
    assert not calls
    assert sent == [{"type": "websocket.close", "code": 1008, "reason": "origin not allowed"}]
