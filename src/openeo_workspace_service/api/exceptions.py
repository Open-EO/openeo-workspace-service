"""
Global exception handlers for the FastAPI application.

Registers handlers for:
  - ``RequestValidationError`` (422) – Pydantic parse failures
  - ``HTTPException``           (4xx/5xx) – already-formatted HTTP errors
  - ``Exception``               (500) – unexpected / unhandled errors

All error responses follow the openEO error body convention::

    {
        "id":      "<request-id or uuid>",
        "code":    "ValidationError",
        "message": "human-readable description",
        "links":   []
    }
"""

from __future__ import annotations

import traceback
import uuid

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# OpenEO-shaped error body
# ---------------------------------------------------------------------------


def _error_body(
    code: str,
    message: str,
    request: Request,
    links: list[dict] | None = None,
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "code": code,
        "message": message,
        "links": links or [],
    }


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all global exception handlers to *app*."""

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Flatten Pydantic v2 errors into a readable message
        errors = exc.errors()
        details = "; ".join(f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}" for e in errors)
        logger.debug(
            "request validation failed",
            path=request.url.path,
            errors=errors,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                code="ValidationError",
                message=f"Request body is invalid: {details}",
                request=request,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        # Map status codes to openEO error codes
        code_map = {
            400: "BadRequest",
            401: "AuthenticationRequired",
            403: "AuthenticationScopeMissing",
            404: "NotFound",
            409: "Conflict",
            422: "ValidationError",
            429: "TooManyRequests",
            500: "Internal",
            503: "ServiceUnavailable",
        }
        code = code_map.get(exc.status_code, "HttpError")
        if exc.status_code >= 500:
            logger.error(
                "http error",
                status_code=exc.status_code,
                detail=exc.detail,
                path=request.url.path,
            )
        else:
            logger.debug(
                "http error",
                status_code=exc.status_code,
                detail=exc.detail,
                path=request.url.path,
            )
        return JSONResponse(
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
            content=_error_body(
                code=code,
                message=str(exc.detail),
                request=request,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "unhandled exception",
            path=request.url.path,
            exc_type=type(exc).__name__,
            traceback=traceback.format_exc(),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                code="Internal",
                message="An unexpected error occurred. Please try again later.",
                request=request,
            ),
        )
