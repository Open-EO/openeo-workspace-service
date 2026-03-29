"""Unit tests for the Keycloak authentication layer."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from openeo_workspace_service.auth.keycloak import TokenClaims, verify_token
from openeo_workspace_service.config.settings import Settings


def _make_settings(**kwargs) -> Settings:
    defaults = dict(
        keycloak_url="http://keycloak:8080",
        keycloak_realm="openeo",
        keycloak_client_id="workspace-service",
        elasticsearch_url="http://localhost:9200",
    )
    defaults.update(kwargs)
    return Settings(**defaults)


class TestTokenClaims:
    def test_roles_empty_when_no_realm_access(self):
        claims = TokenClaims(sub="user-1", raw={})
        assert claims.roles == []

    def test_roles_from_realm_access(self):
        claims = TokenClaims(
            sub="user-1",
            realm_access={"roles": ["workspace-admin", "offline_access"]},
            raw={},
        )
        assert "workspace-admin" in claims.roles

    def test_has_role_true(self):
        claims = TokenClaims(
            sub="user-1",
            realm_access={"roles": ["workspace-admin"]},
            raw={},
        )
        assert claims.has_role("workspace-admin") is True

    def test_has_role_false(self):
        claims = TokenClaims(sub="user-1", raw={})
        assert claims.has_role("workspace-admin") is False


class TestVerifyToken:
    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self):
        settings = _make_settings()
        with pytest.raises(HTTPException) as exc_info:
            await verify_token("not.a.valid.token", settings)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_missing_kid_raises_401(self):
        """A token with no 'kid' in the header should fail immediately."""
        import base64
        import json

        # Craft a token header without kid
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "RS256", "typ": "JWT"}).encode()
        ).rstrip(b"=")
        token = f"{header.decode()}.payload.signature"

        settings = _make_settings()
        with pytest.raises(HTTPException) as exc_info:
            await verify_token(token, settings)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_returns_claims(self):
        """
        Tests the happy path by patching _get_signing_key and jose.jwt.decode.
        """
        settings = _make_settings()
        fake_payload = {
            "sub": "keycloak-user-abc123",
            "preferred_username": "alice",
            "email": "alice@example.com",
            "iss": settings.oidc_issuer,
            "aud": settings.keycloak_client_id,
            "realm_access": {"roles": ["workspace-user"]},
        }
        fake_key = {"kty": "RSA", "kid": "test-kid"}

        with (
            patch(
                "openeo_workspace_service.auth.keycloak.jwt.get_unverified_header",
                return_value={"kid": "test-kid", "alg": "RS256"},
            ),
            patch(
                "openeo_workspace_service.auth.keycloak._get_signing_key",
                new=AsyncMock(return_value=fake_key),
            ),
            patch(
                "openeo_workspace_service.auth.keycloak.jwt.decode",
                return_value=fake_payload,
            ),
        ):
            claims = await verify_token("fake.token.here", settings)

        assert claims.sub == "keycloak-user-abc123"
        assert claims.preferred_username == "alice"
        assert claims.has_role("workspace-user") is True

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        from jose.exceptions import ExpiredSignatureError

        settings = _make_settings()

        with (
            patch(
                "openeo_workspace_service.auth.keycloak.jwt.get_unverified_header",
                return_value={"kid": "test-kid", "alg": "RS256"},
            ),
            patch(
                "openeo_workspace_service.auth.keycloak._get_signing_key",
                new=AsyncMock(return_value={"kid": "test-kid"}),
            ),
            patch(
                "openeo_workspace_service.auth.keycloak.jwt.decode",
                side_effect=ExpiredSignatureError("expired"),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await verify_token("fake.token.here", settings)
            assert exc_info.value.status_code == 401
            assert "expired" in exc_info.value.detail.lower()
