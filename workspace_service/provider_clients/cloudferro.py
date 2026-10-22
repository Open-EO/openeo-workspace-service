"""Provision CloudFerro S3 buckets without Terraform, Vault or shell commands."""

import base64
import argparse
import hashlib
import ipaddress
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping, NotRequired, Sequence, TypedDict
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


Versioning = Literal["Unset", "Enabled", "Suspended"]
PublicAccess = Literal["none", "R", "DANGER_LR"]


class CloudFerroWorkspaceParameters(BaseModel):
    """User-supplied provisioning parameters; secrets must not be persisted."""

    model_config = ConfigDict(extra="forbid")
    aws_access_key_id: SecretStr = Field(min_length=1)
    aws_secret_access_key: SecretStr = Field(min_length=1)
    bucket_name: str | None = None
    region: str = Field(default="waw3-1", min_length=1)
    endpoint_url: Literal["https://s3.waw3-1.cloudferro.com"] = "https://s3.waw3-1.cloudferro.com"

    @field_validator("bucket_name")
    @classmethod
    def validate_bucket_name(cls, name: str | None) -> str | None:
        if name is not None:
            CloudFerroBucketProvisioner._validate_bucket_name(name)
        return name


class BucketPolicy(TypedDict):
    principal: str
    bucket_access: str
    policy_vars: NotRequired[Mapping[str, str]]


