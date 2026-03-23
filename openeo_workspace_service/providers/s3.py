"""
openeo_workspace_service/providers/s3.py
-----------------------------------------
Amazon S3 / S3-compatible workspace provider.

Required parameters (supplied by the user when creating a workspace):
  - aws_access_key_id
  - aws_secret_access_key
  - bucket_name

Optional parameters:
  - endpoint_url   – for S3-compatible stores (MinIO, etc.)
  - region_name    – defaults to us-east-1
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

_REQUIRED_PARAMS = {"aws_access_key_id", "aws_secret_access_key", "bucket_name"}


@register_provider("S3")
class S3WorkspaceProvider(BaseWorkspaceProvider):
    @property
    def metadata(self) -> WorkspaceProvider:
        return WorkspaceProvider(
            title="Amazon S3",
            description=(
                "Amazon S3 is a cloud storage service provided by Amazon Web Services. "
                "Storage containers are called *buckets*. "
                "S3-compatible stores (MinIO, Ceph, etc.) are also supported via ``endpoint_url``."
            ),
            intents=["create", "register"],
            parameters={
                "aws_access_key_id": ProviderParameterSchema(
                    type="string", description="AWS access key ID."
                ),
                "aws_secret_access_key": ProviderParameterSchema(
                    type="string",
                    description="AWS secret access key corresponding to the access key ID.",
                ),
                "bucket_name": ProviderParameterSchema(
                    type="string", description="Name of the S3 bucket."
                ),
                "region_name": ProviderParameterSchema(
                    type="string",
                    description="AWS region (e.g. eu-west-1). Defaults to us-east-1.",
                ),
                "endpoint_url": ProviderParameterSchema(
                    type="string",
                    description=(
                        "Custom S3-compatible endpoint URL "
                        "(e.g. https://minio.example.com). "
                        "Leave empty for native AWS S3."
                    ),
                ),
            },
            links=[
                {
                    "rel": "about",
                    "href": "https://aws.amazon.com/s3/",
                    "title": "Amazon S3 product page",
                }
            ],
        )

    def validate_parameters(self, parameters: dict[str, Any]) -> None:
        missing = _REQUIRED_PARAMS - parameters.keys()
        if missing:
            raise ValueError(f"Missing required S3 parameters: {', '.join(sorted(missing))}")

    async def provision(self, record: "WorkspaceRecord") -> None:
        try:
            import boto3  # type: ignore[import]
            from botocore.exceptions import ClientError  # type: ignore[import]
        except ImportError as exc:
            record.status = "unavailable"
            record.details = "boto3 is not installed; cannot provision S3 workspace."
            logger.error("boto3 not available: %s", exc)
            return

        params = record.parameters
        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=params["aws_access_key_id"],
                aws_secret_access_key=params["aws_secret_access_key"],
                region_name=params.get("region_name", "us-east-1"),
                endpoint_url=params.get("endpoint_url") or None,
            )
            bucket = params["bucket_name"]

            # Try to create the bucket; ignore AlreadyOwnedByYou / BucketAlreadyExists.
            try:
                region = params.get("region_name", "us-east-1")
                if region == "us-east-1":
                    s3.create_bucket(Bucket=bucket)
                else:
                    s3.create_bucket(
                        Bucket=bucket,
                        CreateBucketConfiguration={"LocationConstraint": region},
                    )
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                    raise

            # Determine bucket URL and region.
            location = s3.get_bucket_location(Bucket=bucket)
            resolved_region = location["LocationConstraint"] or "us-east-1"
            endpoint = params.get("endpoint_url") or f"https://s3.{resolved_region}.amazonaws.com"
            record.url = f"{endpoint.rstrip('/')}/{bucket}"
            record.properties = {"region": resolved_region, "bucket": bucket}
            record.status = "ready"
            record.details = None
        except Exception as exc:
            record.status = "unavailable"
            record.details = str(exc)
            logger.exception("S3 provisioning failed for workspace %s", record.id)

    async def delete(self, record: "WorkspaceRecord") -> None:
        """
        Removes the workspace *registration* from the service.
        The S3 bucket itself is intentionally NOT deleted to prevent
        accidental data loss – operators should remove it out-of-band.
        """
        logger.info(
            "Workspace %s de-registered; S3 bucket %s NOT deleted.",
            record.id,
            record.parameters.get("bucket_name"),
        )

    async def refresh_status(self, record: "WorkspaceRecord") -> None:
        """Check if the bucket is still accessible and update free space."""
        try:
            import boto3  # type: ignore[import]
        except ImportError:
            return

        params = record.parameters
        try:
            s3 = boto3.client(
                "s3",
                aws_access_key_id=params["aws_access_key_id"],
                aws_secret_access_key=params["aws_secret_access_key"],
                region_name=params.get("region_name", "us-east-1"),
                endpoint_url=params.get("endpoint_url") or None,
            )
            bucket = params["bucket_name"]
            s3.head_bucket(Bucket=bucket)

            # Approximate used storage via CloudWatch would require extra
            # permissions; we leave free=None unless a quota is set.
            if record.quota:
                paginator = s3.get_paginator("list_objects_v2")
                used = sum(
                    obj["Size"]
                    for page in paginator.paginate(Bucket=bucket)
                    for obj in page.get("Contents", [])
                )
                record.free = max(0, record.quota - used)

            record.status = "ready"
            record.details = None
        except Exception as exc:
            record.status = "unavailable"
            record.details = str(exc)
