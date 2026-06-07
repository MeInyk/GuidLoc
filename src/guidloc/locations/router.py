"""HTTP routes for locations."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.dependencies import get_current_user
from guidloc.common.database import get_session
from guidloc.locations.models import (
    Location,
    LocationCategory,
    LocationChangeRequest,
    LocationChangeRequestStatus,
    PriceLevel,
)
from guidloc.locations.schemas import (
    LocationChangeRequestAmend,
    LocationChangeRequestCreate,
    LocationChangeRequestMergeRequest,
    LocationChangeRequestMergeResult,
    LocationChangeRequestRead,
    LocationListItem,
    LocationRead,
)
from guidloc.locations.service import (
    LocationChangeRequestConflictError,
    LocationChangeRequestNotFoundError,
    StaleLocationChangeRequestError,
    amend_location_change_request,
    cancel_location_change_request,
    create_location_change_request,
    get_location,
    get_location_change_request,
    list_location_change_requests,
    list_locations,
    merge_location_change_request,
)
from guidloc.users.models import User

router = APIRouter(prefix="/locations", tags=["locations"])
change_requests_router = APIRouter(
    prefix="/location-change-requests",
    tags=["location-change-requests"],
)
my_change_requests_router = APIRouter(
    prefix="/users/me/location-change-requests",
    tags=["location-change-requests"],
)


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


@my_change_requests_router.get(
    "",
    response_model=list[LocationChangeRequestRead],
    summary="List the current user's location change requests",
)
async def list_my_change_requests(
    status_filter: LocationChangeRequestStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[LocationChangeRequest]:
    return await list_location_change_requests(
        session,
        created_by_user_id=current_user.id,
        status=status_filter,
    )


@my_change_requests_router.patch(
    "/{request_id}",
    response_model=LocationChangeRequestRead,
    summary="Amend one of the current user's pending location change requests",
)
async def amend_my_change_request(
    request_id: int,
    payload: LocationChangeRequestAmend,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LocationChangeRequest:
    try:
        return await amend_location_change_request(session, current_user.id, request_id, payload)
    except LocationChangeRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocationChangeRequestConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@my_change_requests_router.post(
    "/{request_id}/cancel",
    response_model=LocationChangeRequestRead,
    summary="Cancel one of the current user's pending location change requests",
)
async def cancel_my_change_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LocationChangeRequest:
    try:
        return await cancel_location_change_request(session, current_user.id, request_id)
    except LocationChangeRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except LocationChangeRequestConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@change_requests_router.post(
    "",
    response_model=LocationChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pending location change request",
)
async def create_change_request(
    payload: LocationChangeRequestCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LocationChangeRequest:
    try:
        return await create_location_change_request(session, current_user.id, payload)
    except LocationChangeRequestNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@change_requests_router.get(
    "",
    response_model=list[LocationChangeRequestRead],
    summary="List location change requests",
)
async def list_change_requests(
    status_filter: LocationChangeRequestStatus | None = Query(default=None, alias="status"),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[LocationChangeRequest]:
    return await list_location_change_requests(session, status=status_filter)


@change_requests_router.get(
    "/{request_id}",
    response_model=LocationChangeRequestRead,
    summary="Get a location change request",
)
async def read_change_request(
    request_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LocationChangeRequest:
    request = await get_location_change_request(session, request_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location change request not found",
        )
    return request


@change_requests_router.post(
    "/{request_id}/merge",
    response_model=LocationChangeRequestMergeResult,
    summary="Apply a pending location change request",
)
async def merge_change_request(
    request_id: int,
    payload: LocationChangeRequestMergeRequest | None = None,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> LocationChangeRequestMergeResult:
    request = await get_location_change_request(session, request_id)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Location change request not found",
        )

    try:
        merged_request, location = await merge_location_change_request(
            session,
            request,
            merged_by_user_id=current_user.id,
            force=payload.force if payload else False,
        )
    except LocationChangeRequestNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (LocationChangeRequestConflictError, StaleLocationChangeRequestError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return LocationChangeRequestMergeResult(
        change_request=LocationChangeRequestRead.model_validate(merged_request),
        location=LocationRead.model_validate(location),
    )
