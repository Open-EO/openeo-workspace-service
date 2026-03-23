"""
openeo_workspace_service/db/session.py
----------------------------------------
Async SQLAlchemy engine + session factory.
Call ``init_db()`` once at application startup.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from openeo_workspace_service.config import settings
from openeo_workspace_service.db.models import Base

_engine = create_async_engine(settings.database_url, echo=False)
_async_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables (idempotent – safe to call every startup)."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an ``AsyncSession``."""
    async with _async_session_factory() as session:
        yield session
