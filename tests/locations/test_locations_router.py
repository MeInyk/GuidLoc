"""End-to-end tests for the /locations endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.locations.models import LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationCreate
from guidloc.locations.service import create_location


@pytest.fixture
def sample_payload() -> LocationCreate:
    return LocationCreate(
        name="Test Cafe",
        description="A test cafe",
        address="1 Test St",
        latitude=48.29,
        longitude=25.93,
        category=LocationCategory.CAFE,
        price_level=PriceLevel.LOW,
        tags=["wifi", "quiet"],
    )


async def test_list_locations_returns_empty_initially(client: AsyncClient) -> None:
    response = await client.get("/locations")

    assert response.status_code == 200
    assert response.json() == []


async def test_list_locations_returns_active_only(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_payload: LocationCreate,
) -> None:
    active = await create_location(db_session, sample_payload)
    inactive_payload = sample_payload.model_copy(update={"name": "Hidden", "is_active": False})
    await create_location(db_session, inactive_payload)

    response = await client.get("/locations")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == active.id
    assert body[0]["name"] == "Test Cafe"


async def test_list_locations_uses_compact_schema(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_payload: LocationCreate,
) -> None:
    await create_location(db_session, sample_payload)

    response = await client.get("/locations")

    body = response.json()[0]
    assert "description" not in body
    assert "latitude" not in body
    assert set(body.keys()) == {"id", "name", "address", "category", "price_level", "tags"}


async def test_list_locations_orders_by_name(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_payload: LocationCreate,
) -> None:
    await create_location(db_session, sample_payload.model_copy(update={"name": "Beta"}))
    await create_location(db_session, sample_payload.model_copy(update={"name": "Alpha"}))
    await create_location(db_session, sample_payload.model_copy(update={"name": "Gamma"}))

    response = await client.get("/locations")

    names = [loc["name"] for loc in response.json()]
    assert names == ["Alpha", "Beta", "Gamma"]


async def test_get_location_returns_full_details(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_payload: LocationCreate,
) -> None:
    location = await create_location(db_session, sample_payload)

    response = await client.get(f"/locations/{location.id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == location.id
    assert body["description"] == "A test cafe"
    assert body["latitude"] == pytest.approx(48.29)
    assert body["longitude"] == pytest.approx(25.93)
    assert body["tags"] == ["wifi", "quiet"]


async def test_get_location_unknown_returns_404(client: AsyncClient) -> None:
    response = await client.get("/locations/999999")

    assert response.status_code == 404


async def test_get_inactive_location_returns_404(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_payload: LocationCreate,
) -> None:
    inactive = await create_location(
        db_session,
        sample_payload.model_copy(update={"is_active": False}),
    )

    response = await client.get(f"/locations/{inactive.id}")

    assert response.status_code == 404


async def test_locations_endpoints_are_public(client: AsyncClient) -> None:
    """No Authorization header is required."""
    response = await client.get("/locations")
    assert response.status_code == 200
