"""
Simple in-process rate-limiting middleware.

Uses a per-subject (Keycloak ``sub`` claim) sliding-window counter stored in
a process-local dict.  This is intentionally lightweight:

- Good enough for a single-process deployment or small horizontally-scaled
  clusters where per-instance limiting is acceptable.
- For distributed / accurate rate limiting, replace with a Redis-backed
  implementation (e.g. ``slowapi`` or a custom RESP3 sliding window).

Configuration (environment variables)
--------------------------------------
RATE_LIMIT_REQUESTS  – max requests allowed per window  (default 100)
RATE_LIMIT_WINDOW_S  – window size in seconds           (default 60)

Responses
----------
- Requests within the limit pass through unchanged.
- Exceeded requests receive HTTP **429** with a JSON body matching the
  openEO error shape and ``Retry-After`` / ``X-RateLimit-*`` headers.
- Unauthenticated requests are **not** rate-limited (auth checks apply
  separately at the route level).
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Token-bucket store (process-local)
# ---------------------------------------------------------------------------

# subject → deque of request timestamps (float, monotonic)
_windows: dict[str, Deque[float]] = {}
_lock = Lock()


def _is_allowed(subject: str, limit: int, window: float) -> tuple[bool, int]:
    """
    Sliding-window rate-limit check.

    Returns ``(allowed, remaining)`` where *remaining* is the number of
    requests the caller may still make in this window.
    """
    now = time.monotonic()
    cutoff = now - window

    with _lock:
        if subject not in _windows:
            _windows[subject] = deque()

        dq = _windows[subject]
        # Evict timestamps outside the current window
        while dq and dq[0] < cutoff:
            dq.popleft()

        if len(dq) >= limit:
            remaining = 0
            retry_after = int(dq[0] - cutoff) + 1
            return False, retry_after

        dq.append(now)
        remaining = limit - len(dq)
        return True, remaining


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Per-user sliding-window rate limiter.

    Reads ``limit`` and ``window`` from the application settings so they
    can be changed without modifying this file.
    """

    def __init__(self, app: ASGIApp, limit: int = 100, window: int = 60) -> None:
        super().__init__(app)
        self._limit = limit
        self._window = window

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Extract subject from JWT without full validation (already done by
        # the route-level dependency).  We parse the Authorization header
        # ourselves here just for rate-limit bucketing.
        subject = self._extract_subject(request)

        if subject is None:
            # Anonymous – pass through; auth will reject it at the route level
            return await call_next(request)

        allowed, value = _is_allowed(subject, self._limit, float(self._window))

        if allowed:
            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(self._limit)
            response.headers["X-RateLimit-Remaining"] = str(value)
            response.headers["X-RateLimit-Window"] = str(self._window)
            return response

        # rate limit exceeded
        logger.warning("rate limit exceeded", subject=subject)
        return JSONResponse(
            status_code=429,
            headers={
                "Retry-After": str(value),
                "X-RateLimit-Limit": str(self._limit),
                "X-RateLimit-Remaining": "0",
            },
            content={
                "code": "TooManyRequests",
                "message": (
                    f"Rate limit of {self._limit} requests per {self._window}s exceeded. "
                    f"Retry after {value}s."
                ),
                "links": [],
            },
        )

    @staticmethod
    def _extract_subject(request: Request) -> str | None:
        """
        Cheaply extract the ``sub`` claim from a Bearer JWT without
        verifying the signature (verification happens at the route level).
        """
        auth = request.headers.get("Authorization", "")
        if not auth.lower().startswith("bearer "):
            return None
        token = auth[7:].strip()
        try:
            import base64
            import json

            parts = token.split(".")
            if len(parts) != 3:
                return None
            # Pad and decode payload
            payload_b64 = parts[1] + "=="
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            return payload.get("sub")
        except Exception:
            return None
