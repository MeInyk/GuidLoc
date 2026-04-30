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


async def _populate(db_session: AsyncSession) -> None:
    """Seed a small fixed dataset for filter tests."""
    items = [
        LocationCreate(
            name="Alpha Cafe",
            description="Specialty coffee and pastries",
            address="1 Alpha St",
            latitude=48.29,
            longitude=25.93,
            category=LocationCategory.CAFE,
            price_level=PriceLevel.LOW,
            tags=["wifi", "quiet"],
        ),
        LocationCreate(
            name="Beta Park",
            description="A green park with benches",
            address="2 Beta St",
            latitude=48.30,
            longitude=25.94,
            category=LocationCategory.PARK,
            price_level=PriceLevel.FREE,
            tags=["walk", "outdoor"],
        ),
        LocationCreate(
            name="Gamma Bar",
            description="Cocktails and quiet evenings",
            address="3 Gamma St",
            latitude=48.31,
            longitude=25.95,
            category=LocationCategory.BAR,
            price_level=PriceLevel.MEDIUM,
            tags=["evening", "quiet"],
        ),
        LocationCreate(
            name="Delta Restaurant",
            description="Modern Ukrainian cuisine",
            address="4 Delta St",
            latitude=48.32,
            longitude=25.96,
            category=LocationCategory.RESTAURANT,
            price_level=PriceLevel.HIGH,
            tags=["date-night", "wine"],
        ),
        LocationCreate(
            name="Echo Cafe",
            description="Quick coffee stop",
            address="5 Echo St",
            latitude=48.33,
            longitude=25.97,
            category=LocationCategory.CAFE,
            price_level=PriceLevel.LOW,
            tags=["coffee"],
        ),
    ]
    for item in items:
        await create_location(db_session, item)


async def test_filter_by_single_category(client: AsyncClient, db_session: AsyncSession) -> None:
    await _populate(db_session)

    response = await client.get("/locations", params={"category": "cafe"})

    assert response.status_code == 200
    names = [loc["name"] for loc in response.json()]
    assert names == ["Alpha Cafe", "Echo Cafe"]


async def test_filter_by_multiple_categories(client: AsyncClient, db_session: AsyncSession) -> None:
    await _populate(db_session)

    response = await client.get(
        "/locations",
        params=[("category", "cafe"), ("category", "park")],
    )

    assert response.status_code == 200
    names = sorted(loc["name"] for loc in response.json())
    assert names == ["Alpha Cafe", "Beta Park", "Echo Cafe"]


async def test_filter_by_price_level(client: AsyncClient, db_session: AsyncSession) -> None:
    await _populate(db_session)

    response = await client.get("/locations", params={"price_level": "free"})

    assert response.status_code == 200
    names = [loc["name"] for loc in response.json()]
    assert names == ["Beta Park"]


async def test_search_query_matches_name_or_description(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _populate(db_session)

    response = await client.get("/locations", params={"q": "coffee"})

    assert response.status_code == 200
    names = sorted(loc["name"] for loc in response.json())
    # "Specialty coffee" in description, "Quick coffee stop" in description
    assert names == ["Alpha Cafe", "Echo Cafe"]


async def test_search_query_is_case_insensitive(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _populate(db_session)

    response = await client.get("/locations", params={"q": "GAMMA"})

    assert response.status_code == 200
    names = [loc["name"] for loc in response.json()]
    assert names == ["Gamma Bar"]


async def test_filter_by_tag_requires_all_tags(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _populate(db_session)

    response = await client.get(
        "/locations",
        params=[("tag", "quiet")],
    )

    assert response.status_code == 200
    names = sorted(loc["name"] for loc in response.json())
    assert names == ["Alpha Cafe", "Gamma Bar"]


async def test_filter_by_multiple_tags_uses_and(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await _populate(db_session)

    response = await client.get(
        "/locations",
        params=[("tag", "quiet"), ("tag", "wifi")],
    )

    assert response.status_code == 200
    names = [loc["name"] for loc in response.json()]
    assert names == ["Alpha Cafe"]


async def test_combined_filters(client: AsyncClient, db_session: AsyncSession) -> None:
    await _populate(db_session)

    response = await client.get(
        "/locations",
        params=[
            ("category", "cafe"),
            ("price_level", "low"),
            ("q", "coffee"),
        ],
    )

    assert response.status_code == 200
    names = sorted(loc["name"] for loc in response.json())
    assert names == ["Alpha Cafe", "Echo Cafe"]


async def test_pagination_limit(client: AsyncClient, db_session: AsyncSession) -> None:
    await _populate(db_session)

    response = await client.get("/locations", params={"limit": 2})

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_pagination_offset(client: AsyncClient, db_session: AsyncSession) -> None:
    await _populate(db_session)

    first_page = (await client.get("/locations", params={"limit": 2, "offset": 0})).json()
    second_page = (await client.get("/locations", params={"limit": 2, "offset": 2})).json()

    assert len(first_page) == 2
    assert len(second_page) == 2
    first_ids = {loc["id"] for loc in first_page}
    second_ids = {loc["id"] for loc in second_page}
    assert first_ids.isdisjoint(second_ids)


async def test_invalid_category_returns_422(client: AsyncClient) -> None:
    response = await client.get("/locations", params={"category": "spaceship"})

    assert response.status_code == 422


async def test_limit_validation(client: AsyncClient) -> None:
    too_high = await client.get("/locations", params={"limit": 9999})
    too_low = await client.get("/locations", params={"limit": 0})

    assert too_high.status_code == 422
    assert too_low.status_code == 422
