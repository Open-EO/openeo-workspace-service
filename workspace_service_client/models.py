"""Pydantic models used by the Workspace Service client."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkspaceProvider(BaseModel):
    """Workspace provider definition."""

    title: Optional[str] = None
    description: Optional[str] = None
    deprecated: Optional[bool] = False
    experimental: Optional[bool] = False
    intents: List[str] = Field(default=["create", "register"])
    parameters: Dict[str, Any] = {}
    links: Optional[List[Dict[str, Any]]] = []


class WorkspaceProvidersResponse(BaseModel):
    """Response model for listing workspace providers."""

    providers: Dict[str, WorkspaceProvider]


class Workspace(BaseModel):
    """Workspace metadata."""

    id: str
    type: str
    status: str
    title: Optional[str] = None
    description: Optional[str] = None
    details: Optional[str] = None
    quota: Optional[int] = None
    url: Optional[str] = None
    properties: Optional[Dict[str, Any]] = {}
    free: Optional[int] = None


class WorkspacesListResponse(BaseModel):
    """Response model for listing workspaces."""

    workspaces: List[Workspace]
    links: Dict[str, Any] = Field(default={"rel": [], "href": []})
