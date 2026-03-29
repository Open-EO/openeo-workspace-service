"""
Shared pytest fixtures available to all test modules.

Fixtures here are used across both unit and integration test suites.
Per-module fixtures that are only needed in one file remain in that file.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from openeo_workspace_service.auth.keycloak import TokenClaims, get_current_user
from openeo_workspace_service.db.elasticsearch import get_es


# ---------------------------------------------------------------------------
# Stock user fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def regular_user() -> TokenClaims:
    """A standard authenticated user with the workspace-user role."""
    return TokenClaims(
        sub="regular-user-abc123",
        preferred_username="alice",
        email="alice@example.com",
        realm_access={"roles": ["workspace-user"]},
        raw={"sub": "regular-user-abc123"},
    )


@pytest.fixture
def admin_user() -> TokenClaims:
    """An authenticated user with both workspace-user and workspace-admin roles."""
    return TokenClaims(
        sub="admin-user-xyz789",
        preferred_username="admin",
        email="admin@example.com",
        realm_access={"roles": ["workspace-user", "workspace-admin"]},
        raw={"sub": "admin-user-xyz789"},
    )


# ---------------------------------------------------------------------------
# App / HTTP client fixture factory
# ---------------------------------------------------------------------------


@pytest.fixture
def make_client():
    """
    Factory fixture returning a context-managed ``AsyncClient`` with overrides.

    Usage::

        async def test_foo(make_client, regular_user):
            async with make_client(regular_user) as client:
                resp = await client.get("/workspaces")
    """
    from openeo_workspace_service.app import create_app

    def _factory(user: TokenClaims | None = None, extra_overrides: dict | None = None):
        app = create_app()
        if user is not None:
            app.dependency_overrides[get_current_user] = lambda: user
        fake_es = AsyncMock()
        app.dependency_overrides[get_es] = lambda: fake_es
        if extra_overrides:
            app.dependency_overrides.update(extra_overrides)
        return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    return _factory


# ---------------------------------------------------------------------------
# Workspace document helper
# ---------------------------------------------------------------------------


def make_workspace_doc(
    workspace_id: str = "ws-test",
    owner_id: str = "regular-user-abc123",
    status: str = "ready",
    provider_type: str = "S3",
    **extra: Any,
) -> dict[str, Any]:
    """
    Build a minimal Elasticsearch workspace document for seeding test stores.
    """
    return {
        "id": workspace_id,
        "owner_id": owner_id,
        "type": provider_type,
        "status": status,
        "title": f"Test workspace {workspace_id}",
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
        **extra,
    }
