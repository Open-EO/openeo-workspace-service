"""
Pydantic v2 models that mirror the openEO Workspaces Extension OpenAPI schemas.

Reference: https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/openapi.yaml
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class WorkspaceStatus(StrEnum):
    provisioning = "provisioning"
    unavailable = "unavailable"
    ready = "ready"


class WorkspaceIntent(StrEnum):
    create = "create"
    register = "register"


# ---------------------------------------------------------------------------
# Workspace ID type
# ---------------------------------------------------------------------------

WorkspaceId = Annotated[
    str,
    Field(pattern=r"^[\w\-\.~]+$", examples=["my-workspace"]),
]


# ---------------------------------------------------------------------------
# Provider parameter (inline representation of resource_parameter)
# ---------------------------------------------------------------------------


class ProviderParameter(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str | None = None
    type: str | None = None
    default: Any = None
    required: bool = False


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class Provider(BaseModel):
    model_config = ConfigDict(extra="allow")

    title: str | None = None
    description: str | None = None
    deprecated: bool = False
    experimental: bool = False
    intents: list[WorkspaceIntent] = Field(
        default_factory=lambda: [WorkspaceIntent.create],
        min_length=1,
    )
    parameters: dict[str, ProviderParameter] = Field(default_factory=dict)
    links: list[dict[str, Any]] = Field(default_factory=list)


class WorkspaceProvidersResponse(BaseModel):
    providers: dict[str, Provider]


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


class WorkspaceBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: WorkspaceId
    title: str | None = None
    description: str | None = None
    type: str  # provider name
    status: WorkspaceStatus
    details: str | None = None
    quota: int | None = Field(default=None, description="Max storage quota in bytes")


class WorkspaceReady(WorkspaceBase):
    status: WorkspaceStatus = WorkspaceStatus.ready
    url: str | None = None  # HttpUrl serialised as string to stay JSON-serialisable
    properties: dict[str, Any] | None = None
    free: int | None = Field(default=None, description="Free storage quota in bytes")


class WorkspaceUnavailable(WorkspaceBase):
    status: WorkspaceStatus


# Union – FastAPI will use the right one based on status
Workspace = WorkspaceReady | WorkspaceUnavailable


# ---------------------------------------------------------------------------
# List response
# ---------------------------------------------------------------------------


class Link(BaseModel):
    href: str
    rel: str | None = None
    type: str | None = None
    title: str | None = None


class WorkspacesListResponse(BaseModel):
    workspaces: list[WorkspaceReady | WorkspaceUnavailable]
    links: list[Link] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Create / Register request bodies
# ---------------------------------------------------------------------------


class CreateWorkspaceRequest(BaseModel):
    """Request body for POST /workspaces with intent=create."""

    intent: WorkspaceIntent = WorkspaceIntent.create
    title: str | None = None
    description: str | None = None
    quota: int | None = None
    type: str | None = Field(
        default=None,
        description="Workspace provider name. If null, the back-end picks the default.",
    )
    parameters: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _validate_intent(self) -> CreateWorkspaceRequest:
        if self.intent != WorkspaceIntent.create:
            raise ValueError("intent must be 'create' for CreateWorkspaceRequest")
        return self


class RegisterWorkspaceRequest(BaseModel):
    """Request body for POST /workspaces with intent=register."""

    intent: WorkspaceIntent = WorkspaceIntent.register
    title: str | None = None
    description: str | None = None
    quota: int | None = None
    type: str = Field(..., description="The workspace provider name.")
    url: str = Field(..., description="The URL of the existing external workspace.")
    parameters: dict[str, Any]

    @model_validator(mode="after")
    def _validate_intent(self) -> RegisterWorkspaceRequest:
        if self.intent != WorkspaceIntent.register:
            raise ValueError("intent must be 'register' for RegisterWorkspaceRequest")
        return self


# ---------------------------------------------------------------------------
# Update request body
# ---------------------------------------------------------------------------


class UpdateWorkspaceRequest(BaseModel):
    title: str | None = None
    description: str | None = None
