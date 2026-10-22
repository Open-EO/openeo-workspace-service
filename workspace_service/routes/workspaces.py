"""
Workspaces CRUD routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from starlette.concurrency import run_in_threadpool
from pydantic import ValidationError
from typing import Optional
from workspace_service.models import (
    WorkspacesListResponse,
    Workspace,
    CreateWorkspaceRequest,
    RegisterWorkspaceRequest,
    UpdateWorkspaceRequest
)
from workspace_service.auth import TokenData, verify_token
from workspace_service import db
from workspace_service.config import settings
from workspace_service.provider_clients.registry import PROVIDER_CLIENTS
from workspace_service.routes import providers
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/workspaces")
async def list_workspaces(
    limit: int = Query(default=100, ge=1, le=1000),
    token: TokenData = Depends(verify_token)
) -> WorkspacesListResponse:
    """
    Lists all workspaces that have been added by a user.

    It is strongly RECOMMENDED to keep the response size small by omitting all optional
    non-scalar values (i.e. arrays and objects) from objects in workspaces.
    To get the full metadata for a workspace clients MUST request GET /workspaces/{workspace_id}.
    """
    user_id = token.sub

    try:
        client = db.get_client()
        workspaces, total = await client.list_workspaces(user_id, limit=limit)

        # Convert to response models
        workspace_models = [
            Workspace(
                id=ws["id"],
                type=ws["type"],
                status=ws["status"],
                title=ws.get("title"),
                description=ws.get("description"),
                details=ws.get("details"),
                quota=ws.get("quota"),
                url=ws.get("url"),
            )
            for ws in workspaces
        ]

        return WorkspacesListResponse(
            workspaces=workspace_models,
            links={"rel": [], "href": []}
        )
    except Exception as e:
        logger.error(f"Failed to list workspaces: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list workspaces"
        )

@router.post("/workspaces", status_code=status.HTTP_201_CREATED)
async def create_workspace(
    request: CreateWorkspaceRequest | RegisterWorkspaceRequest,
    response: Response,
    token: TokenData = Depends(verify_token),
):
    """
    Creates a new workspace.

    Create provisions storage through the selected provider client and returns
    ready bucket metadata. Register only records an existing workspace.
    """
    user_id = token.sub
    workspace_id = str(uuid.uuid4())
    provider_type = (request.type or settings.default_workspace_provider).lower()
    provider_client = None
    parameters = None
    if request.intent == "create":
        advertised = providers.WORKSPACE_PROVIDERS.get(provider_type)
        if advertised is None or "create" not in advertised.intents:
            raise HTTPException(status_code=400, detail=f"Unsupported create provider: {provider_type}")
        try:
            provider_client = PROVIDER_CLIENTS.get(provider_type)
        except (ImportError, TypeError):
            logger.exception("Unable to initialize provider client %s", provider_type)
            raise HTTPException(status_code=500, detail="Unable to initialize provider client")
        if provider_client is None:
            raise HTTPException(status_code=400, detail=f"Unsupported create provider: {provider_type}")
        try:
            parameters = provider_client.workspace_parameters.model_validate(request.parameters or {})
            if parameters.bucket_name is None:
                parameters.bucket_name = f"openeo-workspace-{workspace_id}"
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail=[{
                    "loc": ["body", "parameters", *error["loc"]],
                    "msg": error["msg"],
                    "type": error["type"],
                } for error in exc.errors(include_input=False, include_context=False)],
            ) from exc

    try:
        client = db.get_client()

        # Prepare data
        data = {
            "title": getattr(request, "title", None),
            "description": getattr(request, "description", None),
            "type": provider_type,
            "parameters": (
                parameters.model_dump(exclude={"aws_access_key_id", "aws_secret_access_key"})
                if parameters is not None else request.parameters
            ),
            "quota": getattr(request, "quota", None),
        }

        # For register intent, add URL
        if hasattr(request, "url"):
            data["url"] = request.url

        # Create workspace in database
        workspace = await client.create_workspace(workspace_id, user_id, data)

        if provider_client is not None and parameters is not None:
            try:
                metadata = await run_in_threadpool(
                    provider_client.provision_workspace, workspace_id, parameters,
                )
            except Exception:
                logger.error("Provider provisioning failed for workspace %s", workspace_id)
                await client.update_workspace(workspace_id, user_id, {
                    "status": "unavailable",
                    "details": "Bucket provisioning failed; storage may have been partially created.",
                })
                raise HTTPException(
                    status_code=502,
                    detail=f"Bucket provisioning failed for workspace {workspace_id}",
                )
            updated = await client.update_workspace(workspace_id, user_id, {
                **metadata,
                "status": "ready",
                "details": "Workspace bucket provisioned",
            })
            if updated is None:
                raise RuntimeError(f"Provisioned workspace {workspace_id} could not be saved")
            response.headers["Location"] = f"{settings.api_prefix}/{settings.api_version}/workspaces/{workspace_id}"
            return Workspace(**updated)

        # Return response with Location header
        return {
            "id": workspace_id,
            "status": "provisioning",
            "message": "Workspace creation has been queued successfully"
        }

    except HTTPException:
        raise
    except Exception:
        logger.error("Failed to create workspace %s", workspace_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workspace"
        )

@router.get("/workspaces/{workspace_id}")
async def describe_workspace(
    workspace_id: str,
    token: TokenData = Depends(verify_token)
) -> Workspace:
    """
    Returns the full metadata for a workspace.
    """
    user_id = token.sub

    try:
        client = db.get_client()
        workspace = await client.get_workspace(workspace_id, user_id)

        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace '{workspace_id}' not found"
            )

        return Workspace(
            id=workspace["id"],
            type=workspace["type"],
            status=workspace["status"],
            title=workspace.get("title"),
            description=workspace.get("description"),
            details=workspace.get("details"),
            quota=workspace.get("quota"),
            url=workspace.get("url"),
            properties=workspace.get("properties", {}),
            free=workspace.get("free")
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get workspace"
        )

@router.patch("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_workspace(
    workspace_id: str,
    request: UpdateWorkspaceRequest,
    token: TokenData = Depends(verify_token)
):
    """
    Updates the workspace details.
    """
    user_id = token.sub

    try:
        client = db.get_client()

        # Prepare update data
        data = {}
        if request.title is not None:
            data["title"] = request.title
        if request.description is not None:
            data["description"] = request.description

        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update"
            )

        updated = await client.update_workspace(workspace_id, user_id, data)

        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace '{workspace_id}' not found"
            )

        return None  # 204 No Content

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update workspace"
        )

@router.delete("/workspaces/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workspace(
    workspace_id: str,
    token: TokenData = Depends(verify_token)
):
    """
    Removes the workspace from the back-end.
    """
    user_id = token.sub

    try:
        client = db.get_client()
        success = await client.delete_workspace(workspace_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace '{workspace_id}' not found"
            )

        return None  # 204 No Content

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete workspace {workspace_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete workspace"
        )
