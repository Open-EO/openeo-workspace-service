"""
Router: /workspaces and /workspaces/{workspace_id}

Implements:
  GET    /workspaces
  POST   /workspaces
  GET    /workspaces/{workspace_id}
  PATCH  /workspaces/{workspace_id}
  DELETE /workspaces/{workspace_id}
"""
from __future__ import annotations

from typing import Annotated, Any, Union

import structlog
from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from openeo_workspace_service.api.pagination import build_pagination_links
from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
from openeo_workspace_service.config.settings import Settings, get_settings
from openeo_workspace_service.db.elasticsearch import (
    ProviderRepository,
    WorkspaceRepository,
    get_es,
)
from openeo_workspace_service.models.id_generator import make_workspace_id
from openeo_workspace_service.models.workspace import (
    CreateWorkspaceRequest,
    Link,
    RegisterWorkspaceRequest,
    UpdateWorkspaceRequest,
    WorkspaceIntent,
    WorkspaceReady,
    WorkspacesListResponse,
    WorkspaceStatus,
    WorkspaceUnavailable,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Workspaces"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workspace_location(workspace_id: str, settings: Settings, request_base: str) -> str:
    """Build the absolute URL for the Location header."""
    return f"{request_base.rstrip('/')}/workspaces/{workspace_id}"


async def _resolve_provider_type(
    requested_type: str | None,
    repo: ProviderRepository,
    settings: Settings,
) -> str:
    """
    Return the validated provider name.

    Falls back to ``settings.default_workspace_provider`` when ``requested_type``
    is None/null, then validates the name exists in the catalogue.
    """
    provider_name = requested_type or settings.default_workspace_provider
    if provider_name is None:
        # Use the first available provider as last resort
        all_providers = await repo.list_all()
        if not all_providers:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No workspace providers are configured on this back-end.",
            )
        provider_name = next(iter(all_providers))

    provider = await repo.get(provider_name)
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown workspace provider: '{provider_name}'.",
        )
    return provider_name.upper()


# ---------------------------------------------------------------------------
# GET /workspaces
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces",
    response_model=WorkspacesListResponse,
    summary="List all workspaces",
    operation_id="list-workspaces",
)
async def list_workspaces(
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=500, description="Maximum number of results")] = 10,
    offset: Annotated[int, Query(ge=0, description="Number of results to skip")] = 0,
    status: Annotated[WorkspaceStatus | None, Query(description="Filter by workspace status")] = None,
    type: Annotated[str | None, Query(description="Filter by provider type, e.g. S3")] = None,
    es: AsyncElasticsearch = Depends(get_es),
    user: TokenClaims = Depends(get_current_user),
) -> WorkspacesListResponse:
    """
    Returns all workspaces belonging to the authenticated user.
    Scalar-only metadata is returned per spec recommendation; clients should
    call ``GET /workspaces/{workspace_id}`` for the full record.
    """
    repo = WorkspaceRepository(es)
    workspaces = await repo.list(
        owner_id=user.sub, limit=limit, offset=offset,
        status_filter=status, type_filter=type,
    )

    # Strip heavy optional fields for the list view
    slim: list[WorkspaceReady | WorkspaceUnavailable] = []
    for ws in workspaces:
        if isinstance(ws, WorkspaceReady):
            slim.append(
                WorkspaceReady(
                    id=ws.id,
                    title=ws.title,
                    type=ws.type,
                    status=ws.status,
                    details=ws.details,
                )
            )
        else:
            slim.append(ws)

    base_url = str(request.url).split("?")[0]
    links = build_pagination_links(base_url, limit=limit, offset=offset, returned=len(slim))

    # Expose total count for clients that want to render pagination UI
    total = await repo.count(owner_id=user.sub, status_filter=status, type_filter=type)
    response.headers["X-Total-Count"] = str(total)

    return WorkspacesListResponse(workspaces=slim, links=[Link(**lnk) for lnk in links])


# ---------------------------------------------------------------------------
# POST /workspaces
# ---------------------------------------------------------------------------


