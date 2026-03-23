"""
openeo_workspace_service/models/schemas.py
-------------------------------------------
Pydantic v2 request / response schemas that mirror the OpenAPI 3.0 spec defined in
https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/openapi.yaml
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


# ── Shared primitives ────────────────────────────────────────────────────────

WorkspaceId = str  # pattern: '^[\w\-\.~]+$'


class WorkspaceStatus(str, Enum):
    provisioning = "provisioning"
    unavailable = "unavailable"
    ready = "ready"


# ── Workspace provider schemas ───────────────────────────────────────────────

class ProviderParameterSchema(BaseModel):
    """Loose representation of a single provider parameter definition."""

    model_config = ConfigDict(extra="allow")

    type: str | None = None
    description: str | None = None
    required: bool = False


class WorkspaceProvider(BaseModel):
    title: str | None = None
    description: str | None = None
    deprecated: bool = False
    experimental: bool = False
    intents: list[Literal["create", "register"]] = Field(min_length=1)
    parameters: dict[str, ProviderParameterSchema] = Field(default_factory=dict)
    links: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceProvidersResponse(BaseModel):
    providers: dict[str, WorkspaceProvider]


# ── Workspace schemas ────────────────────────────────────────────────────────

class WorkspaceBase(BaseModel):
    title: str | None = None
    description: str | None = None


class CreateWorkspaceBody(WorkspaceBase):
    intent: Literal["create"]
    type: str | None = None
    quota: int | None = Field(None, gt=0, description="Maximum storage in bytes")
    parameters: dict[str, Any] = Field(default_factory=dict)


class RegisterWorkspaceBody(WorkspaceBase):
    intent: Literal["register"]
    type: str
    url: AnyUrl
    quota: int | None = Field(None, gt=0)
    parameters: dict[str, Any]


class UpdateWorkspaceBody(BaseModel):
    title: str | None = None
    description: str | None = None


class WorkspaceResponse(WorkspaceBase):
    """Response body for GET /workspaces/{workspace_id}."""

    id: WorkspaceId
    type: str
    status: WorkspaceStatus
    details: str | None = None
    quota: int | None = None
    # Only present when status == ready
    url: str | None = None
    properties: dict[str, Any] | None = None
    free: int | None = None


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]
    links: list[dict[str, Any]] = Field(default_factory=list)
