"""
openeo_workspace_service/providers/gcs.py
------------------------------------------
Google Cloud Storage workspace provider.

Required parameters:
  - project_id
  - bucket_name
  - service_account_json   (JSON string of the service-account credentials)
"""
from __future__ import annotations

import json
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

_REQUIRED_PARAMS = {"project_id", "bucket_name", "service_account_json"}


@register_provider("GCS")
class GCSWorkspaceProvider(BaseWorkspaceProvider):
    @property
    def metadata(self) -> WorkspaceProvider:
        return WorkspaceProvider(
            title="Google Cloud Storage",
            description="Google Cloud Storage is a RESTful online file storage web service.",
            intents=["create", "register"],
            parameters={
                "project_id": ProviderParameterSchema(
                    type="string", description="GCP project ID."
                ),
                "bucket_name": ProviderParameterSchema(
                    type="string", description="GCS bucket name."
                ),
                "service_account_json": ProviderParameterSchema(
                    type="string",
                    description=(
                        "JSON string of the GCP service account credentials. "
                        "Generate via the GCP Console → IAM → Service Accounts."
                    ),
                ),
                "location": ProviderParameterSchema(
                    type="string",
                    description="GCS bucket location (e.g. EU, US, ASIA). Defaults to US.",
                ),
            },
            links=[
                {
                    "rel": "about",
                    "href": "https://cloud.google.com/storage",
                    "title": "Google Cloud Storage product page",
                }
            ],
        )

    def validate_parameters(self, parameters: dict[str, Any]) -> None:
        missing = _REQUIRED_PARAMS - parameters.keys()
        if missing:
            raise ValueError(f"Missing required GCS parameters: {', '.join(sorted(missing))}")
        try:
            json.loads(parameters["service_account_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError("service_account_json is not valid JSON.") from exc

    async def provision(self, record: "WorkspaceRecord") -> None:
        try:
            from google.cloud import storage as gcs  # type: ignore[import]
            from google.oauth2 import service_account  # type: ignore[import]
        except ImportError as exc:
            record.status = "unavailable"
            record.details = "google-cloud-storage not installed."
            logger.error("google-cloud-storage not available: %s", exc)
            return

        params = record.parameters
        try:
            creds_info = json.loads(params["service_account_json"])
            credentials = service_account.Credentials.from_service_account_info(creds_info)
            client = gcs.Client(project=params["project_id"], credentials=credentials)
            bucket_name = params["bucket_name"]
            bucket = client.bucket(bucket_name)
            if not bucket.exists():
                bucket = client.create_bucket(
                    bucket_name, location=params.get("location", "US")
                )
            record.url = f"https://storage.googleapis.com/{bucket_name}"
            record.properties = {
                "project": params["project_id"],
                "location": params.get("location", "US"),
            }
            record.status = "ready"
            record.details = None
        except Exception as exc:
            record.status = "unavailable"
            record.details = str(exc)
            logger.exception("GCS provisioning failed for workspace %s", record.id)

    async def delete(self, record: "WorkspaceRecord") -> None:
        logger.info(
            "Workspace %s de-registered; GCS bucket NOT deleted.", record.id
        )

    async def refresh_status(self, record: "WorkspaceRecord") -> None:
        try:
            from google.cloud import storage as gcs  # type: ignore[import]
            from google.oauth2 import service_account  # type: ignore[import]
        except ImportError:
            return

        params = record.parameters
        try:
            creds_info = json.loads(params["service_account_json"])
            credentials = service_account.Credentials.from_service_account_info(creds_info)
            client = gcs.Client(project=params["project_id"], credentials=credentials)
            bucket = client.get_bucket(params["bucket_name"])
            if record.quota:
                used = sum(b.size or 0 for b in client.list_blobs(bucket))
                record.free = max(0, record.quota - used)
            record.status = "ready"
            record.details = None
        except Exception as exc:
            record.status = "unavailable"
            record.details = str(exc)
