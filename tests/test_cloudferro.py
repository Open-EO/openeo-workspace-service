import base64
import hashlib
import json

import pytest
from botocore.exceptions import ClientError
from botocore.stub import Stubber

from workspace_service.provider_clients.cloudferro import CloudFerroBucketProvisioner
from workspace_service.provider_clients.cloudferro import main
from workspace_service.provider_clients.cloudferro import CloudFerroWorkspaceParameters


@pytest.fixture
def provisioner():
    with CloudFerroBucketProvisioner(
        access_key="test-access-key", secret_key="test-secret-key",
    ) as instance:
        yield instance


def test_default_creation(provisioner):
    lifecycle = provisioner.build_lifecycle()
    assert lifecycle == {"Rules": [{
        "ID": "CleanupMultipartUploadsDeleteMarkers",
        "Filter": {"Prefix": ""},
        "Status": "Enabled",
        "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        "Expiration": {"ExpiredObjectDeleteMarker": True},
    }]}
    with Stubber(provisioner.s3) as stub:
        stub.add_response("create_bucket", {}, {"Bucket": "workspace-test"})
        stub.add_response("put_bucket_lifecycle_configuration", {}, {
            "Bucket": "workspace-test", "LifecycleConfiguration": lifecycle,
        })
        provisioner.create_bucket("workspace-test")
        stub.assert_no_pending_responses()


def test_workspace_provisioning():
    from unittest.mock import patch

    parameters = CloudFerroWorkspaceParameters(
        aws_access_key_id="test-access", aws_secret_access_key="test-secret",
    )
    with patch.object(CloudFerroBucketProvisioner, "create_bucket") as create:
        metadata = CloudFerroBucketProvisioner.provision_workspace("unique-id", parameters)
    create.assert_called_once_with("openeo-workspace-unique-id")
    assert metadata == {
        "url": "https://s3.waw3-1.cloudferro.com/openeo-workspace-unique-id",
        "properties": {
            "bucket_name": "openeo-workspace-unique-id",
            "region": "waw3-1",
            "endpoint_url": "https://s3.waw3-1.cloudferro.com",
            "s3_url": "s3://openeo-workspace-unique-id",
        },
    }


def test_full_creation(provisioner):
    policies = [{
        "principal": "arn:aws:iam::project:user/user",
        "bucket_access": "LRWSAFE",
        "policy_vars": {"KEY": 'results/"*'},
    }]
    policy = provisioner.build_policy(
        "workspace-test", policies=policies, versioning="Enabled",
        public_access="R", ip_restrictions=["192.0.2.0/24"],
    )
    body = json.dumps(policy, separators=(",", ":"))
    md5 = base64.b64encode(
        hashlib.md5(body.encode(), usedforsecurity=False).digest(),
    ).decode()
    cors_name = "get_head_from_anywhere_content_headers"
    rules = {
        "CAUTION_DANGER_expire_objects_param_prefix_days@results": {
            "Prefix": "results/", "Days": 30,
        },
    }
    with Stubber(provisioner.s3) as stub:
        stub.add_response("create_bucket", {}, {"Bucket": "workspace-test"})
        stub.add_response("put_bucket_policy", {}, {
            "Bucket": "workspace-test", "Policy": body, "ContentMD5": md5,
        })
        stub.add_response("put_bucket_cors", {}, {
            "Bucket": "workspace-test",
            "CORSConfiguration": provisioner.build_cors(cors_name),
        })
        stub.add_response("put_bucket_versioning", {}, {
            "Bucket": "workspace-test", "VersioningConfiguration": {"Status": "Enabled"},
        })
        stub.add_response("put_bucket_lifecycle_configuration", {}, {
            "Bucket": "workspace-test",
            "LifecycleConfiguration": provisioner.build_lifecycle(rules),
        })
        provisioner.create_bucket(
            "workspace-test", policies=policies, versioning="Enabled",
            public_access="R", ip_restrictions=["192.0.2.0/24"],
            cors_policy=cors_name, lifecycle_rules=rules,
        )
        stub.assert_no_pending_responses()
    grant, public, restriction = policy["Statement"]
    assert grant["Resource"][-1] == 'arn:aws:s3:::workspace-test/results/"*'
    assert "s3:DeleteObjectVersion" not in grant["Action"]
    assert "s3:GetObjectVersion" in grant["Action"]
    assert public["Principal"] == {"AWS": ["*"]}
    assert restriction["Condition"] == {
        "NotIpAddress": {"aws:SourceIp": ["192.0.2.0/24"]},
    }


