"""Integration tests for pagination on GET /workspaces."""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.app import create_app
from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
from openeo_workspace_service.db.elasticsearch import get_es
from openeo_workspace_service.models.workspace import WorkspaceReady, WorkspaceStatus

OWNER = "pag-user-001"
FAKE_USER = TokenClaims(sub=OWNER, preferred_username="alice", raw={})

# In-memory store
_store: dict[str, dict[str, Any]] = {}


def _reset():
    _store.clear()


def _seed(n: int) -> None:
    for i in range(n):
        _store[f"ws-{i:03d}"] = {
            "id": f"ws-{i:03d}",
            "owner_id": OWNER,
            "type": "S3",
            "status": "ready",
            "title": f"Workspace {i}",
        }


class FakeWorkspaceRepo:
    def __init__(self, *a, **kw): pass

    async def list(self, owner_id: str, limit: int = 10, offset: int = 0, status_filter=None, type_filter=None):
        items = [
            WorkspaceReady(
                id=doc["id"],
                type=doc["type"],
                status=WorkspaceStatus(doc["status"]),
                title=doc.get("title"),
            )
            for doc in _store.values()
            if doc["owner_id"] == owner_id
        ]
        items.sort(key=lambda w: w.id)
        return items[offset: offset + limit]

    async def count(self, owner_id: str, status_filter=None, type_filter=None) -> int:
        return sum(1 for d in _store.values() if d["owner_id"] == owner_id)


class FakeProviderRepo:
    def __init__(self, *a, **kw): pass
    async def list_all(self): return {}
    async def get(self, name): return {"title": name, "intents": ["create"], "parameters": {}, "links": []}


@pytest.fixture(autouse=True)
def reset_store():
    _reset()
    yield
    _reset()


@pytest.fixture
async def client():
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: FAKE_USER
    fake_es = MagicMock()
    app.dependency_overrides[get_es] = lambda: fake_es
    with (
        patch("openeo_workspace_service.api.workspaces.WorkspaceRepository", FakeWorkspaceRepo),
        patch("openeo_workspace_service.api.workspaces.ProviderRepository", FakeProviderRepo),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac


class TestPaginationHeaders:
    @pytest.mark.asyncio
    async def test_total_count_header_present(self, client):
        _seed(15)
        resp = await client.get("/workspaces?limit=10&offset=0")
        assert resp.status_code == 200
        assert resp.headers.get("x-total-count") == "15"

    @pytest.mark.asyncio
    async def test_total_count_zero_when_empty(self, client):
        resp = await client.get("/workspaces")
        assert resp.headers.get("x-total-count") == "0"

    @pytest.mark.asyncio
    async def test_next_link_on_first_full_page(self, client):
        _seed(20)
        resp = await client.get("/workspaces?limit=10&offset=0")
        data = resp.json()
        rels = [lnk["rel"] for lnk in data["links"]]
        assert "next" in rels

    @pytest.mark.asyncio
    async def test_no_next_on_last_partial_page(self, client):
        _seed(7)
        resp = await client.get("/workspaces?limit=10&offset=0")
        data = resp.json()
        rels = [lnk["rel"] for lnk in data["links"]]
        assert "next" not in rels

    @pytest.mark.asyncio
    async def test_prev_link_when_offset_positive(self, client):
        _seed(20)
        resp = await client.get("/workspaces?limit=10&offset=10")
        data = resp.json()
        rels = [lnk["rel"] for lnk in data["links"]]
        assert "prev" in rels

    @pytest.mark.asyncio
    async def test_correct_items_returned_per_page(self, client):
        _seed(25)
        resp = await client.get("/workspaces?limit=5&offset=5")
        assert resp.status_code == 200
        items = resp.json()["workspaces"]
        assert len(items) == 5
        # IDs should be ws-005 through ws-009
        ids = [w["id"] for w in items]
        assert ids[0] == "ws-005"
        assert ids[-1] == "ws-009"

    @pytest.mark.asyncio
    async def test_next_link_contains_correct_offset(self, client):
        _seed(20)
        resp = await client.get("/workspaces?limit=10&offset=0")
        links = resp.json()["links"]
        next_link = next(lnk for lnk in links if lnk["rel"] == "next")
        assert "offset=10" in next_link["href"]
        assert "limit=10" in next_link["href"]
