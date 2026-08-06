"""Authentication tests for OIDC-protected endpoints."""

import json
import time

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from fastapi.testclient import TestClient

import workspace_service.auth as auth_module
import workspace_service.db as db_module
from workspace_service.auth import OIDCAuthManager, TokenData
from main import app, route_prefix


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class DummyWorkspaceClient:
    """Minimal DB stub for authenticated workspace listing tests."""

    async def list_workspaces(self, user_id: str, limit: int = 100):
        return [], 0


class FailingWorkspaceClient:
    """DB stub used to ensure auth failure happens before DB interaction."""

    async def list_workspaces(self, user_id: str, limit: int = 100):
        raise AssertionError("DB should not be called when authentication fails")


async def _accept_token(_: str) -> TokenData:
    return TokenData(
        sub="user-1",
        iat=1700000000,
        exp=4700000000,
        iss="https://keycloak.example.com/realms/openeo",
        aud="openeo-workspaces",
    )


async def _reject_token(_: str) -> TokenData:
    raise HTTPException(status_code=401, detail="Invalid token")


def test_protected_endpoint_requires_bearer_token(client):
    response = client.get(f"{route_prefix}/workspaces")

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "401"
    assert body["message"] == "Not authenticated"


def test_protected_endpoint_accepts_valid_token(client, monkeypatch):
    monkeypatch.setattr(auth_module.oidc_auth_manager, "verify_token", _accept_token)
    monkeypatch.setattr(db_module, "get_client", lambda: DummyWorkspaceClient())

    response = client.get(
        f"{route_prefix}/workspaces",
        headers={"Authorization": "Bearer valid-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workspaces"] == []
    assert "links" in data


def test_optional_auth_rejects_invalid_token(client, monkeypatch):
    monkeypatch.setattr(auth_module.oidc_auth_manager, "verify_token", _reject_token)
    monkeypatch.setattr(db_module, "get_client", lambda: FailingWorkspaceClient())

    response = client.get(
        f"{route_prefix}/workspace_providers",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "401"
    assert body["message"] == "Invalid token"


@pytest.mark.asyncio
async def test_oidc_discovery_and_jwks_validation(monkeypatch):
    """Verify a real RS256 token through discovery + JWKS without monkeypatching verifier logic."""
    manager = OIDCAuthManager()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk["kid"] = "integration-kid"

    now = int(time.time())
    payload = {
        "sub": "integration-user",
        "iat": now,
        "exp": now + 3600,
        "iss": manager.issuer,
        "aud": manager.client_id,
    }
    token = jwt.encode(
        payload,
        private_key,
        algorithm="RS256",
        headers={"kid": "integration-kid"},
    )

    class MockResponse:
        def __init__(self, url: str, data: dict, status_code: int = 200):
            self._url = url
            self._data = data
            self.status_code = status_code

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("GET", self._url)
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError(
                    f"HTTP {self.status_code}",
                    request=request,
                    response=response,
                )

    async def fake_get(self, url, *args, **kwargs):  # noqa: ARG001
        if url == manager.discovery_url:
            return MockResponse(
                url,
                {
                    "issuer": manager.issuer,
                    "jwks_uri": manager.jwks_url,
                },
            )
        if url == manager.jwks_url:
            return MockResponse(url, {"keys": [jwk]})
        return MockResponse(url, {}, status_code=404)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    token_data = await manager.verify_token(token)

    assert token_data.sub == "integration-user"
    assert token_data.iss == manager.issuer


@pytest.mark.asyncio
async def test_oidc_jwks_key_rotation_refresh(monkeypatch):
    """Verify verifier refreshes JWKS cache when token kid is missing due to key rotation."""
    manager = OIDCAuthManager()

    old_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    old_public_key = old_private_key.public_key()
    old_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(old_public_key))
    old_jwk["kid"] = "old-kid"

    new_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    new_public_key = new_private_key.public_key()
    new_jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(new_public_key))
    new_jwk["kid"] = "new-kid"

    now = int(time.time())
    payload = {
        "sub": "rotated-user",
        "iat": now,
        "exp": now + 3600,
        "iss": manager.issuer,
        "aud": manager.client_id,
    }
    token = jwt.encode(
        payload,
        new_private_key,
        algorithm="RS256",
        headers={"kid": "new-kid"},
    )

    class MockResponse:
        def __init__(self, url: str, data: dict, status_code: int = 200):
            self._url = url
            self._data = data
            self.status_code = status_code

        def json(self):
            return self._data

        def raise_for_status(self):
            if self.status_code >= 400:
                request = httpx.Request("GET", self._url)
                response = httpx.Response(self.status_code, request=request)
                raise httpx.HTTPStatusError(
                    f"HTTP {self.status_code}",
                    request=request,
                    response=response,
                )

    call_counts = {"jwks": 0}

    async def fake_get(self, url, *args, **kwargs):  # noqa: ARG001
        if url == manager.discovery_url:
            return MockResponse(
                url,
                {
                    "issuer": manager.issuer,
                    "jwks_uri": manager.jwks_url,
                },
            )
        if url == manager.jwks_url:
            call_counts["jwks"] += 1
            if call_counts["jwks"] == 1:
                return MockResponse(url, {"keys": [old_jwk]})
            return MockResponse(url, {"keys": [new_jwk]})
        return MockResponse(url, {}, status_code=404)

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    token_data = await manager.verify_token(token)

    assert token_data.sub == "rotated-user"
    assert call_counts["jwks"] >= 2
