"""
Configuration settings for the OpenEO Workspaces API
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    """Application settings"""
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # API
    debug: bool = False
    api_version: str = "v1"
    api_prefix: str = "/api"

    # Security
    oidc_issuer_url: str = "http://localhost/realms/openeo"
    oidc_client_id: str = "openeo-workspaces"
    oidc_client_secret: Optional[str] = None
    oidc_verify_tls: bool = True
    oidc_verify_audience: bool = True
    oidc_jwks_cache_ttl_seconds: int = 300
    jwt_algorithm: str = "RS256"

    # Git workspace store
    git_repo_path: str = "./data"
    git_remote_url: Optional[str] = None
    git_author_name: str = "Workspace Service"
    git_author_email: str = "workspace-service@openeo"

    # Workspace configuration
    default_workspace_provider: str = "s3"
    max_workspace_quota_mb: int = 1000000  # 1TB in megabytes

    # Supported providers
    supported_providers: list = ["s3"]


settings = Settings()

