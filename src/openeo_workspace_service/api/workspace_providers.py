"""
Router: GET /workspace_providers

Lists available workspace providers (S3, GCS, Azure Blob, etc.) stored in
Elasticsearch.  Authentication is optional per the spec.
"""

from __future__ import annotations

from typing import Any

import structlog
from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends

from openeo_workspace_service.auth.keycloak import TokenClaims, get_optional_user
from openeo_workspace_service.db.elasticsearch import ProviderRepository, get_es
from openeo_workspace_service.models.workspace import (
    Provider,
    WorkspaceProvidersResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Workspaces"])


@router.get(
    "/workspace_providers",
    response_model=WorkspaceProvidersResponse,
    summary="Supported workspace providers",
    operation_id="list-workspace-providers",
)
async def list_workspace_providers(
    es: AsyncElasticsearch = Depends(get_es),
    _user: TokenClaims | None = Depends(get_optional_user),
) -> WorkspaceProvidersResponse:
    """
    Returns a map of all supported workspace provider names and their
    configurable parameters.  This endpoint is publicly accessible but
    may surface additional information to authenticated users in future.
    """
    repo = ProviderRepository(es)
    raw_providers: dict[str, Any] = await repo.list_all()

    providers: dict[str, Provider] = {}
    for name, data in raw_providers.items():
        try:
            providers[name] = Provider.model_validate(data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("skipping malformed provider", name=name, error=str(exc))

    return WorkspaceProvidersResponse(providers=providers)
