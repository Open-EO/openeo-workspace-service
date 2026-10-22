"""
Workspace provider routes
"""
import logging
from pathlib import Path
from fastapi import APIRouter, Depends
from pydantic import TypeAdapter
from workspace_service.models import WorkspaceProvidersResponse, WorkspaceProvider
from workspace_service.auth import TokenData, verify_token_optional
from workspace_service.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

def load_workspace_providers(path: Path) -> dict[str, WorkspaceProvider]:
    """Load provider definitions, failing startup on missing or invalid configuration."""
    return TypeAdapter(dict[str, WorkspaceProvider]).validate_json(path.read_bytes())


WORKSPACE_PROVIDERS = load_workspace_providers(settings.workspace_providers_file)

@router.get("/workspace_providers")
async def list_workspace_providers(
    token: TokenData = Depends(verify_token_optional)
) -> WorkspaceProvidersResponse:
    """
    Lists supported workspace providers such as Amazon S3, Google Cloud Storage or Azure Blob Storage.
    The response is an object of all available workspace providers with their supported parameters.

    Workspace provider names MUST be accepted in a *case insensitive* manner throughout the API.
    """
    return WorkspaceProvidersResponse(providers=WORKSPACE_PROVIDERS)
