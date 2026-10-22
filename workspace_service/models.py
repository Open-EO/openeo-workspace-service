"""
Pydantic models for request/response bodies
"""
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field

class ProviderParameters(BaseModel):
    """Provider-specific parameter definition"""
    type: Optional[str] = None
    description: Optional[str] = None
    required: Optional[bool] = False

class WorkspaceProvider(BaseModel):
    """Workspace provider definition"""
    title: Optional[str] = None
    description: Optional[str] = None
    deprecated: Optional[bool] = False
    experimental: Optional[bool] = False
    intents: List[str] = Field(default=["create", "register"])
    parameters: Dict[str, Any] = {}
    links: Optional[List[Dict[str, Any]]] = []

class WorkspaceProvidersResponse(BaseModel):
    """Response for listing workspace providers"""
    providers: Dict[str, WorkspaceProvider]

class CreateWorkspaceRequest(BaseModel):
    """Request to create a new workspace"""
    intent: Literal["create"] = "create"
    title: Optional[str] = None
    description: Optional[str] = None
    type: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = {}
    quota: Optional[int] = None

class RegisterWorkspaceRequest(BaseModel):
    """Request to register an existing workspace"""
    intent: Literal["register"] = "register"
    title: Optional[str] = None
    description: Optional[str] = None
    type: str
    url: str
    parameters: Dict[str, Any]
    quota: Optional[int] = None

class UpdateWorkspaceRequest(BaseModel):
    """Request to update workspace metadata"""
    title: Optional[str] = None
    description: Optional[str] = None

class WorkspaceProvisioning(BaseModel):
    """Workspace in provisioning state"""
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    type: str
    status: str = Field(default="provisioning", pattern="^(provisioning|unavailable)$")
    details: Optional[str] = None
    quota: Optional[int] = None

class WorkspaceReady(BaseModel):
    """Workspace in ready state"""
    id: str
    title: Optional[str] = None
    description: Optional[str] = None
    type: str
    status: str = Field(default="ready")
    details: Optional[str] = None
    quota: Optional[int] = None
    url: str
    properties: Optional[Dict[str, Any]] = {}
    free: Optional[int] = None

class Workspace(BaseModel):
    """Workspace metadata"""
    id: str
    type: str
    status: str = Field(pattern="^(provisioning|unavailable|ready)$")
    title: Optional[str] = None
    description: Optional[str] = None
    details: Optional[str] = None
    quota: Optional[int] = None
    url: Optional[str] = None
    properties: Optional[Dict[str, Any]] = {}
    free: Optional[int] = None

class WorkspacesListResponse(BaseModel):
    """Response for listing workspaces"""
    workspaces: List[Workspace]
    links: Dict[str, Any] = Field(default={"rel": [], "href": []})

class PaginationLink(BaseModel):
    """Pagination link"""
    rel: str
    href: str
    type: Optional[str] = None
