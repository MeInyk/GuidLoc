"""Database operations for locations."""

from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.locations.models import Location, LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationCreate


async def list_locations(
    session: AsyncSession,
    *,
    categories: Sequence[LocationCategory] | None = None,
    price_levels: Sequence[PriceLevel] | None = None,
    tags: Sequence[str] | None = None,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Location]:
    """List active locations with optional filters and pagination.

    - categories: OR-match. A location matches if its category is in the set.
    - price_levels: OR-match.
    - tags: AND-match. A location must have ALL requested tags.
    - query: case-insensitive substring match on name OR description.
    """
    stmt = select(Location).where(Location.is_active.is_(True))

    if categories:
        stmt = stmt.where(Location.category.in_(categories))

    if price_levels:
        stmt = stmt.where(Location.price_level.in_(price_levels))

    if query:
        like = f"%{query.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Location.name).like(like),
                func.lower(Location.description).like(like),
            )
        )

    if tags:
        # JSON portability: load rows and filter in Python. Locations is a
        # small reference table, so this is acceptable for MVP.
        stmt = stmt.order_by(Location.name.asc())
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        required = set(tags)
        rows = [loc for loc in rows if required.issubset(set(loc.tags or []))]
        return rows[offset : offset + limit]

    stmt = stmt.order_by(Location.name.asc()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_location(session: AsyncSession, location_id: int) -> Location | None:
    """Return a single location by id, regardless of is_active."""
    return await session.get(Location, location_id)


async def get_location_by_name(session: AsyncSession, name: str) -> Location | None:
    """Return a location by name, used by the seed script for idempotency."""
    result = await session.execute(select(Location).where(Location.name == name))
    return result.scalar_one_or_none()


async def create_location(session: AsyncSession, payload: LocationCreate) -> Location:
    """Persist a new location. Used by the seed script."""
    location = Location(**payload.model_dump())
    session.add(location)
    await session.commit()
    await session.refresh(location)
    return location
