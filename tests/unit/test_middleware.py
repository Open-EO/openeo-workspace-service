"""
Unit tests for:
  - RequestIDMiddleware (X-Request-ID propagation)
  - Global exception handlers (error body shape)
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.app import create_app
from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
from openeo_workspace_service.db.elasticsearch import get_es


def _app():
    app = create_app()
    fake_user = TokenClaims(sub="u1", raw={})
    app.dependency_overrides[get_current_user] = lambda: fake_user
    fake_es = AsyncMock()
    app.dependency_overrides[get_es] = lambda: fake_es
    return app


# ---------------------------------------------------------------------------
# RequestIDMiddleware
# ---------------------------------------------------------------------------


class TestRequestIDMiddleware:
    @pytest.mark.asyncio
    async def test_response_has_request_id_header(self):
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            resp = await client.get("/health")
        assert "x-request-id" in resp.headers
        # Should be a valid UUID
        request_id = resp.headers["x-request-id"]
        uuid.UUID(request_id)  # raises if not valid UUID

    @pytest.mark.asyncio
    async def test_upstream_request_id_is_echoed(self):
        client_id = str(uuid.uuid4())
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/health", headers={"X-Request-ID": client_id}
            )
        assert resp.headers["x-request-id"] == client_id

    @pytest.mark.asyncio
    async def test_each_request_gets_unique_id(self):
        ids = set()
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            for _ in range(10):
                resp = await client.get("/health")
                ids.add(resp.headers["x-request-id"])
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# Exception handler – error body shape
# ---------------------------------------------------------------------------


class TestExceptionHandlers:
    @pytest.mark.asyncio
    async def test_404_has_openeo_error_shape(self):
        async with AsyncClient(
            transport=ASGITransport(app=_app()), base_url="http://test"
        ) as client:
            resp = await client.get("/workspaces/nonexistent-ws-xyz")
        # Auth will fire first (no token for ES call) – or 404 after ES mock
        # Either way the body must have the openEO shape
        data = resp.json()
        assert "code" in data
        assert "message" in data
        assert "links" in data

    @pytest.mark.asyncio
    async def test_422_on_invalid_body(self):
        fake_user = TokenClaims(sub="u1", raw={})
        app = create_app()
        app.dependency_overrides[get_current_user] = lambda: fake_user
        fake_es = AsyncMock()
        app.dependency_overrides[get_es] = lambda: fake_es

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.patch(
                "/workspaces/ws-1",
                content="not-valid-json",
                headers={"Content-Type": "application/json"},
            )
        assert resp.status_code == 422
        data = resp.json()
        assert data["code"] == "ValidationError"
        assert "message" in data
        assert "id" in data  # openEO error id (UUID)

    @pytest.mark.asyncio
    async def test_401_when_no_token(self):
        # Don't override get_current_user – let real auth run
        app = create_app()
        fake_es = AsyncMock()
        app.dependency_overrides[get_es] = lambda: fake_es

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            with patch(
                "openeo_workspace_service.auth.keycloak._get_signing_key",
                new=AsyncMock(return_value=None),
            ):
                resp = await client.get("/workspaces")

        assert resp.status_code == 401
        data = resp.json()
        assert data["code"] in ("AuthenticationRequired", "NotAuthenticated")
        assert "message" in data
