"""
openEO Workspace Service – application entry point.

Wires together FastAPI, Elasticsearch, and Keycloak OIDC middleware.
"""

from __future__ import annotations

import uvicorn

from openeo_workspace_service.app import create_app

app = create_app()


def run() -> None:
    """CLI entry-point (see pyproject.toml [project.scripts])."""
    from openeo_workspace_service.config.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        "openeo_workspace_service.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=settings.debug,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    run()
