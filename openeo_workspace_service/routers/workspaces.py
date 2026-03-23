"""
openeo_workspace_service/routers/workspaces.py
-----------------------------------------------
Implements the full /workspaces resource:

  GET    /workspaces                  – list all workspaces for the caller
  POST   /workspaces                  – create or register a new workspace
  GET    /workspaces/{workspace_id}   – full metadata for one workspace
  DELETE /workspaces/{workspace_id}   – remove a workspace
  PATCH  /workspaces/{workspace_id}   – update title / description
"""
from __future__ import annotations

import re
import uuid
import logging
from typing import Annotated, Union

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openeo_workspace_service.auth import current_user
from openeo_workspace_service.config import settings
from openeo_workspace_service.db.models import WorkspaceRecord
from openeo_workspace_service.db.session import get_session
from openeo_workspace_service.models.schemas import (
    CreateWorkspaceBody,
    RegisterWorkspaceBody,
    UpdateWorkspaceBody,
    WorkspaceListResponse,
    WorkspaceResponse,
    WorkspaceStatus,
)
from openeo_workspace_service.providers import all_providers, get_provider

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Workspaces"])

_ID_PATTERN = re.compile(r"^[\w\-\.~]+$")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _record_to_response(record: WorkspaceRecord) -> WorkspaceResponse:
    resp = WorkspaceResponse(
        id=record.id,
        title=record.title,
        description=record.description,
        type=record.provider_type,
        status=WorkspaceStatus(record.status),
        details=record.details,
        quota=record.quota,
    )
    if record.status == WorkspaceStatus.ready:
        resp.url = record.url
        resp.properties = record.properties or None
        resp.free = record.free
    return resp


async def _get_owned_workspace(
    workspace_id: str,
    user: str,
    session: AsyncSession,
) -> WorkspaceRecord:
    result = await session.execute(
        select(WorkspaceRecord).where(
            WorkspaceRecord.id == workspace_id,
            WorkspaceRecord.owner == user,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workspace not found.")
    return record


def _pagination_links(
    path: str,
    limit: int,
    offset: int,
    total: int,
) -> list[dict]:
    links: list[dict] = []
    base = f"{settings.public_url.rstrip('/')}{path}"
    if offset + limit < total:
        links.append(
            {
                "rel": "next",
                "href": f"{base}?limit={limit}&offset={offset + limit}",
                "type": "application/json",
            }
        )
    if offset > 0:
        prev_offset = max(0, offset - limit)
        links.append(
            {
                "rel": "prev",
                "href": f"{base}?limit={limit}&offset={prev_offset}",
                "type": "application/json",
            }
        )
    return links


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get(
    "/workspaces",
    response_model=WorkspaceListResponse,
    summary="List all workspaces",
    operation_id="list-workspaces",
)
async def list_workspaces(
    limit: Annotated[int, Query(ge=1, le=settings.page_size_max)] = settings.page_size_default,
    offset: Annotated[int, Query(ge=0)] = 0,
    user: str = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceListResponse:
    result = await session.execute(
        select(WorkspaceRecord)
        .where(WorkspaceRecord.owner == user)
        .order_by(WorkspaceRecord.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    records = result.scalars().all()

    # Count total for pagination links.
    from sqlalchemy import func
    count_result = await session.execute(
        select(func.count()).where(WorkspaceRecord.owner == user)
    )
    total: int = count_result.scalar_one()

    return WorkspaceListResponse(
        workspaces=[_record_to_response(r) for r in records],
        links=_pagination_links("/workspaces", limit, offset, total),
    )


@router.post(
    "/workspaces",
    status_code=status.HTTP_201_CREATED,
    summary="Create Workspace",
    operation_id="create-workspace",
)
async def create_workspace(
    body: Annotated[Union[CreateWorkspaceBody, RegisterWorkspaceBody], ...],
    response: Response,
    user: str = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    # Resolve provider type.
    if body.intent == "create":
        provider_type = (body.type or settings.default_workspace_provider or "").upper()
        if not provider_type:
            available = list(all_providers().keys())
            if not available:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="No workspace providers are configured on this back-end.",
                )
            provider_type = available[0]
    else:
        provider_type = body.type.upper()

    # Validate provider exists.
    try:
        provider = get_provider(provider_type)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown workspace provider: {body.type!r}",
        )

    # Validate provider-specific parameters.
    params = getattr(body, "parameters", {}) or {}
    try:
        provider.validate_parameters(params)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    # Generate a unique workspace id.
    workspace_id = str(uuid.uuid4())

    record = WorkspaceRecord(
        id=workspace_id,
        owner=user,
        title=body.title,
        description=body.description,
        provider_type=provider_type,
        status="provisioning",
        quota=getattr(body, "quota", None),
    )
    record.parameters = params
    if body.intent == "register":
        record.url = str(body.url)  # type: ignore[union-attr]

    session.add(record)
    await session.flush()  # assigns id before provisioning

    # Provision (may update status in-place).
    await provider.provision(record)
    await session.commit()
    await session.refresh(record)

    location = f"{settings.public_url.rstrip('/')}/workspaces/{workspace_id}"
    response.headers["Location"] = location
    response.headers["OpenEO-Identifier"] = workspace_id


@router.get(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Full metadata for a workspace",
    operation_id="describe-workspace",
)
async def describe_workspace(
    workspace_id: str,
    user: str = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> WorkspaceResponse:
    record = await _get_owned_workspace(workspace_id, user, session)

    # Refresh status from the provider before returning.
    try:
        provider = get_provider(record.provider_type)
        await provider.refresh_status(record)
        await session.commit()
        await session.refresh(record)
    except KeyError:
        pass  # Unknown provider – return as-is.

    return _record_to_response(record)


@router.delete(
    "/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Workspace",
    operation_id="delete-workspace",
)
async def delete_workspace(
    workspace_id: str,
    user: str = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    record = await _get_owned_workspace(workspace_id, user, session)

    try:
        provider = get_provider(record.provider_type)
        await provider.delete(record)
    except KeyError:
        logger.warning("Provider %r not found; skipping remote deletion.", record.provider_type)

    await session.delete(record)
    await session.commit()


@router.patch(
    "/workspaces/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Update workspace details",
    operation_id="update-workspace",
)
async def update_workspace(
    workspace_id: str,
    body: UpdateWorkspaceBody,
    user: str = Depends(current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    record = await _get_owned_workspace(workspace_id, user, session)

    if body.title is not None:
        record.title = body.title
    if body.description is not None:
        record.description = body.description

    await session.commit()