@pytest.mark.parametrize("region,extra", [
    ("waw3-1", {}),
    ("WAW3-2", {}),
    ("us-east-1", {}),
    ("eu-central-1", {"CreateBucketConfiguration": {"LocationConstraint": "eu-central-1"}}),
])
def test_regions(region, extra):
    with CloudFerroBucketProvisioner(
        access_key="test", secret_key="test", region=region,
    ) as provisioner, Stubber(provisioner.s3) as stub:
        stub.add_response("create_bucket", {}, {"Bucket": "workspace-test", **extra})
        stub.add_response("put_bucket_lifecycle_configuration", {}, {
            "Bucket": "workspace-test",
            "LifecycleConfiguration": provisioner.build_lifecycle(),
        })
        provisioner.create_bucket("workspace-test")
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("access,versioning,actions", [
    ("R", "Unset", ["GetObject"]),
    ("R", "Enabled", ["GetObject", "GetObjectVersion"]),
    ("LR", "Unset", ["GetObject", "ListBucket"]),
    ("LR", "Suspended", ["GetObject", "GetObjectVersion", "ListBucket", "ListBucketVersions"]),
    ("RW", "Unset", [
        "AbortMultipartUpload", "DeleteObject", "GetObject",
        "ListMultipartUploadParts", "PutObject",
    ]),
    ("LRW", "Unset", [
        "AbortMultipartUpload", "DeleteObject", "GetObject", "ListBucket",
        "ListMultipartUploadParts", "PutObject",
    ]),
    ("LRW", "Enabled", [
        "AbortMultipartUpload", "DeleteObject", "DeleteObjectVersion",
        "GetObject", "GetObjectVersion", "ListBucket", "ListBucketVersions",
        "ListMultipartUploadParts", "PutObject",
    ]),
    ("LRWSAFE", "Enabled", [
        "AbortMultipartUpload", "DeleteObject", "GetObject", "GetObjectVersion",
        "ListBucket", "ListBucketVersions", "ListMultipartUploadParts", "PutObject",
    ]),
    ("BucketInventory", "Unset", [
        "GetBucketInventoryConfiguration", "PutBucketInventoryConfiguration",
        "DeleteBucketInventoryConfiguration",
    ]),
    ("BucketInventoryOBS", "Unset", ["PutObject"]),
])
def test_named_policies(access, versioning, actions):
    policy = CloudFerroBucketProvisioner.build_policy(
        "workspace-test",
        policies=[{"principal": "user", "bucket_access": access}],
        versioning=versioning,
    )
    statement = policy["Statement"][0]
    assert set(statement["Action"]) == {f"s3:{action}" for action in actions}
    if access == "BucketInventoryOBS":
        assert statement["Principal"] == {"Service": ["obs"]}
    elif access == "RW":
        assert "Sid" not in statement
    else:
        assert statement["Sid"] == f"{access}_0"


@pytest.mark.parametrize("public_access,expected", [
    ("none", []), ("R", ["s3:GetObject"]), ("DANGER_LR", ["s3:GetObject", "s3:ListBucket"]),
])
def test_public_only_policies(public_access, expected):
    policy = CloudFerroBucketProvisioner.build_policy(
        "workspace-test", public_access=public_access,
    )
    statements = policy["Statement"]
    assert len(statements) == bool(expected)
    if statements:
        assert statements[0]["Action"] == expected


def test_ip_only_policy():
    policy = CloudFerroBucketProvisioner.build_policy(
        "workspace-test", ip_restrictions=["192.0.2.1/32", "2001:db8::/32"],
    )
    assert policy["Statement"][0]["Effect"] == "Deny"


@pytest.mark.parametrize("name,origins", [
    ("get_from_anywhere_anyheader", ["*"]),
    ("get_from_apex", [
        "https://apex-ge-config-builder.sparkgeo.uk", "https://*.apex.esa.int",
    ]),
    ("get_from_sonata", [
        "https://apex-ge-config-builder.sparkgeo.uk",
        "https://catalogue.sonata-nbs.com", "https://*.sonata-nbs.com",
    ]),
    ("get_from_webeditor", ["https://*.dataspace.copernicus.eu/"]),
    ("get_head_from_anywhere_content_headers", ["*"]),
])
def test_cors_presets(name, origins):
    rule = CloudFerroBucketProvisioner.build_cors(name)["CORSRules"][0]
    assert rule["AllowedOrigins"] == origins
    assert rule["AllowedHeaders"] == ["*"]
    if name == "get_head_from_anywhere_content_headers":
        assert rule["AllowedMethods"] == ["GET", "HEAD"]
        assert rule["ExposeHeaders"] == [
            "Content-Range", "Content-Length", "Accept-Ranges", "ETag",
        ]
        assert rule["MaxAgeSeconds"] == 3600
    else:
        assert rule["AllowedMethods"] == ["GET"]


