"""
Unit tests for the Elasticsearch repository layer.

All tests use an ``AsyncMock`` in place of a real ``AsyncElasticsearch``
client so no cluster is required.
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from openeo_workspace_service.db.elasticsearch import (
    ProviderRepository,
    WorkspaceRepository,
)
from openeo_workspace_service.models.workspace import WorkspaceReady, WorkspaceStatus, WorkspaceUnavailable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_es(**kwargs) -> AsyncMock:
    """Return a minimal AsyncMock that looks like an AsyncElasticsearch client."""
    es = AsyncMock()
    for attr, val in kwargs.items():
        setattr(es, attr, val)
    return es


def _hit(workspace_id: str, owner_id: str, status: str = "ready", **extra) -> dict:
    """Build a fake ES hit document."""
    return {
        "_id": workspace_id,
        "_source": {
            "id": workspace_id,
            "owner_id": owner_id,
            "type": "S3",
            "status": status,
            "title": f"WS {workspace_id}",
            **extra,
        },
    }


OWNER = "user-sub-123"


# ---------------------------------------------------------------------------
# WorkspaceRepository.get
# ---------------------------------------------------------------------------


class TestWorkspaceRepositoryGet:
    @pytest.mark.asyncio
    async def test_returns_workspace_when_found_and_owner_matches(self):
        es = _make_es()
        es.get = AsyncMock(return_value=_hit("ws-1", OWNER))
        repo = WorkspaceRepository(es)
        result = await repo.get("ws-1", OWNER)
        assert result is not None
        assert result.id == "ws-1"
        assert isinstance(result, WorkspaceReady)

    @pytest.mark.asyncio
    async def test_returns_none_when_owner_does_not_match(self):
        es = _make_es()
        es.get = AsyncMock(return_value=_hit("ws-1", "other-user"))
        repo = WorkspaceRepository(es)
        result = await repo.get("ws-1", OWNER)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self):
        from elasticsearch import NotFoundError

        es = _make_es()
        es.get = AsyncMock(side_effect=NotFoundError(404, {}, {}))
        repo = WorkspaceRepository(es)
        result = await repo.get("missing", OWNER)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_unavailable_workspace(self):
        es = _make_es()
        es.get = AsyncMock(return_value=_hit("ws-2", OWNER, status="provisioning"))
        repo = WorkspaceRepository(es)
        result = await repo.get("ws-2", OWNER)
        assert isinstance(result, WorkspaceUnavailable)
        assert result.status == WorkspaceStatus.provisioning


# ---------------------------------------------------------------------------
# WorkspaceRepository.list
# ---------------------------------------------------------------------------


class TestWorkspaceRepositoryList:
    @pytest.mark.asyncio
    async def test_returns_empty_list(self):
        es = _make_es()
        es.search = AsyncMock(return_value={"hits": {"hits": []}})
        repo = WorkspaceRepository(es)
        result = await repo.list(OWNER)
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_multiple_workspaces(self):
        es = _make_es()
        es.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        _hit("ws-a", OWNER),
                        _hit("ws-b", OWNER, status="provisioning"),
                    ]
                }
            }
        )
        repo = WorkspaceRepository(es)
        result = await repo.list(OWNER)
        assert len(result) == 2
        assert result[0].id == "ws-a"

    @pytest.mark.asyncio
    async def test_search_called_with_owner_filter(self):
        es = _make_es()
        es.search = AsyncMock(return_value={"hits": {"hits": []}})
        repo = WorkspaceRepository(es)
        await repo.list(OWNER, limit=25)
        call_body = es.search.call_args.kwargs["body"]
        assert call_body["query"]["term"]["owner_id"] == OWNER
        assert call_body["size"] == 25


# ---------------------------------------------------------------------------
# WorkspaceRepository.create
# ---------------------------------------------------------------------------


class TestWorkspaceRepositoryListFilters:
    @pytest.mark.asyncio
    async def test_list_with_status_filter_builds_bool_query(self):
        es = _make_es()
        es.search = AsyncMock(return_value={"hits": {"hits": []}})
        repo = WorkspaceRepository(es)
        from openeo_workspace_service.models.workspace import WorkspaceStatus
        await repo.list(OWNER, status_filter=WorkspaceStatus.ready)
        body = es.search.call_args.kwargs["body"]
        # Should be a bool must query, not a plain term query
        assert "bool" in body["query"]
        musts = body["query"]["bool"]["must"]
        status_clause = next((m for m in musts if "term" in m and "status" in m["term"]), None)
        assert status_clause is not None
        assert status_clause["term"]["status"] == "ready"

    @pytest.mark.asyncio
    async def test_list_with_type_filter_uppercases_type(self):
        es = _make_es()
        es.search = AsyncMock(return_value={"hits": {"hits": []}})
        repo = WorkspaceRepository(es)
        await repo.list(OWNER, type_filter="s3")
        body = es.search.call_args.kwargs["body"]
        musts = body["query"]["bool"]["must"]
        type_clause = next((m for m in musts if "term" in m and "type" in m["term"]), None)
        assert type_clause is not None
        assert type_clause["term"]["type"] == "S3"

    @pytest.mark.asyncio
    async def test_list_no_filters_uses_simple_term_query(self):
        es = _make_es()
        es.search = AsyncMock(return_value={"hits": {"hits": []}})
        repo = WorkspaceRepository(es)
        await repo.list(OWNER)
        body = es.search.call_args.kwargs["body"]
        # No filters → simple {"term": {"owner_id": ...}} without bool wrapper
        assert "term" in body["query"]
        assert "bool" not in body["query"]

    @pytest.mark.asyncio
    async def test_count_with_status_filter(self):
        es = _make_es()
        es.count = AsyncMock(return_value={"count": 3})
        repo = WorkspaceRepository(es)
        from openeo_workspace_service.models.workspace import WorkspaceStatus
        result = await repo.count(OWNER, status_filter=WorkspaceStatus.provisioning)
        assert result == 3
        body = es.count.call_args.kwargs["body"]
        assert "bool" in body["query"]


class TestWorkspaceRepositoryCreate:
    @pytest.mark.asyncio
    async def test_create_indexes_document(self):
        es = _make_es()
        es.index = AsyncMock()
        es.indices = AsyncMock()
        es.get = AsyncMock(
            return_value=_hit("ws-new", OWNER, status="provisioning")
        )
        repo = WorkspaceRepository(es)
        result = await repo.create(
            workspace_id="ws-new",
            owner_id=OWNER,
            doc={"type": "S3", "status": "provisioning"},
        )
        es.index.assert_awaited_once()
        call_kwargs = es.index.call_args.kwargs
        assert call_kwargs["id"] == "ws-new"
        assert call_kwargs["document"]["owner_id"] == OWNER
        assert isinstance(result, WorkspaceUnavailable)

    @pytest.mark.asyncio
    async def test_create_injects_timestamps(self):
        es = _make_es()
        es.index = AsyncMock()
        es.indices = AsyncMock()
        es.get = AsyncMock(return_value=_hit("ws-ts", OWNER))
        repo = WorkspaceRepository(es)
        await repo.create("ws-ts", OWNER, {"type": "S3", "status": "ready"})
        doc = es.index.call_args.kwargs["document"]
        assert "created_at" in doc
        assert "updated_at" in doc


# ---------------------------------------------------------------------------
# WorkspaceRepository.update
# ---------------------------------------------------------------------------


class TestWorkspaceRepositoryUpdate:
    @pytest.mark.asyncio
    async def test_update_existing(self):
        es = _make_es()
        es.get = AsyncMock(return_value=_hit("ws-u", OWNER))
        es.update = AsyncMock()
        repo = WorkspaceRepository(es)
        result = await repo.update("ws-u", OWNER, {"title": "New Title"})
        assert result is True
        es.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_not_found_returns_false(self):
        from elasticsearch import NotFoundError

        es = _make_es()
        es.get = AsyncMock(side_effect=NotFoundError(404, {}, {}))
        repo = WorkspaceRepository(es)
        result = await repo.update("ghost", OWNER, {"title": "X"})
        assert result is False


# ---------------------------------------------------------------------------
# WorkspaceRepository.delete
# ---------------------------------------------------------------------------


class TestWorkspaceRepositoryDelete:
    @pytest.mark.asyncio
    async def test_delete_existing(self):
        es = _make_es()
        es.get = AsyncMock(return_value=_hit("ws-d", OWNER))
        es.delete = AsyncMock()
        repo = WorkspaceRepository(es)
        result = await repo.delete("ws-d", OWNER)
        assert result is True
        es.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_not_found_returns_false(self):
        from elasticsearch import NotFoundError

        es = _make_es()
        es.get = AsyncMock(side_effect=NotFoundError(404, {}, {}))
        repo = WorkspaceRepository(es)
        result = await repo.delete("ghost", OWNER)
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_other_owners_workspace_returns_false(self):
        es = _make_es()
        es.get = AsyncMock(return_value=_hit("ws-other", "different-owner"))
        repo = WorkspaceRepository(es)
        result = await repo.delete("ws-other", OWNER)
        assert result is False


# ---------------------------------------------------------------------------
# ProviderRepository
# ---------------------------------------------------------------------------


class TestProviderRepository:
    @pytest.mark.asyncio
    async def test_list_all_returns_providers(self):
        es = _make_es()
        es.search = AsyncMock(
            return_value={
                "hits": {
                    "hits": [
                        {
                            "_id": "S3",
                            "_source": {
                                "name": "S3",
                                "title": "Amazon S3",
                                "intents": ["create"],
                                "parameters": {},
                                "links": [],
                            },
                        }
                    ]
                }
            }
        )
        repo = ProviderRepository(es)
        result = await repo.list_all()
        assert "S3" in result
        assert result["S3"]["title"] == "Amazon S3"

    @pytest.mark.asyncio
    async def test_get_existing_provider(self):
        es = _make_es()
        es.get = AsyncMock(
            return_value={
                "_id": "S3",
                "_source": {
                    "name": "S3",
                    "title": "Amazon S3",
                    "intents": ["create", "register"],
                    "parameters": {},
                    "links": [],
                },
            }
        )
        repo = ProviderRepository(es)
        result = await repo.get("S3")
        assert result is not None
        assert result["title"] == "Amazon S3"
        assert "name" not in result  # should be stripped

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self):
        from elasticsearch import NotFoundError

        es = _make_es()
        es.get = AsyncMock(side_effect=NotFoundError(404, {}, {}))
        repo = ProviderRepository(es)
        result = await repo.get("NONEXISTENT")
        assert result is None

    @pytest.mark.asyncio
    async def test_upsert_calls_index(self):
        es = _make_es()
        es.index = AsyncMock()
        repo = ProviderRepository(es)
        await repo.upsert("GCS", {"title": "Google Cloud Storage", "intents": ["create"]})
        es.index.assert_awaited_once()
        doc = es.index.call_args.kwargs["document"]
        assert doc["name"] == "GCS"


class TestWorkspaceRepositoryCount:
    @pytest.mark.asyncio
    async def test_count_returns_correct_number(self):
        es = _make_es()
        es.count = AsyncMock(return_value={"count": 7})
        repo = WorkspaceRepository(es)
        result = await repo.count(OWNER)
        assert result == 7
        call_body = es.count.call_args.kwargs["body"]
        assert call_body["query"]["term"]["owner_id"] == OWNER

    @pytest.mark.asyncio
    async def test_count_returns_zero_when_empty(self):
        es = _make_es()
        es.count = AsyncMock(return_value={"count": 0})
        repo = WorkspaceRepository(es)
        result = await repo.count(OWNER)
        assert result == 0
