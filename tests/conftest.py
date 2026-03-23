"""
tests/conftest.py
-----------------
Shared fixtures for the test suite.

Uses an in-memory SQLite database so tests run without any external services.
Provider calls are monkeypatched so no real cloud credentials are required.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from openeo_workspace_service.db.models import Base
from openeo_workspace_service.db.session import get_session
from openeo_workspace_service.main import create_app

# ── In-memory async SQLite engine ────────────────────────────────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

_test_engine = create_async_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
_test_session_factory = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def session() -> AsyncSession:
    async with _test_session_factory() as s:
        yield s


# ── FastAPI test client ───────────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def client(session: AsyncSession):
    """Return an AsyncClient wired to the test app with the test DB session."""
    app = create_app()

    async def _override_session():
        yield session

    app.dependency_overrides[get_session] = _override_session

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ── Auth override ─────────────────────────────────────────────────────────────

@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Return Bearer headers.  Auth is bypassed via the dev-mode token-as-user-id."""
    return {"Authorization": "Bearer testuser"}
