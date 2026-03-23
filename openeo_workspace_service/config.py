"""
openeo_workspace_service/config.py
-----------------------------------
Application-wide settings loaded from environment variables or a .env file.
"""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OPENEO_WS_", env_file=".env", extra="ignore")

    # ── Database ────────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./workspaces.db"
    """Async SQLAlchemy URL.  Use ``postgresql+asyncpg://…`` in production."""

    # ── Auth ────────────────────────────────────────────────────────────────
    oidc_discovery_url: str = ""
    """OIDC well-known discovery URL used to validate Bearer tokens.
    Leave empty to disable token validation (useful for testing)."""

    # ── Service ─────────────────────────────────────────────────────────────
    public_url: str = "https://openeo.example/api/v1"
    """Base URL advertised in Location headers and links."""

    default_workspace_provider: str | None = None
    """Provider name chosen when a *create* workspace request omits ``type``."""

    page_size_default: int = 25
    page_size_max: int = 100

    # ── Logging ─────────────────────────────────────────────────────────────
    log_level: str = "INFO"


settings = Settings()
