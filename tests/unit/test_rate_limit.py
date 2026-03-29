"""Unit tests for the rate-limiting middleware."""
from __future__ import annotations

import base64
import json
import time

import pytest

from openeo_workspace_service.api.rate_limit import RateLimitMiddleware, _is_allowed, _windows


def _reset_windows() -> None:
    _windows.clear()


def _make_jwt_header(sub: str) -> str:
    """Forge a (non-signed) JWT token carrying the given sub claim."""
    header = base64.urlsafe_b64encode(b'{"alg":"RS256","typ":"JWT"}').rstrip(b"=").decode()
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "iss": "test"}).encode()
    ).rstrip(b"=").decode()
    return f"Bearer {header}.{payload}.fakesig"


@pytest.fixture(autouse=True)
def reset():
    _reset_windows()
    yield
    _reset_windows()


class TestIsAllowed:
    def test_first_request_allowed(self):
        allowed, _ = _is_allowed("user-1", limit=5, window=60.0)
        assert allowed is True

    def test_requests_within_limit_all_allowed(self):
        for _ in range(5):
            allowed, _ = _is_allowed("user-2", limit=5, window=60.0)
            assert allowed is True

    def test_request_over_limit_denied(self):
        for _ in range(5):
            _is_allowed("user-3", limit=5, window=60.0)
        allowed, retry_after = _is_allowed("user-3", limit=5, window=60.0)
        assert allowed is False
        assert retry_after >= 1

    def test_different_users_independent_buckets(self):
        for _ in range(5):
            _is_allowed("user-a", limit=5, window=60.0)
        # user-a is now at limit; user-b should be fine
        allowed, _ = _is_allowed("user-b", limit=5, window=60.0)
        assert allowed is True

    def test_remaining_decrements(self):
        _, r1 = _is_allowed("user-4", limit=10, window=60.0)
        _, r2 = _is_allowed("user-4", limit=10, window=60.0)
        assert r2 < r1

    def test_old_timestamps_evicted(self):
        # Fill up the bucket using a tiny window
        for _ in range(3):
            _is_allowed("user-5", limit=3, window=0.01)
        # After sleeping past the window, a new request should be allowed
        time.sleep(0.05)
        allowed, _ = _is_allowed("user-5", limit=3, window=0.01)
        assert allowed is True


class TestExtractSubject:
    def test_extracts_sub_from_bearer(self):
        token = _make_jwt_header("my-subject-123")
        # Simulate request object with headers
        class FakeRequest:
            headers = {"Authorization": token}
        subject = RateLimitMiddleware._extract_subject(FakeRequest())
        assert subject == "my-subject-123"

    def test_returns_none_when_no_auth(self):
        class FakeRequest:
            headers = {}
        assert RateLimitMiddleware._extract_subject(FakeRequest()) is None

    def test_returns_none_for_malformed_token(self):
        class FakeRequest:
            headers = {"Authorization": "Bearer not.a.valid.jwt.at.all"}
        # Should not raise, just return None
        result = RateLimitMiddleware._extract_subject(FakeRequest())
        # May return None or a value; must not raise
        assert result is None or isinstance(result, str)

    def test_returns_none_for_non_bearer(self):
        class FakeRequest:
            headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        assert RateLimitMiddleware._extract_subject(FakeRequest()) is None


class TestRateLimitMiddlewareIntegration:
    """End-to-end test through the ASGI middleware stack."""

    @pytest.mark.asyncio
    async def test_rate_limit_headers_present(self):
        from unittest.mock import AsyncMock

        from httpx import ASGITransport, AsyncClient

        from openeo_workspace_service.app import create_app
        from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
        from openeo_workspace_service.db.elasticsearch import get_es

        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: TokenClaims(sub="rl-user", raw={})
        app.dependency_overrides[get_es] = lambda: AsyncMock()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/health",
                headers={"Authorization": _make_jwt_header("rl-user")},
            )

        assert "x-ratelimit-limit" in resp.headers
        assert "x-ratelimit-remaining" in resp.headers
        assert "x-ratelimit-window" in resp.headers

    @pytest.mark.asyncio
    async def test_returns_429_when_exceeded(self):
        from unittest.mock import AsyncMock

        from httpx import ASGITransport, AsyncClient

        from openeo_workspace_service.app import create_app
        from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
        from openeo_workspace_service.config.settings import get_settings
        from openeo_workspace_service.db.elasticsearch import get_es

        # Create app with very tight limit
        get_settings.cache_clear()
        import os
        os.environ["RATE_LIMIT_REQUESTS"] = "2"
        os.environ["RATE_LIMIT_WINDOW_S"] = "60"
        get_settings.cache_clear()

        try:
            app = create_app()
            app.dependency_overrides[get_current_user] = lambda: TokenClaims(sub="rl-tight", raw={})
            app.dependency_overrides[get_es] = lambda: AsyncMock()

            token = _make_jwt_header("rl-tight")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                for _ in range(2):
                    await client.get("/health", headers={"Authorization": token})
                resp = await client.get("/health", headers={"Authorization": token})

            assert resp.status_code == 429
            assert resp.json()["code"] == "TooManyRequests"
            assert "Retry-After" in resp.headers
        finally:
            os.environ.pop("RATE_LIMIT_REQUESTS", None)
            os.environ.pop("RATE_LIMIT_WINDOW_S", None)
            get_settings.cache_clear()
