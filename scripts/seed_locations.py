"""Seed the database with a starter set of Chernivtsi locations.

Idempotent: locations are matched by name and skipped if they already exist.

Usage:
    uv run python -m scripts.seed_locations
"""

import asyncio
import logging

from guidloc.common.database import async_session_factory
from guidloc.common.logging import setup_logging
from guidloc.locations.models import LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationCreate
from guidloc.locations.service import create_location, get_location_by_name

logger = logging.getLogger(__name__)


SEED_LOCATIONS: list[LocationCreate] = [
    LocationCreate(
        name="Chernivtsi National University",
        description=(
            "A UNESCO World Heritage Site, the former Residence of Bukovinian "
            "and Dalmatian Metropolitans. Stunning red-brick architecture and "
            "landscaped courtyards."
        ),
        address="2 Kotsiubynskoho St, Chernivtsi",
        latitude=48.299444,
        longitude=25.924722,
        category=LocationCategory.ATTRACTION,
        price_level=PriceLevel.LOW,
        tags=["unesco", "architecture", "must-see", "photography"],
    ),
    LocationCreate(
        name="Olha Kobylianska Street",
        description=(
            "The pedestrian heart of Chernivtsi: cobblestones, cafes, "
            "Austro-Hungarian facades and street musicians on weekends."
        ),
        address="Olha Kobylianska St, Chernivtsi",
        latitude=48.291,
        longitude=25.935,
        category=LocationCategory.ATTRACTION,
        price_level=PriceLevel.FREE,
        tags=["walk", "central", "evening", "cafes"],
    ),
    LocationCreate(
        name="Central Square",
        description=(
            "The main square with the City Hall, fountains and the daily "
            "midday trumpeter performance from the tower."
        ),
        address="Tsentralna Square, Chernivtsi",
        latitude=48.292,
        longitude=25.934,
        category=LocationCategory.ATTRACTION,
        price_level=PriceLevel.FREE,
        tags=["central", "landmark", "family-friendly"],
    ),
    LocationCreate(
        name="Veterynarna Coffee",
        description=(
            "A cozy specialty coffee shop popular with students and "
            "freelancers. Known for filter coffee and homemade pastries."
        ),
        address="Holovna St, Chernivtsi",
        latitude=48.293,
        longitude=25.937,
        category=LocationCategory.CAFE,
        price_level=PriceLevel.LOW,
        tags=["coffee", "specialty", "wifi", "quiet"],
    ),
    LocationCreate(
        name="Reflection Restaurant",
        description=(
            "Modern Ukrainian cuisine with a refined wine list. Good choice "
            "for a date or special occasion."
        ),
        address="Holovna St, Chernivtsi",
        latitude=48.294,
        longitude=25.938,
        category=LocationCategory.RESTAURANT,
        price_level=PriceLevel.HIGH,
        tags=["date-night", "ukrainian-cuisine", "wine"],
    ),
    LocationCreate(
        name="Shevchenko Park",
        description=(
            "A large public park with shaded alleys, playgrounds and a pond. "
            "Great for a walk on a sunny day."
        ),
        address="Shevchenko Park, Chernivtsi",
        latitude=48.296,
        longitude=25.928,
        category=LocationCategory.PARK,
        price_level=PriceLevel.FREE,
        tags=["walk", "family-friendly", "outdoor", "nature"],
    ),
    LocationCreate(
        name="Chernivtsi Regional Art Museum",
        description=(
            "A compact art collection housed in a historical mansion on the central square."
        ),
        address="Tsentralna Square 10, Chernivtsi",
        latitude=48.292,
        longitude=25.934,
        category=LocationCategory.MUSEUM,
        price_level=PriceLevel.LOW,
        tags=["art", "indoor", "rainy-day"],
    ),
    LocationCreate(
        name="Drunken Cherry",
        description=(
            "A small bar chain serving warm cherry liqueur. Tiny, atmospheric, "
            "perfect for a short stop."
        ),
        address="Olha Kobylianska St, Chernivtsi",
        latitude=48.291,
        longitude=25.935,
        category=LocationCategory.BAR,
        price_level=PriceLevel.LOW,
        tags=["evening", "drinks", "quick-stop"],
    ),
]


async def seed() -> None:
    setup_logging("INFO")
    inserted = 0
    skipped = 0
    async with async_session_factory() as session:
        for payload in SEED_LOCATIONS:
            existing = await get_location_by_name(session, payload.name)
            if existing is not None:
                skipped += 1
                continue
            await create_location(session, payload)
            inserted += 1
    logger.info("Seeding finished: inserted=%d, skipped=%d", inserted, skipped)


if __name__ == "__main__":
    asyncio.run(seed())
