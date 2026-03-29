"""Integration tests for the admin router (/admin/workspaces, /admin/providers)."""
from __future__ import annotations

from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.app import create_app
from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
from openeo_workspace_service.db.elasticsearch import get_es

# ---------------------------------------------------------------------------
# Shared test users
# ---------------------------------------------------------------------------

ADMIN_USER = TokenClaims(
    sub="admin-sub-001",
    preferred_username="admin",
    realm_access={"roles": ["workspace-admin", "workspace-user"]},
    raw={},
)

REGULAR_USER = TokenClaims(
    sub="regular-sub-001",
    preferred_username="bob",
    realm_access={"roles": ["workspace-user"]},
    raw={},
)

# In-memory stores
_ws_store: dict[str, dict[str, Any]] = {}
_prov_store: dict[str, dict[str, Any]] = {}


def _reset() -> None:
    _ws_store.clear()
    _prov_store.clear()


# ---------------------------------------------------------------------------
# Fake repositories for admin routes
# ---------------------------------------------------------------------------


class FakeAdminES:
    """Minimal fake that admin.py accesses directly (not via repository classes)."""

    async def search(self, index: str, body: dict) -> dict:
        owner_filter = (
            body.get("query", {}).get("term", {}).get("owner_id")
        )
        docs = list(_ws_store.values())
        if owner_filter:
            docs = [d for d in docs if d.get("owner_id") == owner_filter]
        return {"hits": {"hits": [{"_source": d} for d in docs]}}

    async def get(self, index: str, id: str) -> dict:
        from elasticsearch import NotFoundError

        if index.endswith("providers"):
            doc = _prov_store.get(id)
        else:
            doc = _ws_store.get(id)
        if doc is None:
            raise NotFoundError(404, {}, {})
        return {"_source": doc}

    async def delete(self, index: str, id: str) -> None:
        from elasticsearch import NotFoundError

        if index.endswith("providers"):
            if id not in _prov_store:
                raise NotFoundError(404, {}, {})
            del _prov_store[id]
        else:
            if id not in _ws_store:
                raise NotFoundError(404, {}, {})
            del _ws_store[id]

    async def index(self, index: str, id: str, document: dict) -> None:
        if index.endswith("providers"):
            _prov_store[id] = document
        else:
            _ws_store[id] = document


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_client(user: TokenClaims) -> AsyncClient:
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: user
    fake_es = FakeAdminES()
    app.dependency_overrides[get_es] = lambda: fake_es
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def reset_stores():
    _reset()
    yield
    _reset()


# ---------------------------------------------------------------------------
# Admin list workspaces
# ---------------------------------------------------------------------------


class TestAdminListWorkspaces:
    @pytest.mark.asyncio
    async def test_admin_can_list_all(self):
        _ws_store["ws-a"] = {"id": "ws-a", "owner_id": "user-1", "type": "S3", "status": "ready"}
        _ws_store["ws-b"] = {"id": "ws-b", "owner_id": "user-2", "type": "S3", "status": "ready"}

        async with _make_client(ADMIN_USER) as client:
            resp = await client.get("/admin/workspaces")
        assert resp.status_code == 200
        assert len(resp.json()["workspaces"]) == 2

    @pytest.mark.asyncio
    async def test_regular_user_is_forbidden(self):
        async with _make_client(REGULAR_USER) as client:
            resp = await client.get("/admin/workspaces")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_can_filter_by_owner(self):
        _ws_store["ws-1"] = {"id": "ws-1", "owner_id": "user-A", "type": "S3", "status": "ready"}
        _ws_store["ws-2"] = {"id": "ws-2", "owner_id": "user-B", "type": "S3", "status": "ready"}

        async with _make_client(ADMIN_USER) as client:
            resp = await client.get("/admin/workspaces?owner_id=user-A")
        assert resp.status_code == 200
        workspaces = resp.json()["workspaces"]
        assert len(workspaces) == 1
        assert workspaces[0]["id"] == "ws-1"


# ---------------------------------------------------------------------------
# Admin get workspace
# ---------------------------------------------------------------------------


class TestAdminGetWorkspace:
    @pytest.mark.asyncio
    async def test_admin_can_get_any_workspace(self):
        _ws_store["ws-x"] = {
            "id": "ws-x",
            "owner_id": "some-other-user",
            "type": "S3",
            "status": "ready",
        }
        async with _make_client(ADMIN_USER) as client:
            resp = await client.get("/admin/workspaces/ws-x")
        assert resp.status_code == 200
        assert resp.json()["id"] == "ws-x"

    @pytest.mark.asyncio
    async def test_returns_404_for_missing(self):
        async with _make_client(ADMIN_USER) as client:
            resp = await client.get("/admin/workspaces/ghost")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Admin delete workspace
# ---------------------------------------------------------------------------


class TestAdminDeleteWorkspace:
    @pytest.mark.asyncio
    async def test_admin_can_delete_any_workspace(self):
        _ws_store["ws-del"] = {
            "id": "ws-del",
            "owner_id": "some-user",
            "type": "S3",
            "status": "ready",
        }
        async with _make_client(ADMIN_USER) as client:
            resp = await client.delete("/admin/workspaces/ws-del")
        assert resp.status_code == 204
        assert "ws-del" not in _ws_store

    @pytest.mark.asyncio
    async def test_regular_user_cannot_delete(self):
        _ws_store["ws-prot"] = {
            "id": "ws-prot",
            "owner_id": REGULAR_USER.sub,
            "type": "S3",
            "status": "ready",
        }
        async with _make_client(REGULAR_USER) as client:
            resp = await client.delete("/admin/workspaces/ws-prot")
        assert resp.status_code == 403
        assert "ws-prot" in _ws_store  # not deleted


# ---------------------------------------------------------------------------
# Admin upsert provider
# ---------------------------------------------------------------------------


class TestAdminUpsertProvider:
    @pytest.mark.asyncio
    async def test_upsert_provider(self):
        async with _make_client(ADMIN_USER) as client:
            resp = await client.post(
                "/admin/providers/SWIFT",
                json={
                    "title": "OpenStack Swift",
                    "intents": ["register"],
                    "parameters": {"endpoint": {"type": "string"}},
                    "links": [],
                },
            )
        assert resp.status_code == 204
        assert "SWIFT" in _prov_store

    @pytest.mark.asyncio
    async def test_regular_user_cannot_upsert_provider(self):
        async with _make_client(REGULAR_USER) as client:
            resp = await client.post("/admin/providers/SWIFT", json={})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Admin delete provider
# ---------------------------------------------------------------------------


class TestAdminDeleteProvider:
    @pytest.mark.asyncio
    async def test_delete_existing_provider(self):
        _prov_store["MYCLOUD"] = {"name": "MYCLOUD", "title": "My Cloud"}
        async with _make_client(ADMIN_USER) as client:
            resp = await client.delete("/admin/providers/MYCLOUD")
        assert resp.status_code == 204
        assert "MYCLOUD" not in _prov_store

    @pytest.mark.asyncio
    async def test_delete_missing_provider_returns_404(self):
        async with _make_client(ADMIN_USER) as client:
            resp = await client.delete("/admin/providers/NONEXISTENT")
        assert resp.status_code == 404
