"""
OpenEO Workspaces API
A FastAPI implementation of the openEO Workspaces Extension
"""
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from app.config import settings
from app.routes import workspaces, providers
from app import db

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
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
    prefix="/api/v1",
    tags=["Workspaces"]
)

app.include_router(
    workspaces.router,
    prefix="/api/v1",
    tags=["Workspaces"]
)

# Root endpoint
@app.get("/api/v1", tags=["API Info"])
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

