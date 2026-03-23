"""
tests/test_providers_unit.py
-----------------------------
Unit tests for the provider registry and the S3 provider's parameter validation.
No real cloud calls are made.
"""
from __future__ import annotations

import pytest

from openeo_workspace_service.providers.base import all_providers, get_provider
from openeo_workspace_service.providers.s3 import S3WorkspaceProvider


def test_get_provider_s3():
    p = get_provider("S3")
    assert isinstance(p, S3WorkspaceProvider)


def test_get_provider_case_insensitive():
    p = get_provider("s3")
    assert isinstance(p, S3WorkspaceProvider)


def test_get_provider_unknown_raises():
    with pytest.raises(KeyError):
        get_provider("UNKNOWN_XYZ")


def test_all_providers_includes_s3():
    providers = all_providers()
    assert "S3" in providers


def test_s3_validate_parameters_valid():
    p = S3WorkspaceProvider()
    # Should not raise.
    p.validate_parameters(
        {
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "aws_secret_access_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "bucket_name": "my-bucket",
        }
    )


def test_s3_validate_parameters_missing_raises():
    p = S3WorkspaceProvider()
    with pytest.raises(ValueError, match="bucket_name"):
        p.validate_parameters(
            {
                "aws_access_key_id": "key",
                "aws_secret_access_key": "secret",
                # bucket_name omitted
            }
        )


def test_s3_metadata_has_intents():
    p = S3WorkspaceProvider()
    meta = p.metadata
    assert "create" in meta.intents
    assert "register" in meta.intents


def test_s3_metadata_parameters_documented():
    p = S3WorkspaceProvider()
    params = p.metadata.parameters
    for name in ("aws_access_key_id", "aws_secret_access_key", "bucket_name"):
        assert name in params
        assert params[name].description