class CloudFerroBucketProvisioner:
    """Manage buckets with existing owner credentials via the S3 API.

    Configuration failures propagate without deleting the partially configured
    bucket. Credentials and bucket policies are never logged.
    """

    _LEGACY_NAMES = {
        "lcfm_waw3-1_4b82fdbbe2580bdfc4f595824922507c0d7cae2541c0799982",
        "WaterAndWetness", "SmallWoodyFeatures", "OpenEO-artifacts",
        "OpenEO-data", "OpenEO-data-vlcc", "tf_vlcc_applications",
        "tf_vlcc_rancher", "tf_vlcc_system_services",
        "tf_vlcc_system_services_crds", "project_dependencies",
    }
    _WRITE_ACTIONS = [
        "s3:AbortMultipartUpload", "s3:DeleteObject", "s3:GetObject",
        "s3:ListMultipartUploadParts", "s3:PutObject",
    ]
    _CORS_ORIGINS = {
        "get_from_anywhere_anyheader": ["*"],
        "get_from_apex": [
            "https://apex-ge-config-builder.sparkgeo.uk", "https://*.apex.esa.int",
        ],
        "get_from_sonata": [
            "https://apex-ge-config-builder.sparkgeo.uk",
            "https://catalogue.sonata-nbs.com", "https://*.sonata-nbs.com",
        ],
        "get_from_webeditor": ["https://*.dataspace.copernicus.eu/"],
        "get_head_from_anywhere_content_headers": ["*"],
    }
    _EXPIRATION_RULE = "CAUTION_DANGER_expire_objects_param_prefix_days"
    workspace_parameters = CloudFerroWorkspaceParameters

    @classmethod
    def provision_workspace(
        cls, workspace_id: str, parameters: CloudFerroWorkspaceParameters,
    ) -> dict[str, Any]:
        """Provision a private workspace and return only non-secret metadata."""
        bucket_name = parameters.bucket_name or f"openeo-workspace-{workspace_id}"
        with cls(
            access_key=parameters.aws_access_key_id.get_secret_value(),
            secret_key=parameters.aws_secret_access_key.get_secret_value(),
            endpoint_url=parameters.endpoint_url,
            region=parameters.region,
        ) as client:
            client.create_bucket(bucket_name)
        return {
            "url": f"{parameters.endpoint_url}/{bucket_name}",
            "properties": {
                "bucket_name": bucket_name,
                "region": parameters.region,
                "endpoint_url": parameters.endpoint_url,
                "s3_url": f"s3://{bucket_name}",
            },
        }

    def __init__(
        self,
        *,
        access_key: str,
        secret_key: str,
        endpoint_url: str = "https://s3.waw3-1.cloudferro.com",
        region: str = "waw3-1",
    ):
        if not access_key or not secret_key:
            raise ValueError("S3 access_key and secret_key are required")
        self.region = region
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                connect_timeout=10,
                read_timeout=30,
                retries={"mode": "standard", "max_attempts": 3},
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
            ),
        )

    def close(self) -> None:
        self.s3.close()

    def __enter__(self) -> "CloudFerroBucketProvisioner":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    @classmethod
    def _validate_bucket_name(cls, bucket_name: str) -> None:
        valid = (
            re.fullmatch(r"[a-z0-9][a-z0-9-]{1,61}[a-z0-9]", bucket_name)
            and not bucket_name.startswith("xn--")
            and not bucket_name.endswith("-s3alias")
        )
        if not valid and bucket_name not in cls._LEGACY_NAMES:
            raise ValueError(f"Invalid bucket name: {bucket_name!r}")

    @staticmethod
    def _validate_versioning(versioning: str) -> None:
        if versioning not in {"Unset", "Enabled", "Suspended"}:
            raise ValueError("versioning must be Unset, Enabled or Suspended")

    @classmethod
    def _statement(
        cls,
        bucket_name: str,
        access: str,
        principal: str,
        sid: str,
        key: str,
        versioning: Versioning,
    ) -> dict[str, Any]:
        versioned = versioning != "Unset"
        available = {"R", "LR", "LRW", "LRWSAFE"} if versioned else {
            "R", "RW", "LR", "LRW", "BucketInventory", "BucketInventoryOBS",
        }
        if access not in available:
            raise ValueError(f"No policy template for {access!r} with versioning {versioning!r}")
        if not principal:
            raise ValueError("A policy principal is required")
        bucket_arn = f"arn:aws:s3:::{bucket_name}"
        resources = [f"{bucket_arn}/{key}"]
        if access in {"RW", "LRW", "LRWSAFE"}:
            actions = list(cls._WRITE_ACTIONS)
        else:
            actions = ["s3:GetObject"]
        if versioned:
            actions.append("s3:GetObjectVersion")
            if access == "LRW":
                actions.append("s3:DeleteObjectVersion")
        if access.startswith("L"):
            resources.insert(0, bucket_arn)
            actions.append("s3:ListBucket")
            if versioned:
                actions.append("s3:ListBucketVersions")
        policy_principal = {"AWS": [principal]}
        if access == "BucketInventory":
            actions = [
                "s3:GetBucketInventoryConfiguration",
                "s3:PutBucketInventoryConfiguration",
                "s3:DeleteBucketInventoryConfiguration",
            ]
            resources = [bucket_arn]
        elif access == "BucketInventoryOBS":
            actions = ["s3:PutObject"]
            resources = [f"{bucket_arn}/*"]
            policy_principal = {"Service": ["obs"]}
        statement = {
            "Action": sorted(actions),
            "Effect": "Allow",
            "Resource": resources,
            "Principal": policy_principal,
        }
        if access != "RW":
            statement["Sid"] = sid
        return statement

    @classmethod
    def build_policy(
        cls,
        bucket_name: str,
        *,
        policies: Sequence[BucketPolicy] = (),
        versioning: Versioning = "Unset",
        public_access: PublicAccess = "none",
        ip_restrictions: Sequence[str] = (),
    ) -> dict[str, Any]:
        cls._validate_bucket_name(bucket_name)
        cls._validate_versioning(versioning)
        if public_access not in {"none", "R", "DANGER_LR"}:
            raise ValueError("public_access must be none, R or DANGER_LR")
        statements = []
        for index, policy in enumerate(policies):
            access = policy["bucket_access"]
            statements.append(cls._statement(
                bucket_name, access, policy["principal"], f"{access}_{index}",
                policy.get("policy_vars", {}).get("KEY", "*"), versioning,
            ))
        if public_access != "none":
            access = public_access.removeprefix("DANGER_")
            statements.append(cls._statement(
                bucket_name, access, "*", f"PUBLIC_{access}", "*", versioning,
            ))
        if ip_restrictions:
            for cidr in ip_restrictions:
                ipaddress.ip_network(cidr)
            statements.append({
                "Sid": "IPRestrictions",
                "Effect": "Deny",
                "Principal": "*",
                "Action": "s3:*",
                "Resource": [
                    f"arn:aws:s3:::{bucket_name}", f"arn:aws:s3:::{bucket_name}/*",
                ],
                "Condition": {"NotIpAddress": {"aws:SourceIp": list(ip_restrictions)}},
            })
        return {"Version": "2012-10-17", "Statement": statements}

    @classmethod
    def build_cors(cls, cors_policy: str) -> dict[str, Any] | None:
        if cors_policy == "none":
            return None
        if cors_policy not in cls._CORS_ORIGINS:
            raise ValueError(f"Unknown CORS policy: {cors_policy!r}")
        rule: dict[str, Any] = {
            "AllowedHeaders": ["*"],
            "AllowedMethods": ["GET"],
            "AllowedOrigins": list(cls._CORS_ORIGINS[cors_policy]),
        }
        if cors_policy == "get_head_from_anywhere_content_headers":
            rule.update(
                AllowedMethods=["GET", "HEAD"],
                ExposeHeaders=["Content-Range", "Content-Length", "Accept-Ranges", "ETag"],
                MaxAgeSeconds=3600,
            )
        return {"CORSRules": [rule]}

    @classmethod
    def build_lifecycle(
        cls, lifecycle_rules: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        requested = dict(lifecycle_rules or {})
        names = {name.split("@")[0] for name in requested}
        defaults: dict[str, Mapping[str, Any]] = {"abort_multipart_after_1_day": {}}
        if cls._EXPIRATION_RULE not in names:
            defaults["expired_deletion_markers"] = {}
        else:
            requested.pop("expired_deletion_markers", None)
        rules: dict[str, dict[str, Any]] = {}
        for name, params in sorted((defaults | requested).items()):
            template, _, suffix = name.partition("@")
            prefix = ""
            if template == "abort_multipart_after_1_day":
                rule_id = "CleanupMultipartUploads"
                action = {"AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}}
            elif template == "expired_deletion_markers":
                rule_id = "DeleteMarkers"
                action = {"Expiration": {"ExpiredObjectDeleteMarker": True}}
            elif template == cls._EXPIRATION_RULE:
                prefix = params.get("Prefix")
                days = params.get("Days")
                if not isinstance(prefix, str):
                    raise ValueError(f"{name}: Prefix must be a string")
                if type(days) is not int or days < 1:
                    raise ValueError(f"{name}: Days must be a positive integer")
                rule_id = "DangerExpireObject"
                action = {"Expiration": {"Days": days}}
            else:
                raise ValueError(f"Unknown lifecycle rule: {name!r}")
            rule = rules.setdefault(prefix, {
                "ID": "", "Filter": {"Prefix": prefix}, "Status": "Enabled",
            })
            rule["ID"] = (rule["ID"] + (rule_id + suffix)[:255])[:255]
            for field, value in action.items():
                if field in rule and rule[field] != value:
                    raise ValueError(f"Conflicting lifecycle actions for prefix {prefix!r}")
                rule[field] = value
        ids = [rule["ID"] for rule in rules.values()]
        if len(set(ids)) != len(ids):
            raise ValueError("Lifecycle rule IDs must remain unique after truncation to 255 characters")
        return {"Rules": [rules[prefix] for prefix in sorted(rules)]}

    def create_bucket(
        self,
        bucket_name: str,
        *,
        policies: Sequence[BucketPolicy] = (),
        cors_policy: str = "none",
        versioning: Versioning = "Unset",
        public_access: PublicAccess = "none",
        ip_restrictions: Sequence[str] = (),
        lifecycle_rules: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Create and configure a bucket; validate all options before API calls.

        ``none`` CORS and an empty policy leave existing configuration untouched.
        Existing buckets are not silently adopted; creation errors propagate.
        """
        policy = self.build_policy(
            bucket_name, policies=policies, versioning=versioning,
            public_access=public_access, ip_restrictions=ip_restrictions,
        )
        cors = self.build_cors(cors_policy)
        lifecycle = self.build_lifecycle(lifecycle_rules)
        create_options: dict[str, Any] = {"Bucket": bucket_name}
        if "waw" not in self.region.lower() and self.region != "us-east-1":
            create_options["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self.s3.create_bucket(**create_options)
        self._apply_configuration(bucket_name, policy, cors, lifecycle, versioning)

    def configure_bucket(
        self,
        bucket_name: str,
        *,
        policies: Sequence[BucketPolicy] = (),
        cors_policy: str = "none",
        versioning: Versioning = "Unset",
        public_access: PublicAccess = "none",
        ip_restrictions: Sequence[str] = (),
        lifecycle_rules: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> None:
        """Apply configuration to an existing bucket, without clearing omitted settings.

        Supplied grants replace the bucket policy; lifecycle rules replace the
        lifecycle configuration, including the two default cleanup actions.
        """
        policy = self.build_policy(
            bucket_name, policies=policies, versioning=versioning,
            public_access=public_access, ip_restrictions=ip_restrictions,
        )
        cors = self.build_cors(cors_policy)
        lifecycle = self.build_lifecycle(lifecycle_rules)
        self._apply_configuration(bucket_name, policy, cors, lifecycle, versioning)

    def _apply_configuration(
        self,
        bucket_name: str,
        policy: dict[str, Any],
        cors: dict[str, Any] | None,
        lifecycle: dict[str, Any],
        versioning: Versioning,
    ) -> None:
        if policy["Statement"]:
            body = json.dumps(policy, separators=(",", ":"))
            content_md5 = base64.b64encode(
                hashlib.md5(body.encode(), usedforsecurity=False).digest(),
            ).decode("ascii")
            self.s3.put_bucket_policy(
                Bucket=bucket_name, Policy=body, ContentMD5=content_md5,
            )
        if cors is not None:
            self.s3.put_bucket_cors(Bucket=bucket_name, CORSConfiguration=cors)
        if versioning != "Unset":
            self.set_versioning(bucket_name, versioning)
        self.s3.put_bucket_lifecycle_configuration(
            Bucket=bucket_name, LifecycleConfiguration=lifecycle,
        )

    def set_versioning(self, bucket_name: str, status: Versioning) -> None:
        """Enable or suspend versioning; S3 cannot restore the pristine Unset state."""
        self._validate_bucket_name(bucket_name)
        if status not in {"Enabled", "Suspended"}:
            raise ValueError("Versioning can only be Enabled or Suspended, never Unset")
        self.s3.put_bucket_versioning(
            Bucket=bucket_name, VersioningConfiguration={"Status": status},
        )

    def delete_bucket(self, bucket_name: str) -> None:
        """Delete only an empty bucket; never delete objects or versions."""
        self._validate_bucket_name(bucket_name)
        self.s3.delete_bucket(Bucket=bucket_name)


PROVIDER_CLIENT = CloudFerroBucketProvisioner


def main(argv: Sequence[str] | None = None) -> None:
    """Create and verify an empty private test bucket, leaving it in place."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument("--keys", type=Path, default=Path("keys.json"))
    parser.add_argument("--bucket-name", help="Defaults to a unique test bucket name")
    args = parser.parse_args(argv)
    keys = json.loads(args.keys.read_text())
    if not isinstance(keys, dict) or any(
        not isinstance(keys.get(key), str) or not keys[key]
        for key in ("aws_access_key", "aws_secret_key")
    ):
        raise ValueError("Keys file must contain non-empty aws_access_key and aws_secret_key strings")
    name = args.bucket_name or (
        "openeo-workspace-test-"
        + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        + "-" + uuid4().hex[:8]
    )
    print(f"Creating private bucket: {name}", flush=True)
    with CloudFerroBucketProvisioner(
        access_key=keys["aws_access_key"], secret_key=keys["aws_secret_key"],
    ) as provisioner:
        provisioner.create_bucket(name)
        print("Bucket created; verifying configuration.", flush=True)
        provisioner.s3.head_bucket(Bucket=name)
        rules = provisioner.s3.get_bucket_lifecycle_configuration(Bucket=name)["Rules"]
        for rule in rules:
            # CloudFerro returns the empty filter in the legacy Prefix format.
            if "Prefix" in rule:
                rule["Filter"] = {"Prefix": rule.pop("Prefix")}
        if rules != provisioner.build_lifecycle()["Rules"]:
            raise RuntimeError(f"Unexpected lifecycle configuration for {name}")
        if provisioner.s3.list_objects_v2(Bucket=name, MaxKeys=1).get("Contents"):
            raise RuntimeError(f"Test bucket {name} is not empty")
        grants = provisioner.s3.get_bucket_acl(Bucket=name)["Grants"]
        if any(grant["Grantee"]["Type"] != "CanonicalUser" for grant in grants):
            raise RuntimeError(f"Unexpected group ACL grant on {name}")
        try:
            provisioner.s3.get_bucket_policy(Bucket=name)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchBucketPolicy":
                raise
        else:
            raise RuntimeError(f"Unexpected bucket policy on {name}")
        print(f"Verified {name}: empty, private and default lifecycle active. Bucket left in place.")


if __name__ == "__main__":
    main()
