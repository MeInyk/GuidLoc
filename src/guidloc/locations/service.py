"""Database operations for locations."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.locations.models import Location
from guidloc.locations.schemas import LocationCreate


async def list_active_locations(session: AsyncSession) -> list[Location]:
    """Return all active locations ordered by name."""
    result = await session.execute(
        select(Location).where(Location.is_active.is_(True)).order_by(Location.name.asc())
    )
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
