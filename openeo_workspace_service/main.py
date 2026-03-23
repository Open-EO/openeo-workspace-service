"""
openeo_workspace_service/main.py
----------------------------------
Application factory and CLI entry point.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from openeo_workspace_service.config import settings
from openeo_workspace_service.db.session import init_db
from openeo_workspace_service.routers import providers, workspaces

logging.basicConfig(level=settings.log_level.upper())
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="openEO Workspace Service",
        version="0.1.0",
        description=(
            "Reference implementation of the **openEO Workspaces Extension** "
            "(v0.1.0).  Provides an interface for connecting external file storage "
            "such as cloud buckets to openEO back-ends."
        ),
        license_info={"name": "Apache 2.0", "url": "https://www.apache.org/licenses/LICENSE-2.0"},
        contact={
            "name": "openEO Consortium",
            "url": "https://openeo.org",
            "email": "openeo.psc@uni-muenster.de",
        },
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Startup ──────────────────────────────────────────────────────────────
    @app.on_event("startup")
    async def _startup() -> None:
        await init_db()
        logger.info("openEO Workspace Service started. DB: %s", settings.database_url)

    # ── Exception handlers ───────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def _generic_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": "InternalError", "message": "An unexpected error occurred."},
        )

    # ── Routers ──────────────────────────────────────────────────────────────
    app.include_router(providers.router)
    app.include_router(workspaces.router)

    return app


app = create_app()


def cli() -> None:
    """Entry-point used by ``openeo-workspace-service`` console script."""
    import uvicorn

    uvicorn.run(
        "openeo_workspace_service.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    cli()
