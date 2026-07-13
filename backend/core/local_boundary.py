"""Browser-origin boundary for the unauthenticated local control plane."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import Receive, Scope, Send

ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]
SAFE_HTTP_METHODS = {"GET", "HEAD", "OPTIONS"}


class LocalOriginBoundaryMiddleware:
    """Reject cross-origin writes and WebSockets while preserving CLI access.

    The application intentionally has no login system because it is a local
    desktop service. Requests without an Origin header remain available to
    trusted local tools; browser requests must come from an explicit frontend
    origin.
    """

    def __init__(self, app: ASGIApp, *, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin and origin not in self.allowed_origins:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008, "reason": "origin not allowed"})
                return
            if scope.get("method", "GET").upper() not in SAFE_HTTP_METHODS:
                response = PlainTextResponse("origin not allowed", status_code=403)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)
