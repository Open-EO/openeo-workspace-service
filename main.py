"""
OpenEO Workspaces API
A FastAPI implementation of the openEO Workspaces Extension
"""
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from workspace_service.config import settings
from workspace_service.routes import workspaces, providers
from workspace_service import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

route_prefix = f"{settings.api_prefix}/{settings.api_version}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and clean up services during the application lifespan."""
    logger.info("Starting up OpenEO Workspaces API")
    await db.initialize()
    logger.info("Database initialized successfully")
    try:
        yield
    finally:
        logger.info("Shutting down OpenEO Workspaces API")
        await db.close()

# Initialize FastAPI app
app = FastAPI(
    title="openEO API - Workspaces Extension",
    version="0.1.0",
    description="The Workspace Extension to the openEO API provides an interface for connecting external file storage to openEO back-end implementations.",
    openapi_url=f"{route_prefix}/openapi.json",
    docs_url=f"{route_prefix}/docs",
    redoc_url=f"{route_prefix}/redoc",
    lifespan=lifespan,
)

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health():
    """Health check endpoint"""
    return {"status": "healthy"}

# Include routers
app.include_router(
    providers.router,
    prefix=route_prefix,
    tags=["Workspaces"]
)

app.include_router(
    workspaces.router,
    prefix=route_prefix,
    tags=["Workspaces"]
)

# Root endpoint
@app.get(route_prefix, tags=["API Info"])
async def api_info():
    """Return API version and basic information"""
    return {
        "api_version": "0.1.0",
        "title": "openEO API - Workspaces Extension",
        "documentation_url": "https://github.com/Open-EO/openeo-api/blob/draft/extensions/workspaces/README.md"
    }

# Exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Handle HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": str(exc.status_code),
            "message": exc.detail,
        }
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug
    )
