"""
OpenAPI metadata – tags, security schemes, and external docs.

Import and apply ``configure_openapi(app)`` from the app factory so the
generated ``/openapi.json`` is fully spec-compliant and shows correct
security requirements in Swagger UI.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

TAGS_METADATA = [
    {
        "name": "Workspaces",
        "description": (
            "Management of user workspaces. All endpoints require a valid Bearer token issued by Keycloak."
        ),
        "externalDocs": {
            "description": "openEO Workspaces Extension spec",
            "url": "https://github.com/Open-EO/openeo-api/blob/master/extensions/workspaces/README.md",
        },
    },
    {
        "name": "Admin",
        "description": (
            "Privileged operations requiring the ``workspace-admin`` Keycloak realm role. "
            "These endpoints allow administrators to manage workspaces across all users."
        ),
    },
    {
        "name": "Internal",
        "description": (
            "Internal endpoints for back-end provisioning workers. "
            "Secured via a shared ``X-Internal-API-Key`` header rather than Keycloak."
        ),
    },
    {
        "name": "Health",
        "description": "Liveness and readiness probes for Kubernetes / Docker health checks.",
    },
]


def custom_openapi(app: FastAPI):  # type: ignore[return]
    """
    Build a custom OpenAPI schema that:
    - Adds the Bearer / OIDC security scheme.
    - Marks all non-health routes as requiring authentication.
    - Includes rich tag descriptions.
    """
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=TAGS_METADATA,
    )

    # Security schemes
    schema.setdefault("components", {}).setdefault("securitySchemes", {})
    schema["components"]["securitySchemes"]["BearerAuth"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Keycloak-issued JWT access token. "
            "Obtain via the Keycloak token endpoint: "
            "`POST /realms/{realm}/protocol/openid-connect/token`"
        ),
    }
    schema["components"]["securitySchemes"]["InternalApiKey"] = {
        "type": "apiKey",
        "in": "header",
        "name": "X-Internal-API-Key",
        "description": "Shared secret for internal provisioning endpoints.",
    }

    # Apply Bearer to every path that isn't /health or /ready
    unprotected = {"/health", "/ready", "/workspace_providers"}
    for path, path_item in schema.get("paths", {}).items():
        if path in unprotected:
            continue
        for method_item in path_item.values():
            if not isinstance(method_item, dict):
                continue
            if path.startswith("/internal"):
                method_item.setdefault("security", [{"InternalApiKey": []}])
            else:
                method_item.setdefault("security", [{"BearerAuth": []}])

    # External docs
    schema["externalDocs"] = {
        "description": "openEO API specification",
        "url": "https://openeo.org/documentation/1.0/developers/api/reference.html",
    }

    app.openapi_schema = schema
    return app.openapi_schema


def configure_openapi(app: FastAPI) -> None:
    """Attach the custom OpenAPI schema generator to *app*."""
    app.openapi = lambda: custom_openapi(app)  # type: ignore[method-assign]
