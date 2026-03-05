"""SQLite async database engine and session factory."""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from ai_vault.settings import get_settings

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(url: Optional[str] = None) -> AsyncEngine:
    """Get or create the async SQLite engine."""
    global _engine
    if _engine is None:
        db_url = url or get_settings().database_url
        _engine = create_async_engine(db_url, echo=False)
    return _engine


def get_session_factory(engine: Optional[AsyncEngine] = None) -> async_sessionmaker[AsyncSession]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        eng = engine or get_engine()
        _session_factory = async_sessionmaker(eng, expire_on_commit=False)
    return _session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session (for FastAPI dependency injection)."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def init_db(engine: Optional[AsyncEngine] = None) -> None:
    """Create all tables."""
    from ai_vault.models.base import Base

    eng = engine or get_engine()
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def reset_engine() -> None:
    """Reset global engine/factory (for testing)."""
    global _engine, _session_factory
    _engine = None
    _session_factory = None
