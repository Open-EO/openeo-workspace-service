"""Integration tests for the internal provisioning status endpoint."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.app import create_app
from openeo_workspace_service.db.elasticsearch import get_es

INTERNAL_KEY = "super-secret-internal-key-123"

# In-memory store used by the fake ES
_ws_store: dict[str, dict[str, Any]] = {}


def _reset():
    _ws_store.clear()


class FakeES:
    async def update(self, index: str, id: str, doc: dict) -> None:
        from elasticsearch import NotFoundError
        if id not in _ws_store:
            raise NotFoundError(404, {}, {})
        _ws_store[id].update(doc)

    async def get(self, index: str, id: str) -> dict:
        from elasticsearch import NotFoundError
        if id not in _ws_store:
            raise NotFoundError(404, {}, {})
        return {"_source": _ws_store[id]}


@pytest.fixture(autouse=True)
def reset():
    _reset()
    yield
    _reset()


@pytest.fixture
def app_with_key():
    """App with INTERNAL_API_KEY configured."""
    with patch.dict(
        "os.environ",
        {"INTERNAL_API_KEY": INTERNAL_KEY},
        clear=False,
    ):
        # Reset the settings cache so the new env var is picked up
        from openeo_workspace_service.config.settings import get_settings
        get_settings.cache_clear()

        app = create_app()
        fake_es = FakeES()
        app.dependency_overrides[get_es] = lambda: fake_es
        yield app

        get_settings.cache_clear()


@pytest.fixture
def app_without_key():
    """App without INTERNAL_API_KEY – internal endpoint should be disabled."""
    from openeo_workspace_service.config.settings import get_settings
    get_settings.cache_clear()
    app = create_app()
    fake_es = FakeES()
    app.dependency_overrides[get_es] = lambda: fake_es
    yield app
    get_settings.cache_clear()


class TestInternalStatusUpdate:
    @pytest.mark.asyncio
    async def test_update_to_ready(self, app_with_key):
        _ws_store["ws-prov"] = {
            "id": "ws-prov",
            "owner_id": "user-1",
            "type": "S3",
            "status": "provisioning",
        }
        async with AsyncClient(
            transport=ASGITransport(app=app_with_key), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/internal/workspaces/ws-prov/status",
                json={"status": "ready", "url": "https://bucket.s3.example.com"},
                headers={"X-Internal-API-Key": INTERNAL_KEY},
            )
        assert resp.status_code == 204
        assert _ws_store["ws-prov"]["status"] == "ready"
        assert _ws_store["ws-prov"]["url"] == "https://bucket.s3.example.com"

    @pytest.mark.asyncio
    async def test_update_to_unavailable_with_details(self, app_with_key):
        _ws_store["ws-fail"] = {
            "id": "ws-fail",
            "owner_id": "user-2",
            "type": "S3",
            "status": "provisioning",
        }
        async with AsyncClient(
            transport=ASGITransport(app=app_with_key), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/internal/workspaces/ws-fail/status",
                json={"status": "unavailable", "details": "Bucket creation failed: quota exceeded"},
                headers={"X-Internal-API-Key": INTERNAL_KEY},
            )
        assert resp.status_code == 204
        assert _ws_store["ws-fail"]["status"] == "unavailable"
        assert "quota" in _ws_store["ws-fail"]["details"]

    @pytest.mark.asyncio
    async def test_missing_key_returns_401(self, app_with_key):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_key), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/internal/workspaces/ws-x/status",
                json={"status": "ready"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_wrong_key_returns_401(self, app_with_key):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_key), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/internal/workspaces/ws-x/status",
                json={"status": "ready"},
                headers={"X-Internal-API-Key": "wrong-key"},
            )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_not_found_returns_404(self, app_with_key):
        async with AsyncClient(
            transport=ASGITransport(app=app_with_key), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/internal/workspaces/ghost/status",
                json={"status": "ready"},
                headers={"X-Internal-API-Key": INTERNAL_KEY},
            )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_endpoint_returns_404_when_key_not_configured(self, app_without_key):
        async with AsyncClient(
            transport=ASGITransport(app=app_without_key), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/internal/workspaces/ws-x/status",
                json={"status": "ready"},
                headers={"X-Internal-API-Key": "any-key"},
            )
        # 404 because the feature is disabled
        assert resp.status_code == 404
