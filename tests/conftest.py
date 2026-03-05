"""Shared test fixtures for AI Vault."""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from ai_vault.models.base import Base


@pytest.fixture(autouse=True)
def _set_encryption_key(monkeypatch):
    """Set a test encryption key for all tests."""
    monkeypatch.setenv("AI_VAULT_ENCRYPTION_KEY", "test-key-do-not-use-in-production-1234567890")


@pytest_asyncio.fixture
async def db_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Yield an async session backed by in-memory SQLite."""
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session
