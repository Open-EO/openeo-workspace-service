"""Unit tests for health / readiness endpoints."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.app import create_app
from openeo_workspace_service.auth.keycloak import get_current_user
from openeo_workspace_service.db.elasticsearch import get_es


def _make_app():
    app = create_app()
    # Disable auth for these tests – health endpoints shouldn't need a token
    return app


class TestLiveness:
    @pytest.mark.asyncio
    async def test_liveness_always_200(self):
        app = _make_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestReadiness:
    @pytest.mark.asyncio
    async def test_ready_when_all_checks_pass(self):
        app = _make_app()
        fake_es = AsyncMock()
        fake_es.cluster = AsyncMock()
        fake_es.cluster.health = AsyncMock(return_value={"status": "green"})
        app.dependency_overrides[get_es] = lambda: fake_es

        with patch(
            "openeo_workspace_service.api.health._check_keycloak",
            new=AsyncMock(return_value={"ok": True, "http_status": 200}),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/ready")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["checks"]["elasticsearch"]["ok"] is True
        assert data["checks"]["keycloak"]["ok"] is True

    @pytest.mark.asyncio
    async def test_degraded_when_es_down(self):
        app = _make_app()
        fake_es = AsyncMock()
        fake_es.cluster = AsyncMock()
        fake_es.cluster.health = AsyncMock(side_effect=Exception("Connection refused"))
        app.dependency_overrides[get_es] = lambda: fake_es

        with patch(
            "openeo_workspace_service.api.health._check_keycloak",
            new=AsyncMock(return_value={"ok": True, "http_status": 200}),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/ready")

        assert resp.status_code == 503
        assert resp.json()["status"] == "degraded"
        assert resp.json()["checks"]["elasticsearch"]["ok"] is False

    @pytest.mark.asyncio
    async def test_degraded_when_keycloak_down(self):
        app = _make_app()
        fake_es = AsyncMock()
        fake_es.cluster = AsyncMock()
        fake_es.cluster.health = AsyncMock(return_value={"status": "yellow"})
        app.dependency_overrides[get_es] = lambda: fake_es

        with patch(
            "openeo_workspace_service.api.health._check_keycloak",
            new=AsyncMock(return_value={"ok": False, "error": "timeout"}),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/ready")

        assert resp.status_code == 503
        assert resp.json()["checks"]["keycloak"]["ok"] is False
