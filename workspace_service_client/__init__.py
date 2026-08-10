"""Python client package for the OpenEO Workspace Service API."""

from workspace_service_client.client import (
    WorkspaceServiceClient,
    WorkspaceServiceClientError,
)

__all__ = ["WorkspaceServiceClient", "WorkspaceServiceClientError"]
