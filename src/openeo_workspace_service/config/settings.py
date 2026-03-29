"""
Application settings loaded from environment variables / .env file.

All configuration is centralised here so every other module imports
`get_settings()` rather than reading `os.environ` directly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ---------------------------------------------------------------- Server
    environment: str = "production"
    debug: bool = False
    server_host: str = "0.0.0.0"
    server_port: int = 8000

    # ------------------------------------------------------------------ CORS
    cors_origins: list[str] = ["*"]

    # --------------------------------------------------------- Elasticsearch
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_username: str | None = None
    elasticsearch_password: str | None = None
    elasticsearch_ca_certs: str | None = None
    elasticsearch_verify_certs: bool = True
    elasticsearch_index_prefix: str = "openeo_workspaces"

    # ---------------------------------------------------------------- Index names (derived)
    @property
    def workspace_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_v1"

    @property
    def provider_index(self) -> str:
        return f"{self.elasticsearch_index_prefix}_providers_v1"

    # ---------------------------------------------------------------- Keycloak / OIDC
    keycloak_url: AnyHttpUrl = Field(
        default="http://localhost:8080",
        description="Base URL of the Keycloak server, e.g. https://keycloak.example.com",
    )
    keycloak_realm: str = "openeo"
    keycloak_client_id: str = "workspace-service"
    keycloak_client_secret: str | None = None

    # Derived OIDC URLs
    @property
    def oidc_issuer(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}"

    @property
    def oidc_jwks_uri(self) -> str:
        return f"{self.oidc_issuer}/protocol/openid-connect/certs"

    @property
    def oidc_token_endpoint(self) -> str:
        return f"{self.oidc_issuer}/protocol/openid-connect/token"

    # JWT validation
    jwt_algorithms: list[str] = ["RS256"]
    jwt_audience: str | None = None  # defaults to keycloak_client_id when None

    # ------------------------------------------------ Workspace provider defaults
    default_workspace_provider: str | None = None

    # ------------------------------------------ Internal provisioning API key
    # When set, PUT /internal/workspaces/{id}/status is enabled.
    internal_api_key: str | None = None

    # -------------------------------------------------------------- Logging
    # Force JSON log output. Defaults to JSON when debug=False.
    json_logs: bool | None = None

    # ------------------------------------------------------------- Rate limiting
    rate_limit_requests: int = 100  # max requests per window per user
    rate_limit_window_s: int = 60  # window size in seconds

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
