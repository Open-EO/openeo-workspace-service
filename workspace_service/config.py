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

    # Elasticsearch
    elasticsearch_host: str = "localhost"
    elasticsearch_port: int = 9200
    elasticsearch_user: Optional[str] = None
    elasticsearch_password: Optional[str] = None
    elasticsearch_scheme: str = "https"
    elasticsearch_index_prefix: str = "openeo-workspaces"

    # Workspace configuration
    default_workspace_provider: str = "s3"
    max_workspace_quota: int = 1099511627776  # 1TB in bytes

    # Supported providers
    supported_providers: list = ["s3"]


settings = Settings()

