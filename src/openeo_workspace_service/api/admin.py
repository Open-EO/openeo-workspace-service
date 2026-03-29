"""
Admin router: /admin/workspaces

Provides privileged operations that require the ``workspace-admin`` Keycloak
realm role.  These endpoints allow administrators to inspect and delete any
user's workspaces, regardless of ownership.

All routes are prefixed with ``/admin`` and gated behind ``RequireRole``.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from elasticsearch import AsyncElasticsearch, NotFoundError
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from openeo_workspace_service.auth.keycloak import RequireRole, TokenClaims
from openeo_workspace_service.config.settings import get_settings
from openeo_workspace_service.db.elasticsearch import ProviderRepository, get_es
from openeo_workspace_service.models.workspace import (
    WorkspaceReady,
    WorkspacesListResponse,
    WorkspaceStatus,
    WorkspaceUnavailable,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])

_require_admin = RequireRole("workspace-admin")


# ---------------------------------------------------------------------------
# Repository helper (direct ES search, not owner-scoped)
# ---------------------------------------------------------------------------


async def _list_all_workspaces(
    es: AsyncElasticsearch,
    limit: int = 50,
    offset: int = 0,
    owner_filter: str | None = None,
) -> list[dict[str, Any]]:
    query: dict[str, Any] = {"term": {"owner_id": owner_filter}} if owner_filter else {"match_all": {}}
    resp = await es.search(
        index=_index(es),
        body={
            "query": query,
            "from": offset,
            "size": limit,
            "sort": [{"created_at": "desc"}],
        },
    )
    return [hit["_source"] for hit in resp["hits"]["hits"]]


def _index(es: AsyncElasticsearch) -> str:

    return get_settings().workspace_index


def _doc_to_model(src: dict[str, Any]) -> WorkspaceReady | WorkspaceUnavailable:
    status_val = WorkspaceStatus(src.get("status", "unavailable"))
    if status_val == WorkspaceStatus.ready:
        return WorkspaceReady(**{k: v for k, v in src.items() if k != "owner_id"})
    return WorkspaceUnavailable(**{k: v for k, v in src.items() if k != "owner_id"})


# ---------------------------------------------------------------------------
# GET /admin/workspaces
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces",
    response_model=WorkspacesListResponse,
    summary="[Admin] List all workspaces across all users",
)
async def admin_list_workspaces(
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    owner_id: Annotated[str | None, Query(description="Filter by owner subject")] = None,
    es: AsyncElasticsearch = Depends(get_es),
    admin: TokenClaims = Depends(_require_admin),
) -> WorkspacesListResponse:
    """Return all workspaces (optionally filtered by ``owner_id``)."""
    docs = await _list_all_workspaces(es, limit=limit, offset=offset, owner_filter=owner_id)
    workspaces = [_doc_to_model(doc) for doc in docs]
    logger.info(
        "admin list workspaces",
        admin=admin.sub,
        count=len(workspaces),
        owner_filter=owner_id,
    )
    return WorkspacesListResponse(workspaces=workspaces, links=[])


# ---------------------------------------------------------------------------
# GET /admin/workspaces/{workspace_id}
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceReady | WorkspaceUnavailable,
    summary="[Admin] Get any workspace by ID",
)
async def admin_get_workspace(
    workspace_id: str,
    es: AsyncElasticsearch = Depends(get_es),
    admin: TokenClaims = Depends(_require_admin),
) -> WorkspaceReady | WorkspaceUnavailable:
    try:
        resp = await es.get(index=_index(es), id=workspace_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found.") from NotFoundError

    return _doc_to_model(resp["_source"])


# ---------------------------------------------------------------------------
# DELETE /admin/workspaces/{workspace_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[Admin] Delete any workspace by ID",
)
async def admin_delete_workspace(
    workspace_id: str,
    es: AsyncElasticsearch = Depends(get_es),
    admin: TokenClaims = Depends(_require_admin),
) -> Response:
    try:
        await es.delete(index=_index(es), id=workspace_id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Workspace '{workspace_id}' not found.") from NotFoundError

    logger.info("admin deleted workspace", workspace_id=workspace_id, admin=admin.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# POST /admin/providers  – upsert a provider record
# ---------------------------------------------------------------------------


@router.post(
    "/providers/{provider_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[Admin] Create or update a workspace provider",
)
async def admin_upsert_provider(
    provider_name: str,
    body: dict[str, Any],
    es: AsyncElasticsearch = Depends(get_es),
    admin: TokenClaims = Depends(_require_admin),
) -> Response:

    repo = ProviderRepository(es)
    await repo.upsert(provider_name.upper(), body)
    logger.info("admin upserted provider", name=provider_name.upper(), admin=admin.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# DELETE /admin/providers/{provider_name}
# ---------------------------------------------------------------------------


@router.delete(
    "/providers/{provider_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[Admin] Delete a workspace provider",
)
async def admin_delete_provider(
    provider_name: str,
    es: AsyncElasticsearch = Depends(get_es),
    admin: TokenClaims = Depends(_require_admin),
) -> Response:
    try:
        await es.delete(index=get_settings().provider_index, id=provider_name.upper())
    except NotFoundError:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_name}' not found.") from NotFoundError
    logger.info("admin deleted provider", name=provider_name.upper(), admin=admin.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
