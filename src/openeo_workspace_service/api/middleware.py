"""
Request ID middleware.

Injects a unique ``X-Request-ID`` header into every response and binds it
to the structlog context so every log line emitted during the request
automatically carries the request ID.

The ID is taken from the incoming ``X-Request-ID`` header if present
(useful when an upstream gateway already assigned one), otherwise a new
UUIDv4 is generated.
"""

from __future__ import annotations

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

_REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assign and propagate a per-request trace ID."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(_REQUEST_ID_HEADER) or str(uuid.uuid4())

        # Bind to structlog context for the duration of this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers[_REQUEST_ID_HEADER] = request_id
        return response
