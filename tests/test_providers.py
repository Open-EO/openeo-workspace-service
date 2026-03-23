"""
tests/test_providers.py
------------------------
Tests for GET /workspace_providers.
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_providers_unauthenticated(client):
    """Endpoint must be reachable without a Bearer token."""
    resp = await client.get("/workspace_providers")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_list_providers_returns_known_providers(client):
    resp = await client.get("/workspace_providers")
    body = resp.json()

    assert "providers" in body
    providers = body["providers"]
    # At minimum the three built-in providers should be present.
    for name in ("S3", "AZURE", "GCS"):
        assert name in providers, f"Expected provider {name!r} in response"


@pytest.mark.asyncio
async def test_provider_has_required_fields(client):
    resp = await client.get("/workspace_providers")
    providers = resp.json()["providers"]

    for name, provider in providers.items():
        assert "intents" in provider, f"{name}: missing 'intents'"
        assert len(provider["intents"]) >= 1, f"{name}: 'intents' must not be empty"
        assert "parameters" in provider, f"{name}: missing 'parameters'"


@pytest.mark.asyncio
async def test_s3_provider_intents(client):
    resp = await client.get("/workspace_providers")
    s3 = resp.json()["providers"]["S3"]
    assert "create" in s3["intents"]
    assert "register" in s3["intents"]


@pytest.mark.asyncio
async def test_s3_provider_parameters(client):
    resp = await client.get("/workspace_providers")
    params = resp.json()["providers"]["S3"]["parameters"]
    for required_param in ("aws_access_key_id", "aws_secret_access_key", "bucket_name"):
        assert required_param in params, f"S3 provider missing parameter {required_param!r}"
