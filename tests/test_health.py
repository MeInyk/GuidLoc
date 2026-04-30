"""Tests for the health endpoint."""

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from guidloc.common.database import get_session
from guidloc.main import app


@pytest_asyncio.fixture
async def client(test_engine: AsyncEngine) -> AsyncIterator[TestClient]:
    factory = async_sessionmaker(test_engine, expire_on_commit=False, autoflush=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["env"] == "test"
    assert body["database"] == "ok"
