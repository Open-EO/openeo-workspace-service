"""
Integration tests for the workspace API endpoints.

Strategy:
  - Spin up the FastAPI app with TestClient / AsyncClient (no real network).
  - Override the `get_es` and `get_current_user` FastAPI dependencies so no
    real Elasticsearch or Keycloak is required.
  - An in-memory dict acts as the fake Elasticsearch backing store.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.app import create_app
from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
from openeo_workspace_service.db.elasticsearch import (
    get_es,
)
from openeo_workspace_service.models.workspace import WorkspaceReady, WorkspaceStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FAKE_USER = TokenClaims(
    sub="test-user-001",
    preferred_username="alice",
    email="alice@example.com",
    raw={"sub": "test-user-001"},
)

FAKE_PROVIDERS: dict[str, Any] = {
    "S3": {
        "title": "Amazon S3",
        "intents": ["create", "register"],
        "parameters": {
            "bucket_name": {"description": "Bucket name", "type": "string"},
        },
        "links": [],
    }
}

# In-memory workspace store keyed by workspace_id
_store: dict[str, dict[str, Any]] = {}


def _reset_store() -> None:
    _store.clear()


class FakeWorkspaceRepository:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def list(self, owner_id: str, limit: int = 10, offset: int = 0, status_filter=None, type_filter=None):
        return [
            WorkspaceReady(**{k: v for k, v in doc.items() if k != "owner_id"})
            for doc in _store.values()
            if doc.get("owner_id") == owner_id
            and doc.get("status") == WorkspaceStatus.ready.value
        ]

    async def get(self, workspace_id: str, owner_id: str):
        doc = _store.get(workspace_id)
        if doc is None or doc.get("owner_id") != owner_id:
            return None
        return WorkspaceReady(**{k: v for k, v in doc.items() if k != "owner_id"})

    async def create(self, workspace_id: str, owner_id: str, doc: dict[str, Any]):
        _store[workspace_id] = {**doc, "id": workspace_id, "owner_id": owner_id}
        return WorkspaceReady(
            id=workspace_id,
            type=doc.get("type", "S3"),
            status=WorkspaceStatus(doc.get("status", "provisioning")),
        )

    async def update(self, workspace_id: str, owner_id: str, partial: dict[str, Any]):
        doc = _store.get(workspace_id)
        if doc is None or doc.get("owner_id") != owner_id:
            return False
        doc.update(partial)
        return True

    async def delete(self, workspace_id: str, owner_id: str):
        doc = _store.get(workspace_id)
        if doc is None or doc.get("owner_id") != owner_id:
            return False
        del _store[workspace_id]
        return True

    async def exists(self, workspace_id: str):
        return workspace_id in _store

    async def count(self, owner_id: str, status_filter=None, type_filter=None) -> int:
        return sum(1 for d in _store.values() if d.get("owner_id") == owner_id)


class FakeProviderRepository:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def list_all(self):
        return dict(FAKE_PROVIDERS)

    async def get(self, name: str):
        return FAKE_PROVIDERS.get(name.upper())


@pytest.fixture(autouse=True)
def clear_store():
    _reset_store()
    yield
    _reset_store()


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    app = create_app()

    # Override auth
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER

    # Override ES dependency
    fake_es = MagicMock()
    app.dependency_overrides[get_es] = lambda: fake_es

    # Patch the repository classes themselves
    with (
        patch(
            "openeo_workspace_service.api.workspaces.WorkspaceRepository",
            FakeWorkspaceRepository,
        ),
        patch(
            "openeo_workspace_service.api.workspaces.ProviderRepository",
            FakeProviderRepository,
        ),
        patch(
            "openeo_workspace_service.api.workspace_providers.ProviderRepository",
            FakeProviderRepository,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


# ---------------------------------------------------------------------------
# GET /workspace_providers
# ---------------------------------------------------------------------------


class TestWorkspaceProviders:
    @pytest.mark.asyncio
    async def test_list_providers(self, client: AsyncClient):
        resp = await client.get("/workspace_providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "providers" in data
        assert "S3" in data["providers"]
        assert data["providers"]["S3"]["title"] == "Amazon S3"


# ---------------------------------------------------------------------------
# POST /workspaces
# ---------------------------------------------------------------------------


class TestCreateWorkspace:
    @pytest.mark.asyncio
    async def test_create_intent(self, client: AsyncClient):
        resp = await client.post(
            "/workspaces",
            json={"intent": "create", "type": "S3", "title": "My Workspace"},
        )
        assert resp.status_code == 201
        assert "Location" in resp.headers
        assert "OpenEO-Identifier" in resp.headers
        workspace_id = resp.headers["OpenEO-Identifier"]
        assert workspace_id in resp.headers["Location"]

    @pytest.mark.asyncio
    async def test_register_intent(self, client: AsyncClient):
        resp = await client.post(
            "/workspaces",
            json={
                "intent": "register",
                "type": "S3",
                "url": "https://my-bucket.s3.example.com",
                "parameters": {"bucket_name": "my-bucket"},
            },
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_invalid_intent(self, client: AsyncClient):
        resp = await client.post("/workspaces", json={"intent": "unknown"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_missing_url(self, client: AsyncClient):
        resp = await client.post(
            "/workspaces",
            json={"intent": "register", "type": "S3", "parameters": {}},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /workspaces
# ---------------------------------------------------------------------------


class TestListWorkspaces:
    @pytest.mark.asyncio
    async def test_empty_list(self, client: AsyncClient):
        resp = await client.get("/workspaces")
        assert resp.status_code == 200
        data = resp.json()
        assert data["workspaces"] == []
        assert "links" in data

    @pytest.mark.asyncio
    async def test_list_after_create(self, client: AsyncClient):
        # Seed the store directly
        _store["ws-001"] = {
            "id": "ws-001",
            "owner_id": FAKE_USER.sub,
            "type": "S3",
            "status": "ready",
            "title": "Seeded workspace",
        }
        resp = await client.get("/workspaces")
        assert resp.status_code == 200
        assert len(resp.json()["workspaces"]) == 1

    @pytest.mark.asyncio
    async def test_limit_parameter(self, client: AsyncClient):
        resp = await client.get("/workspaces?limit=5")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_status_filter_param_accepted(self, client: AsyncClient):
        resp = await client.get("/workspaces?status=ready")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_type_filter_param_accepted(self, client: AsyncClient):
        resp = await client.get("/workspaces?type=S3")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_invalid_status_filter_rejected(self, client: AsyncClient):
        resp = await client.get("/workspaces?status=nonexistent")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}
# ---------------------------------------------------------------------------


class TestDescribeWorkspace:
    @pytest.mark.asyncio
    async def test_found(self, client: AsyncClient):
        _store["ws-abc"] = {
            "id": "ws-abc",
            "owner_id": FAKE_USER.sub,
            "type": "S3",
            "status": "ready",
            "title": "Test WS",
        }
        resp = await client.get("/workspaces/ws-abc")
        assert resp.status_code == 200
        assert resp.json()["id"] == "ws-abc"

    @pytest.mark.asyncio
    async def test_not_found(self, client: AsyncClient):
        resp = await client.get("/workspaces/does-not-exist")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_other_users_workspace_not_found(self, client: AsyncClient):
        _store["ws-other"] = {
            "id": "ws-other",
            "owner_id": "other-user-999",
            "type": "S3",
            "status": "ready",
        }
        resp = await client.get("/workspaces/ws-other")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /workspaces/{workspace_id}
# ---------------------------------------------------------------------------


class TestUpdateWorkspace:
    @pytest.mark.asyncio
    async def test_update_title(self, client: AsyncClient):
        _store["ws-upd"] = {
            "id": "ws-upd",
            "owner_id": FAKE_USER.sub,
            "type": "S3",
            "status": "ready",
            "title": "Old Title",
        }
        resp = await client.patch("/workspaces/ws-upd", json={"title": "New Title"})
        assert resp.status_code == 204
        assert _store["ws-upd"]["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_update_not_found(self, client: AsyncClient):
        resp = await client.patch("/workspaces/ghost", json={"title": "X"})
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_empty_body_rejected(self, client: AsyncClient):
        _store["ws-emp"] = {
            "id": "ws-emp",
            "owner_id": FAKE_USER.sub,
            "type": "S3",
            "status": "ready",
        }
        resp = await client.patch("/workspaces/ws-emp", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /workspaces/{workspace_id}
# ---------------------------------------------------------------------------


class TestDeleteWorkspace:
    @pytest.mark.asyncio
    async def test_delete_existing(self, client: AsyncClient):
        _store["ws-del"] = {
            "id": "ws-del",
            "owner_id": FAKE_USER.sub,
            "type": "S3",
            "status": "ready",
        }
        resp = await client.delete("/workspaces/ws-del")
        assert resp.status_code == 204
        assert "ws-del" not in _store

    @pytest.mark.asyncio
    async def test_delete_not_found(self, client: AsyncClient):
        resp = await client.delete("/workspaces/ghost")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_other_users_workspace(self, client: AsyncClient):
        _store["ws-foreign"] = {
            "id": "ws-foreign",
            "owner_id": "another-user",
            "type": "S3",
            "status": "ready",
        }
        resp = await client.delete("/workspaces/ws-foreign")
        assert resp.status_code == 404
        assert "ws-foreign" in _store  # not deleted


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
