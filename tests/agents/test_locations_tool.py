"""Tests for the search_locations tool implementation."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.agents.tools import search_locations_impl
from guidloc.locations.models import LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationCreate
from guidloc.locations.service import create_location


@pytest.fixture
async def populated_db(db_session: AsyncSession) -> AsyncSession:
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
            description="Green park with benches",
            address="2 Beta St",
            latitude=48.30,
            longitude=25.94,
            category=LocationCategory.PARK,
            price_level=PriceLevel.FREE,
            tags=["walk", "outdoor"],
        ),
    ]
    for item in items:
        await create_location(db_session, item)
    return db_session


async def test_returns_no_matches_message_for_empty_db(db_session: AsyncSession) -> None:
    result = await search_locations_impl(db_session, query="anything")

    assert "no matching" in result.lower()


async def test_returns_human_readable_lines(populated_db: AsyncSession) -> None:
    result = await search_locations_impl(populated_db)

    assert "Alpha Cafe" in result
    assert "Beta Park" in result
    assert "[cafe]" in result
    assert "[park]" in result


async def test_filters_by_category(populated_db: AsyncSession) -> None:
    result = await search_locations_impl(populated_db, category="cafe")

    assert "Alpha Cafe" in result
    assert "Beta Park" not in result


async def test_invalid_category_returns_message(populated_db: AsyncSession) -> None:
    result = await search_locations_impl(populated_db, category="spaceship")

    assert "unknown category" in result.lower()


async def test_filters_by_tag(populated_db: AsyncSession) -> None:
    result = await search_locations_impl(populated_db, tag="walk")

    assert "Beta Park" in result
    assert "Alpha Cafe" not in result


async def test_query_searches_description(populated_db: AsyncSession) -> None:
    result = await search_locations_impl(populated_db, query="coffee")

    assert "Alpha Cafe" in result
    assert "Beta Park" not in result


async def test_limit_is_clamped(populated_db: AsyncSession) -> None:
    result = await search_locations_impl(populated_db, limit=999)
    # Should still succeed without error.
    assert "Alpha Cafe" in result
