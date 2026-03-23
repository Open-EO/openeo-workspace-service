"""
openeo_workspace_service/providers/azure.py
--------------------------------------------
Azure Blob Storage workspace provider.

Required parameters:
  - account_name
  - account_key
  - container_name
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from openeo_workspace_service.models.schemas import (
    ProviderParameterSchema,
    WorkspaceProvider,
)
from openeo_workspace_service.providers.base import BaseWorkspaceProvider, register_provider

if TYPE_CHECKING:
    from openeo_workspace_service.db.models import WorkspaceRecord

logger = logging.getLogger(__name__)

_REQUIRED_PARAMS = {"account_name", "account_key", "container_name"}


@register_provider("AZURE")
class AzureWorkspaceProvider(BaseWorkspaceProvider):
    @property
    def metadata(self) -> WorkspaceProvider:
        return WorkspaceProvider(
            title="Azure Blob Storage",
            description=(
                "Microsoft Azure Blob Storage is a massively scalable object storage "
                "solution for the cloud."
            ),
            intents=["create", "register"],
            parameters={
                "account_name": ProviderParameterSchema(
                    type="string", description="Azure Storage account name."
                ),
                "account_key": ProviderParameterSchema(
                    type="string", description="Azure Storage account key."
                ),
                "container_name": ProviderParameterSchema(
                    type="string", description="Name of the blob container."
                ),
            },
            links=[
                {
                    "rel": "about",
                    "href": "https://azure.microsoft.com/products/storage/blobs/",
                    "title": "Azure Blob Storage product page",
                }
            ],
        )

    def validate_parameters(self, parameters: dict[str, Any]) -> None:
        missing = _REQUIRED_PARAMS - parameters.keys()
        if missing:
            raise ValueError(f"Missing required Azure parameters: {', '.join(sorted(missing))}")

    async def provision(self, record: "WorkspaceRecord") -> None:
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore[import]
        except ImportError as exc:
            record.status = "unavailable"
            record.details = "azure-storage-blob not installed."
            logger.error("azure-storage-blob not available: %s", exc)
            return

        params = record.parameters
        try:
            conn_str = (
                f"DefaultEndpointsProtocol=https;"
                f"AccountName={params['account_name']};"
                f"AccountKey={params['account_key']};"
                f"EndpointSuffix=core.windows.net"
            )
            client = BlobServiceClient.from_connection_string(conn_str)
            container = params["container_name"]
            try:
                client.create_container(container)
            except Exception as exc:
                if "ContainerAlreadyExists" not in str(exc):
                    raise
            record.url = (
                f"https://{params['account_name']}.blob.core.windows.net/{container}"
            )
            record.properties = {"container": container}
            record.status = "ready"
            record.details = None
        except Exception as exc:
            record.status = "unavailable"
            record.details = str(exc)
            logger.exception("Azure provisioning failed for workspace %s", record.id)

    async def delete(self, record: "WorkspaceRecord") -> None:
        logger.info(
            "Workspace %s de-registered; Azure container NOT deleted.",
            record.id,
        )

    async def refresh_status(self, record: "WorkspaceRecord") -> None:
        try:
            from azure.storage.blob import BlobServiceClient  # type: ignore[import]
        except ImportError:
            return

        params = record.parameters
        try:
            conn_str = (
                f"DefaultEndpointsProtocol=https;"
                f"AccountName={params['account_name']};"
                f"AccountKey={params['account_key']};"
                f"EndpointSuffix=core.windows.net"
            )
            client = BlobServiceClient.from_connection_string(conn_str)
            client.get_container_client(params["container_name"]).get_container_properties()
            record.status = "ready"
            record.details = None
        except Exception as exc:
            record.status = "unavailable"
            record.details = str(exc)