def test_lifecycle_grouping_and_conflicts():
    name = "CAUTION_DANGER_expire_objects_param_prefix_days"
    result = CloudFerroBucketProvisioner.build_lifecycle({
        f"{name}@a": {"Prefix": "", "Days": 7},
        f"{name}@b": {"Prefix": "other/", "Days": 30},
    })
    assert result == {"Rules": [
        {
            "ID": "DangerExpireObjectaCleanupMultipartUploads",
            "Filter": {"Prefix": ""}, "Status": "Enabled",
            "Expiration": {"Days": 7},
            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1},
        },
        {
            "ID": "DangerExpireObjectb",
            "Filter": {"Prefix": "other/"}, "Status": "Enabled",
            "Expiration": {"Days": 30},
        },
    ]}
    with pytest.raises(ValueError, match="Conflicting"):
        CloudFerroBucketProvisioner.build_lifecycle({
            f"{name}@a": {"Prefix": "", "Days": 7},
            f"{name}@b": {"Prefix": "", "Days": 30},
        })


def test_lifecycle_id_limit_and_uniqueness():
    name = "CAUTION_DANGER_expire_objects_param_prefix_days"
    suffix = "x" * 300
    result = CloudFerroBucketProvisioner.build_lifecycle({
        f"{name}@{suffix}": {"Prefix": "", "Days": 7},
    })
    assert len(result["Rules"][0]["ID"]) == 255
    with pytest.raises(ValueError, match="unique"):
        CloudFerroBucketProvisioner.build_lifecycle({
            f"{name}@{suffix}a": {"Prefix": "a/", "Days": 7},
            f"{name}@{suffix}b": {"Prefix": "b/", "Days": 7},
        })


@pytest.mark.parametrize("kwargs", [
    {"public_access": "R"},
    {"ip_restrictions": ["192.0.2.0/24"]},
])
def test_public_and_ip_policies_applied_without_grants(provisioner, kwargs):
    policy = provisioner.build_policy("workspace-test", **kwargs)
    body = json.dumps(policy, separators=(",", ":"))
    md5 = base64.b64encode(
        hashlib.md5(body.encode(), usedforsecurity=False).digest(),
    ).decode()
    with Stubber(provisioner.s3) as stub:
        stub.add_response("put_bucket_policy", {}, {
            "Bucket": "workspace-test", "Policy": body, "ContentMD5": md5,
        })
        stub.add_response("put_bucket_lifecycle_configuration", {}, {
            "Bucket": "workspace-test",
            "LifecycleConfiguration": provisioner.build_lifecycle(),
        })
        provisioner.configure_bucket("workspace-test", **kwargs)
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("kwargs", [
    {"cors_policy": "unknown"},
    {"versioning": "unset"},
    {"public_access": "LRW"},
    {"ip_restrictions": ["not-an-ip"]},
    {"policies": [{"principal": "", "bucket_access": "R"}]},
    {"policies": [{"principal": "user", "bucket_access": "unknown"}]},
    {"policies": [{"principal": "user", "bucket_access": "RW"}], "versioning": "Enabled"},
    {"policies": [{"principal": "user", "bucket_access": "LRWSAFE"}]},
    {"lifecycle_rules": {"unknown": {}}},
    {"lifecycle_rules": {"CAUTION_DANGER_expire_objects_param_prefix_days": {
        "Prefix": "", "Days": 0,
    }}},
    {"lifecycle_rules": {"CAUTION_DANGER_expire_objects_param_prefix_days": {
        "Days": 1,
    }}},
])
def test_invalid_config_makes_no_requests(provisioner, kwargs):
    with Stubber(provisioner.s3), pytest.raises(ValueError):
        provisioner.create_bucket("workspace-test", **kwargs)


@pytest.mark.parametrize("name", [
    "", "ab", "a" * 64, "Bad-name", "bad_name", "-bad-name",
    "bad-name-", "xn--name", "name-s3alias", "name.with.dots",
])
def test_invalid_names(provisioner, name):
    with Stubber(provisioner.s3), pytest.raises(ValueError, match="Invalid bucket"):
        provisioner.create_bucket(name)


def test_legacy_name():
    assert CloudFerroBucketProvisioner.build_policy("OpenEO-data")["Statement"] == []


