"""HTTP routes for locations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.common.database import get_session
from guidloc.locations.models import Location
from guidloc.locations.schemas import LocationListItem, LocationRead
from guidloc.locations.service import get_location, list_active_locations

router = APIRouter(prefix="/locations", tags=["locations"])


@router.get(
    "",
    response_model=list[LocationListItem],
    summary="List active locations",
)
async def list_locations(
    session: AsyncSession = Depends(get_session),
) -> list[Location]:
    return await list_active_locations(session)


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
