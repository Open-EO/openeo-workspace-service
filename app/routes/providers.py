"""
Workspace provider routes
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
from app.models import WorkspaceProvidersResponse, WorkspaceProvider
from app.auth import TokenData, verify_token_optional

logger = logging.getLogger(__name__)
router = APIRouter()

# Define supported providers
WORKSPACE_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "s3": {
        "title": "Amazon S3",
        "description": "Amazon S3 is a cloud storage service provided by Amazon Web Services. It provides storage containers which are called buckets.",
        "intents": ["create", "register"],
        "parameters": {
            "aws_access_key_id": {
                "type": "string",
                "description": "AWS access key"
            },
            "aws_secret_access_key": {
                "type": "string",
                "description": "AWS secret key associated with the access key."
            },
            "bucket_name": {
                "type": "string",
                "description": "Bucket name"
            }
        },
        "links": []
    },
    "gcs": {
        "title": "Google Cloud Storage",
        "description": "Google Cloud Storage is a cloud storage service provided by Google Cloud. It provides storage containers which are called buckets.",
        "intents": ["create", "register"],
        "parameters": {
            "project_id": {
                "type": "string",
                "description": "Google Cloud project ID"
            },
            "service_account_key": {
                "type": "string",
                "description": "Service account key (JSON format)"
            },
            "bucket_name": {
                "type": "string",
                "description": "Bucket name"
            }
        },
        "links": []
    },
    "azure": {
        "title": "Azure Blob Storage",
        "description": "Azure Blob Storage is a cloud storage service provided by Microsoft Azure. It provides storage containers.",
        "intents": ["create", "register"],
        "parameters": {
            "connection_string": {
                "type": "string",
                "description": "Azure storage connection string"
            },
            "container_name": {
                "type": "string",
                "description": "Container name"
            }
        },
        "links": []
    }
}

@router.get("/workspace_providers")
async def list_workspace_providers(
    token: TokenData = Depends(verify_token_optional)
) -> WorkspaceProvidersResponse:
    """
    Lists supported workspace providers such as Amazon S3, Google Cloud Storage or Azure Blob Storage.
    The response is an object of all available workspace providers with their supported parameters.

    Workspace provider names MUST be accepted in a *case insensitive* manner throughout the API.
    """
    providers = {}

    for provider_name, provider_config in WORKSPACE_PROVIDERS.items():
        providers[provider_name] = WorkspaceProvider(**provider_config)

    return WorkspaceProvidersResponse(providers=providers)

