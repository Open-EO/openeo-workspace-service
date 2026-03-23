"""
openeo_workspace_service/routers/providers.py
----------------------------------------------
GET /workspace_providers
"""
from __future__ import annotations

from fastapi import APIRouter

from openeo_workspace_service.models.schemas import WorkspaceProvidersResponse
from openeo_workspace_service.providers import all_providers

router = APIRouter(tags=["Workspaces"])


@router.get(
    "/workspace_providers",
    response_model=WorkspaceProvidersResponse,
    summary="Supported workspace providers",
    operation_id="list-workspace-providers",
)
async def list_workspace_providers() -> WorkspaceProvidersResponse:
    """
    Lists all workspace providers supported by this back-end, together with
    their required/optional parameters.

    Authentication is optional – the spec allows both authenticated and
    unauthenticated access to this discovery endpoint.
    """
    return WorkspaceProvidersResponse(
        providers={name: provider.metadata for name, provider in all_providers().items()}
    )