@router.post(
    "/workspaces",
    status_code=status.HTTP_201_CREATED,
    summary="Create Workspace",
    operation_id="create-workspace",
    response_class=Response,
)
async def create_workspace(
    body: dict[str, Any],
    es: AsyncElasticsearch = Depends(get_es),
    settings: Settings = Depends(get_settings),
    user: TokenClaims = Depends(get_current_user),
) -> Response:
    """
    Creates (intent=``create``) or registers (intent=``register``) a workspace.

    The spec uses a discriminated union on ``intent``; we parse it manually so
    both variants can share this single route.
    """
    intent_raw = body.get("intent")
    if intent_raw not in (WorkspaceIntent.create.value, WorkspaceIntent.register.value):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"'intent' must be one of: create, register.  Got: '{intent_raw}'.",
        )

    intent = WorkspaceIntent(intent_raw)
    provider_repo = ProviderRepository(es)
    workspace_repo = WorkspaceRepository(es)

    # Generate a human-readable workspace ID from the title
    title_hint = body.get("title")
    workspace_id = make_workspace_id(title_hint)

    if intent == WorkspaceIntent.create:
        req = CreateWorkspaceRequest.model_validate(body)
        provider_type = await _resolve_provider_type(req.type, provider_repo, settings)

        doc: dict[str, Any] = {
            "type": provider_type,
            "status": WorkspaceStatus.provisioning.value,
            "title": req.title,
            "description": req.description,
            "quota": req.quota,
            "parameters": req.parameters or {},
        }

    else:  # register
        req_reg = RegisterWorkspaceRequest.model_validate(body)
        provider_type = await _resolve_provider_type(req_reg.type, provider_repo, settings)

        doc = {
            "type": provider_type,
            "status": WorkspaceStatus.ready.value,
            "title": req_reg.title,
            "description": req_reg.description,
            "quota": req_reg.quota,
            "url": req_reg.url,
            "parameters": req_reg.parameters,
        }

    await workspace_repo.create(workspace_id=workspace_id, owner_id=user.sub, doc=doc)
    logger.info(
        "workspace created",
        workspace_id=workspace_id,
        owner=user.sub,
        intent=intent.value,
        provider=provider_type,
    )

    location = f"/workspaces/{workspace_id}"
    return Response(
        status_code=status.HTTP_201_CREATED,
        headers={
            "Location": location,
            "OpenEO-Identifier": workspace_id,
        },
    )


# ---------------------------------------------------------------------------
# GET /workspaces/{workspace_id}
# ---------------------------------------------------------------------------


@router.get(
    "/workspaces/{workspace_id}",
    response_model=Union[WorkspaceReady, WorkspaceUnavailable],
    summary="Full metadata for a workspace",
    operation_id="describe-workspace",
)
async def describe_workspace(
    workspace_id: str,
    es: AsyncElasticsearch = Depends(get_es),
    user: TokenClaims = Depends(get_current_user),
) -> WorkspaceReady | WorkspaceUnavailable:
    repo = WorkspaceRepository(es)
    workspace = await repo.get(workspace_id, owner_id=user.sub)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{workspace_id}' not found.",
        )
    return workspace


# ---------------------------------------------------------------------------
# PATCH /workspaces/{workspace_id}
# ---------------------------------------------------------------------------


@router.patch(
    "/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update workspace details",
    operation_id="update-workspace",
)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceRequest,
    es: AsyncElasticsearch = Depends(get_es),
    user: TokenClaims = Depends(get_current_user),
) -> Response:
    repo = WorkspaceRepository(es)

    partial: dict[str, Any] = {}
    if body.title is not None:
        partial["title"] = body.title
    if body.description is not None:
        partial["description"] = body.description

    if not partial:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one of 'title' or 'description' must be provided.",
        )

    updated = await repo.update(workspace_id, owner_id=user.sub, partial=partial)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{workspace_id}' not found.",
        )

    logger.info("workspace updated", workspace_id=workspace_id, owner=user.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# DELETE /workspaces/{workspace_id}
# ---------------------------------------------------------------------------


@router.delete(
    "/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Workspace",
    operation_id="delete-workspace",
)
async def delete_workspace(
    workspace_id: str,
    es: AsyncElasticsearch = Depends(get_es),
    user: TokenClaims = Depends(get_current_user),
) -> Response:
    repo = WorkspaceRepository(es)
    deleted = await repo.delete(workspace_id, owner_id=user.sub)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{workspace_id}' not found.",
        )

    logger.info("workspace deleted", workspace_id=workspace_id, owner=user.sub)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
