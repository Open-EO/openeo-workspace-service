"""
Internal router: /internal/workspaces/{workspace_id}/status

This endpoint is intended for use by back-end provisioning workers (e.g. a
Celery task, a Kubernetes Job, or a cloud function) that asynchronously
create workspaces and need to report the outcome back to the service.

It is **not** part of the public openEO API surface.  Access is controlled
by a shared secret (``INTERNAL_API_KEY`` setting) rather than Keycloak, so
that provisioning workers do not need to be OIDC clients.

Security model
--------------
The caller must supply the header ``X-Internal-API-Key: <secret>``.
If the header is missing or wrong the endpoint returns 401.
Set ``INTERNAL_API_KEY`` in the environment; if it is unset the endpoint
is disabled entirely (returns 404 for all requests).
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Annotated, Any

import structlog
from elasticsearch import AsyncElasticsearch, NotFoundError
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel

from openeo_workspace_service.config.settings import Settings, get_settings
from openeo_workspace_service.db.elasticsearch import get_es
from openeo_workspace_service.models.workspace import WorkspaceStatus

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["Internal"])


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------


async def _require_internal_key(
    x_internal_api_key: Annotated[str | None, Header(alias="X-Internal-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    expected = getattr(settings, "internal_api_key", None)
    if not expected:
        # Feature disabled – return 404 so the route is invisible
        raise HTTPException(status_code=404, detail="Not found")
    if x_internal_api_key is None or not secrets.compare_digest(x_internal_api_key, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing internal API key.",
        )


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class WorkspaceStatusUpdate(BaseModel):
    """Payload sent by provisioning workers to update workspace state."""

    status: WorkspaceStatus
    details: str | None = None
    url: str | None = None
    properties: dict[str, Any] | None = None
    free: int | None = None


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.put(
    "/workspaces/{workspace_id}/status",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="[Internal] Update workspace provisioning status",
    dependencies=[Depends(_require_internal_key)],
)
async def update_workspace_status(
    workspace_id: str,
    body: WorkspaceStatusUpdate,
    es: AsyncElasticsearch = Depends(get_es),
) -> Response:
    """
    Called by a provisioning worker once the workspace creation is complete
    (or has failed).  Updates the ``status``, ``url``, ``details``, and
    ``properties`` fields of the workspace document.
    """
    # We update without owner check because this is an internal endpoint
    partial: dict[str, Any] = {"status": body.status.value}
    if body.details is not None:
        partial["details"] = body.details
    if body.url is not None:
        partial["url"] = body.url
    if body.properties is not None:
        partial["properties"] = body.properties
    if body.free is not None:
        partial["free"] = body.free

    # Direct ES update (bypass owner check)
    settings = get_settings()
    partial["updated_at"] = datetime.now(UTC).isoformat()

    try:
        await es.update(index=settings.workspace_index, id=workspace_id, doc=partial)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Workspace '{workspace_id}' not found.",
        ) from NotFoundError

    logger.info(
        "workspace status updated (internal)",
        workspace_id=workspace_id,
        new_status=body.status.value,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
