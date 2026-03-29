"""
Readiness and liveness probes.

``GET /health``    – liveness: always 200 if the process is alive.
``GET /ready``     – readiness: checks Elasticsearch + Keycloak reachability.

The readiness probe is used by Kubernetes / Docker to decide whether traffic
should be routed to this instance.  It checks:

1. Elasticsearch cluster health (green or yellow is OK; red or unreachable is not).
2. Keycloak JWKS endpoint reachability (HTTP 200 expected).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog
from elasticsearch import AsyncElasticsearch
from fastapi import APIRouter, Depends, Response, status

from openeo_workspace_service.config.settings import Settings, get_settings
from openeo_workspace_service.db.elasticsearch import get_es

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Health"])


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


async def _check_elasticsearch(es: AsyncElasticsearch) -> dict[str, Any]:
    try:
        health = await asyncio.wait_for(es.cluster.health(timeout="3s"), timeout=5.0)
        cluster_status = health.get("status", "unknown")
        ok = cluster_status in ("green", "yellow")
        return {"ok": ok, "status": cluster_status}
    except Exception as exc:
        logger.warning("elasticsearch health check failed", error=str(exc))
        return {"ok": False, "error": str(exc)}


async def _check_keycloak(settings: Settings) -> dict[str, Any]:
    url = settings.oidc_jwks_uri
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
            ok = resp.status_code == 200
            return {"ok": ok, "http_status": resp.status_code}
    except Exception as exc:
        logger.warning("keycloak health check failed", error=str(exc))
        return {"ok": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get(
    "/health",
    summary="Liveness probe",
    response_model=dict,
)
async def liveness() -> dict[str, str]:
    """Always returns 200 while the process is running."""
    return {"status": "ok"}


@router.get(
    "/ready",
    summary="Readiness probe",
    response_model=dict,
)
async def readiness(
    response: Response,
    es: AsyncElasticsearch = Depends(get_es),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Checks downstream dependencies.  Returns 200 when all checks pass,
    503 when any check fails.
    """
    es_result, kc_result = await asyncio.gather(
        _check_elasticsearch(es),
        _check_keycloak(settings),
    )

    all_ok = es_result["ok"] and kc_result["ok"]
    http_status = status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    response.status_code = http_status

    return {
        "status": "ok" if all_ok else "degraded",
        "checks": {
            "elasticsearch": es_result,
            "keycloak": kc_result,
        },
    }
