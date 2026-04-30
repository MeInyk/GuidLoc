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
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from guidloc.auth import models as _refresh_token_models  # noqa: F401
from guidloc.chats import models as _chats_models  # noqa: F401
from guidloc.common.database import Base, get_session
from guidloc.main import app

# Import all model modules so that metadata is fully populated before create_all.
from guidloc.users import models as _users_models  # noqa: F401


@pytest_asyncio.fixture(scope="session")
async def test_engine() -> AsyncIterator[AsyncEngine]:
    """Single shared in-memory SQLite engine for the test session."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_database(test_engine: AsyncEngine) -> AsyncIterator[None]:
    """Reset the schema before every test to ensure isolation.

    Tests (and endpoints they exercise) commit data to the shared in-memory
    database, so a simple session.rollback() is not enough. Dropping and
    recreating all tables guarantees a clean state per test.
    """
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest_asyncio.fixture
async def db_session(test_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Provide an AsyncSession that rolls back after each test."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


@pytest_asyncio.fixture
async def client(test_engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """HTTP client wired to the FastAPI app with test DB session override."""
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