def test_suspend_and_refuse_unset(provisioner):
    with Stubber(provisioner.s3) as stub:
        stub.add_response("put_bucket_versioning", {}, {
            "Bucket": "workspace-test",
            "VersioningConfiguration": {"Status": "Suspended"},
        })
        provisioner.set_versioning("workspace-test", "Suspended")
        with pytest.raises(ValueError, match="never Unset"):
            provisioner.set_versioning("workspace-test", "Unset")
        stub.assert_no_pending_responses()


def test_configure_existing_bucket(provisioner):
    with Stubber(provisioner.s3) as stub:
        stub.add_response("put_bucket_lifecycle_configuration", {}, {
            "Bucket": "workspace-test",
            "LifecycleConfiguration": provisioner.build_lifecycle(),
        })
        provisioner.configure_bucket("workspace-test")
        stub.assert_no_pending_responses()


def test_creation_error_is_not_ignored(provisioner):
    with Stubber(provisioner.s3) as stub:
        stub.add_client_error("create_bucket", "BucketAlreadyExists",
                              expected_params={"Bucket": "workspace-test"})
        with pytest.raises(ClientError, match="BucketAlreadyExists"):
            provisioner.create_bucket("workspace-test")
        stub.assert_no_pending_responses()


def test_configuration_failure_does_not_delete_bucket(provisioner):
    with Stubber(provisioner.s3) as stub:
        stub.add_response("create_bucket", {}, {"Bucket": "workspace-test"})
        stub.add_client_error("put_bucket_lifecycle_configuration", "AccessDenied",
                              expected_params={
                                  "Bucket": "workspace-test",
                                  "LifecycleConfiguration": provisioner.build_lifecycle(),
                              })
        with pytest.raises(ClientError, match="AccessDenied"):
            provisioner.create_bucket("workspace-test")
        stub.assert_no_pending_responses()


def test_delete_empty_bucket_only(provisioner):
    with Stubber(provisioner.s3) as stub:
        stub.add_response("delete_bucket", {}, {"Bucket": "workspace-test"})
        provisioner.delete_bucket("workspace-test")
        stub.add_client_error("delete_bucket", "BucketNotEmpty",
                              expected_params={"Bucket": "workspace-test"})
        with pytest.raises(ClientError, match="BucketNotEmpty"):
            provisioner.delete_bucket("workspace-test")
        stub.assert_no_pending_responses()


@pytest.mark.parametrize("legacy_prefix", [False, True])
def test_test_bucket_cli(provisioner, monkeypatch, tmp_path, capsys, legacy_prefix):
    keys_file = tmp_path / "keys.json"
    keys_file.write_text(json.dumps({
        "aws_access_key": "test-access", "aws_secret_key": "test-secret",
    }))

    def factory(**kwargs):
        assert kwargs == {"access_key": "test-access", "secret_key": "test-secret"}
        return provisioner

    monkeypatch.setattr("workspace_service.provider_clients.cloudferro.CloudFerroBucketProvisioner", factory)
    bucket = {"Bucket": "workspace-test"}
    lifecycle = provisioner.build_lifecycle()
    returned = provisioner.build_lifecycle()
    if legacy_prefix:
        returned["Rules"][0]["Prefix"] = returned["Rules"][0].pop("Filter")["Prefix"]
    with Stubber(provisioner.s3) as stub:
        stub.add_response("create_bucket", {}, bucket)
        stub.add_response("put_bucket_lifecycle_configuration", {}, {
            **bucket, "LifecycleConfiguration": lifecycle,
        })
        stub.add_response("head_bucket", {}, bucket)
        stub.add_response("get_bucket_lifecycle_configuration", returned, bucket)
        stub.add_response("list_objects_v2", {"KeyCount": 0}, {**bucket, "MaxKeys": 1})
        stub.add_response("get_bucket_acl", {"Grants": [{
            "Grantee": {"Type": "CanonicalUser", "ID": "owner"},
            "Permission": "FULL_CONTROL",
        }]}, bucket)
        stub.add_client_error("get_bucket_policy", "NoSuchBucketPolicy",
                              expected_params=bucket)
        main(["--keys", str(keys_file), "--bucket-name", "workspace-test"])
        stub.assert_no_pending_responses()
    output = capsys.readouterr().out
    assert "Verified workspace-test" in output
    assert "test-secret" not in output


def test_test_bucket_cli_rejects_invalid_credentials(tmp_path):
    keys_file = tmp_path / "keys.json"
    keys_file.write_text('{"aws_access_key": "test"}')
    with pytest.raises(ValueError, match="Keys file must contain"):
        main(["--keys", str(keys_file)])
