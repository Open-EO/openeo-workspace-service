"""Application factory – builds and configures the FastAPI instance."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from openeo_workspace_service.api.admin import router as admin_router
from openeo_workspace_service.api.exceptions import register_exception_handlers
from openeo_workspace_service.api.health import router as health_router
from openeo_workspace_service.api.internal import router as internal_router
from openeo_workspace_service.api.middleware import RequestIDMiddleware
from openeo_workspace_service.api.openapi import configure_openapi
from openeo_workspace_service.api.rate_limit import RateLimitMiddleware
from openeo_workspace_service.api.workspace_providers import router as providers_router
from openeo_workspace_service.api.workspaces import router as workspaces_router
from openeo_workspace_service.config.logging import configure_logging
from openeo_workspace_service.config.settings import get_settings
from openeo_workspace_service.db.aliases import ensure_aliases
from openeo_workspace_service.db.elasticsearch import (
    get_es_client,
    init_indices,
    seed_default_providers,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle hook."""
    settings = get_settings()
    configure_logging(debug=settings.debug, json_logs=settings.json_logs)
    logger.info("starting openeo-workspace-service", version="0.1.0", env=settings.environment)

    # Ensure Elasticsearch indices exist, aliases, and seed default providers
    async with get_es_client() as es:
        await init_indices(es)
        await ensure_aliases(es)
        await seed_default_providers(es)

    logger.info("elasticsearch indices ready")
    yield
    logger.info("shutting down openeo-workspace-service")


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title="openEO Workspace Service",
        description=(
            "VITO implementation of the openEO Workspaces Extension API, "
            "backed by Elasticsearch and secured with Keycloak."
        ),
        version="0.1.0",
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=_lifespan,
    )

    # ------------------------------------------------------------------ CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --------------------------------------------------------- Middleware
    application.add_middleware(RequestIDMiddleware)
    application.add_middleware(
        RateLimitMiddleware,
        limit=settings.rate_limit_requests,
        window=settings.rate_limit_window_s,
    )

    # --------------------------------------------------------------- Routers
    application.include_router(health_router)
    application.include_router(providers_router)
    application.include_router(workspaces_router)
    application.include_router(admin_router)
    application.include_router(internal_router)

    # -------------------------------------------------- Exception handlers
    register_exception_handlers(application)

    # ----------------------------------------- Custom OpenAPI schema
    configure_openapi(application)

    return application
