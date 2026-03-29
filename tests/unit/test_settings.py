"""Unit tests for application settings."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from openeo_workspace_service.config.settings import Settings


class TestSettings:
    def test_defaults_are_valid(self):
        s = Settings()
        assert s.server_port == 8000
        assert s.debug is False
        assert s.elasticsearch_url == "http://localhost:9200"
        assert s.keycloak_realm == "openeo"

    def test_derived_oidc_issuer(self):
        s = Settings(keycloak_url="https://kc.example.com", keycloak_realm="myrealm")
        assert s.oidc_issuer == "https://kc.example.com/realms/myrealm"

    def test_derived_jwks_uri(self):
        s = Settings(keycloak_url="https://kc.example.com", keycloak_realm="myrealm")
        assert s.oidc_jwks_uri == (
            "https://kc.example.com/realms/myrealm/protocol/openid-connect/certs"
        )

    def test_derived_workspace_index(self):
        s = Settings(elasticsearch_index_prefix="myapp")
        assert s.workspace_index == "myapp_v1"

    def test_derived_provider_index(self):
        s = Settings(elasticsearch_index_prefix="myapp")
        assert s.provider_index == "myapp_providers_v1"

    def test_cors_origins_split_from_string(self):
        s = Settings(cors_origins="https://a.example.com, https://b.example.com")
        assert s.cors_origins == ["https://a.example.com", "https://b.example.com"]

    def test_cors_origins_accepts_list(self):
        s = Settings(cors_origins=["https://a.example.com"])
        assert s.cors_origins == ["https://a.example.com"]

    def test_jwt_audience_defaults_to_client_id(self):
        s = Settings(keycloak_client_id="my-client")
        # jwt_audience is None by default; consuming code falls back to client_id
        assert s.jwt_audience is None
        assert s.keycloak_client_id == "my-client"

    def test_internal_api_key_optional(self):
        s = Settings()
        assert s.internal_api_key is None

    def test_internal_api_key_set(self):
        s = Settings(internal_api_key="secret-key-abc")
        assert s.internal_api_key == "secret-key-abc"

    def test_debug_flag(self):
        s = Settings(debug=True)
        assert s.debug is True

    def test_elasticsearch_credentials_optional(self):
        s = Settings()
        assert s.elasticsearch_username is None
        assert s.elasticsearch_password is None
