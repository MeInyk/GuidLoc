"""Shared pytest fixtures and test environment setup."""

import os

# Force an isolated in-memory database for tests.
# Must be set before guidloc modules are imported anywhere.
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["APP_ENV"] = "test"
os.environ["APP_DEBUG"] = "false"

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from guidloc.common.database import Base

# Import all model modules so that metadata is fully populated before create_all.
from guidloc.users import models as _users_models  # noqa: F401


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """Create a single shared in-memory SQLite engine for the whole test session.

    StaticPool keeps one connection alive so that the in-memory database
    is shared across sessions within the same process.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession that rolls back after each test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
