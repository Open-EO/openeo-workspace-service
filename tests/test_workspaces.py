"""
tests/test_workspaces.py
-------------------------
Integration tests for the /workspaces resource.

Provider cloud calls are replaced with simple async no-ops so the tests do
not require real AWS / Azure / GCS credentials.
"""
from __future__ import annotations

import pytest

from openeo_workspace_service.db.models import WorkspaceRecord
from openeo_workspace_service.providers import base as providers_base


# ── Helpers ──────────────────────────────────────────────────────────────────

class _NoOpProvider:
    """Stub provider that sets status=ready without touching any cloud service."""

    @property
    def metadata(self):
        from openeo_workspace_service.models.schemas import WorkspaceProvider
        return WorkspaceProvider(
            title="NoOp",
            intents=["create", "register"],
            parameters={},
        )

    def validate_parameters(self, parameters):
        pass

    async def provision(self, record: WorkspaceRecord) -> None:
        record.status = "ready"
        record.url = "https://noop.example/bucket"
        record.properties = {"note": "test"}

    async def delete(self, record: WorkspaceRecord) -> None:
        pass

    async def refresh_status(self, record: WorkspaceRecord) -> None:
        pass


@pytest.fixture(autouse=True)
def _patch_providers(monkeypatch):
    """Replace the provider registry with a single NoOp provider for all tests."""
    noop = _NoOpProvider()
    monkeypatch.setattr(
        providers_base,
        "_REGISTRY",
        {"S3": type("S3Provider", (), {
            "__call__": lambda self: noop,
            **{k: v for k, v in _NoOpProvider.__dict__.items() if not k.startswith("__")}
        })},
    )
    # Simpler: just patch get_provider and all_providers directly.
    monkeypatch.setattr(providers_base, "get_provider", lambda name: noop)
    monkeypatch.setattr(providers_base, "all_providers", lambda: {"S3": noop})


# ── CREATE ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_workspace_returns_201(client, auth_headers):
    resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3", "title": "My Workspace"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
async def test_create_workspace_sets_location_header(client, auth_headers):
    resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3"},
        headers=auth_headers,
    )
    assert "location" in resp.headers
    assert "/workspaces/" in resp.headers["location"]


@pytest.mark.asyncio
async def test_create_workspace_sets_openeo_identifier_header(client, auth_headers):
    resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3"},
        headers=auth_headers,
    )
    assert "openeo-identifier" in resp.headers
    assert len(resp.headers["openeo-identifier"]) > 0


@pytest.mark.asyncio
async def test_register_workspace_requires_url(client, auth_headers):
    resp = await client.post(
        "/workspaces",
        json={"intent": "register", "type": "S3", "parameters": {}},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_workspace_requires_auth(client):
    resp = await client.post("/workspaces", json={"intent": "create", "type": "S3"})
    assert resp.status_code == 403


# ── LIST ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_workspaces_empty(client, auth_headers):
    resp = await client.get("/workspaces", headers={"Authorization": "Bearer fresh_user"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["workspaces"] == []
    assert "links" in body


@pytest.mark.asyncio
async def test_list_workspaces_shows_own_workspaces(client, auth_headers):
    # Create two workspaces.
    for title in ("Alpha", "Beta"):
        await client.post(
            "/workspaces",
            json={"intent": "create", "type": "S3", "title": title},
            headers=auth_headers,
        )

    resp = await client.get("/workspaces", headers=auth_headers)
    assert resp.status_code == 200
    titles = [w["title"] for w in resp.json()["workspaces"]]
    assert "Alpha" in titles
    assert "Beta" in titles


@pytest.mark.asyncio
async def test_list_workspaces_requires_auth(client):
    resp = await client.get("/workspaces")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_workspaces_isolation(client):
    """Workspaces created by one user must not appear for another."""
    await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3", "title": "UserA-ws"},
        headers={"Authorization": "Bearer userA"},
    )
    resp = await client.get("/workspaces", headers={"Authorization": "Bearer userB"})
    titles = [w["title"] for w in resp.json()["workspaces"]]
    assert "UserA-ws" not in titles


# ── DESCRIBE ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_describe_workspace(client, auth_headers):
    create_resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3", "title": "Described"},
        headers=auth_headers,
    )
    ws_id = create_resp.headers["openeo-identifier"]

    resp = await client.get(f"/workspaces/{ws_id}", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == ws_id
    assert body["title"] == "Described"
    assert body["status"] in ("provisioning", "ready", "unavailable")


@pytest.mark.asyncio
async def test_describe_workspace_not_found(client, auth_headers):
    resp = await client.get("/workspaces/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_describe_workspace_cross_user_forbidden(client):
    create_resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3"},
        headers={"Authorization": "Bearer ownerUser"},
    )
    ws_id = create_resp.headers["openeo-identifier"]

    resp = await client.get(
        f"/workspaces/{ws_id}", headers={"Authorization": "Bearer otherUser"}
    )
    assert resp.status_code == 404


# ── UPDATE ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_workspace_title(client, auth_headers):
    create_resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3", "title": "Old Title"},
        headers=auth_headers,
    )
    ws_id = create_resp.headers["openeo-identifier"]

    patch_resp = await client.patch(
        f"/workspaces/{ws_id}",
        json={"title": "New Title"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 204

    describe_resp = await client.get(f"/workspaces/{ws_id}", headers=auth_headers)
    assert describe_resp.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_update_workspace_not_found(client, auth_headers):
    resp = await client.patch(
        "/workspaces/ghost-id",
        json={"title": "Whatever"},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── DELETE ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_workspace(client, auth_headers):
    create_resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3"},
        headers=auth_headers,
    )
    ws_id = create_resp.headers["openeo-identifier"]

    del_resp = await client.delete(f"/workspaces/{ws_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Workspace should now be gone.
    get_resp = await client.get(f"/workspaces/{ws_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_workspace_not_found(client, auth_headers):
    resp = await client.delete("/workspaces/ghost-id", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_workspace_cross_user_forbidden(client):
    create_resp = await client.post(
        "/workspaces",
        json={"intent": "create", "type": "S3"},
        headers={"Authorization": "Bearer realOwner"},
    )
    ws_id = create_resp.headers["openeo-identifier"]

    resp = await client.delete(
        f"/workspaces/{ws_id}", headers={"Authorization": "Bearer intruder"}
    )
    assert resp.status_code == 404
