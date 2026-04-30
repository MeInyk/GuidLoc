"""HTTP routes for locations."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.common.database import get_session
from guidloc.locations.models import Location, LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationListItem, LocationRead
from guidloc.locations.service import get_location, list_locations

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get(
    "",
    response_model=list[LocationListItem],
    summary="List active locations with optional filters",
)
async def list_locations_endpoint(
    category: list[LocationCategory] | None = Query(default=None),
    price_level: list[PriceLevel] | None = Query(default=None),
    tag: list[str] | None = Query(default=None, description="All requested tags must match"),
    q: str | None = Query(default=None, description="Search in name and description"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[Location]:
    return await list_locations(
        session,
        categories=category,
        price_levels=price_level,
        tags=tag,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{location_id}",
    response_model=LocationRead,
    summary="Get a location by id",
)
async def read_location(
    location_id: int,
    session: AsyncSession = Depends(get_session),
) -> Location:
    location = await get_location(session, location_id)
    if location is None or not location.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Location not found")
    return location
