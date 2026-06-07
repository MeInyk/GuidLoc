"""Database operations for locations."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.locations.models import (
    Location,
    LocationCategory,
    LocationChangeRequest,
    LocationChangeRequestStatus,
    LocationChangeRequestType,
    PriceLevel,
)
from guidloc.locations.schemas import (
    LOCATION_CHANGE_FIELDS,
    LocationChangeRequestAmend,
    LocationChangeRequestCreate,
    LocationCreate,
    LocationProposalFields,
)


class LocationChangeRequestError(Exception):
    """Base exception for location change request operations."""


class LocationChangeRequestNotFoundError(LocationChangeRequestError):
    """Raised when a location or change request cannot be found."""


class LocationChangeRequestConflictError(LocationChangeRequestError):
    """Raised when a pending change cannot be safely applied."""


class StaleLocationChangeRequestError(LocationChangeRequestConflictError):
    """Raised when an update proposal was based on an older location version."""


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


def _location_snapshot(location: Location) -> dict[str, Any]:
    return {
        "id": location.id,
        "name": location.name,
        "description": location.description,
        "address": location.address,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "category": location.category.value,
        "price_level": location.price_level.value if location.price_level else None,
        "tags": list(location.tags or []),
        "is_active": location.is_active,
        "updated_at": location.updated_at.isoformat() if location.updated_at else None,
    }


def _safe_changes(data: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(data) - LOCATION_CHANGE_FIELDS)
    if unknown:
        raise LocationChangeRequestConflictError(
            f"Change request contains unsupported fields: {', '.join(unknown)}"
        )
    return dict(data)


def _location_create_from_changes(changes: dict[str, Any]) -> LocationCreate:
    data = {
        "name": changes["name"],
        "description": changes.get("description") or "",
        "address": changes["address"],
        "latitude": changes["latitude"],
        "longitude": changes["longitude"],
        "category": changes["category"],
        "price_level": changes.get("price_level"),
        "tags": changes.get("tags") or [],
        "is_active": changes.get("is_active", True),
    }
    return LocationCreate.model_validate(data)


def _coerce_update_value(field: str, value: Any) -> Any:
    if field == "category":
        return value if isinstance(value, LocationCategory) else LocationCategory(value)
    if field == "price_level":
        if value is None:
            return None
        return value if isinstance(value, PriceLevel) else PriceLevel(value)
    if field == "tags":
        return list(value or [])
    return value


async def create_location_change_request(
    session: AsyncSession,
    user_id: int,
    payload: LocationChangeRequestCreate,
) -> LocationChangeRequest:
    """Create a pending proposal without mutating the public locations table."""
    original_snapshot = None
    original_updated_at = None

    if payload.change_type is LocationChangeRequestType.UPDATE:
        location = await get_location(session, payload.location_id or 0)
        if location is None:
            raise LocationChangeRequestNotFoundError("Location not found")
        original_snapshot = _location_snapshot(location)
        original_updated_at = location.updated_at

    request = LocationChangeRequest(
        created_by_user_id=user_id,
        location_id=payload.location_id,
        change_type=payload.change_type,
        status=LocationChangeRequestStatus.PENDING,
        reason=payload.reason,
        proposed_changes=payload.proposed_changes.to_changes(),
        original_snapshot=original_snapshot,
        original_location_updated_at=original_updated_at,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def get_location_change_request(
    session: AsyncSession,
    request_id: int,
) -> LocationChangeRequest | None:
    """Return a location change request by primary key."""
    return await session.get(LocationChangeRequest, request_id)


async def get_user_location_change_request(
    session: AsyncSession,
    user_id: int,
    request_id: int,
) -> LocationChangeRequest | None:
    """Return a change request only if it belongs to the given user."""
    result = await session.execute(
        select(LocationChangeRequest).where(
            LocationChangeRequest.id == request_id,
            LocationChangeRequest.created_by_user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_location_change_requests(
    session: AsyncSession,
    *,
    created_by_user_id: int | None = None,
    status: LocationChangeRequestStatus | None = None,
) -> list[LocationChangeRequest]:
    """List location change requests for review/debug views."""
    stmt = select(LocationChangeRequest).order_by(LocationChangeRequest.id.desc())
    if created_by_user_id is not None:
        stmt = stmt.where(LocationChangeRequest.created_by_user_id == created_by_user_id)
    if status is not None:
        stmt = stmt.where(LocationChangeRequest.status == status)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def amend_location_change_request(
    session: AsyncSession,
    user_id: int,
    request_id: int,
    payload: LocationChangeRequestAmend,
) -> LocationChangeRequest:
    """Merge extra fields into a user's pending change request."""
    request = await get_user_location_change_request(session, user_id, request_id)
    if request is None:
        raise LocationChangeRequestNotFoundError("Location change request not found")
    if request.status is not LocationChangeRequestStatus.PENDING:
        raise LocationChangeRequestConflictError("Only pending change requests can be amended")

    current_changes = dict(request.proposed_changes or {})
    current_changes.update(payload.proposed_changes.to_changes())

    # Re-validate the full request shape after merging partial changes.
    validated = LocationChangeRequestCreate(
        change_type=request.change_type,
        location_id=request.location_id,
        reason=payload.reason or request.reason,
        proposed_changes=LocationProposalFields.model_validate(current_changes),
    )

    request.reason = validated.reason
    request.proposed_changes = validated.proposed_changes.to_changes()
    await session.commit()
    await session.refresh(request)
    return request


async def cancel_location_change_request(
    session: AsyncSession,
    user_id: int,
    request_id: int,
) -> LocationChangeRequest:
    """Cancel a user's pending change request."""
    request = await get_user_location_change_request(session, user_id, request_id)
    if request is None:
        raise LocationChangeRequestNotFoundError("Location change request not found")
    if request.status is not LocationChangeRequestStatus.PENDING:
        raise LocationChangeRequestConflictError("Only pending change requests can be cancelled")

    request.status = LocationChangeRequestStatus.CANCELLED
    await session.commit()
    await session.refresh(request)
    return request


async def find_locations_for_change(
    session: AsyncSession,
    name: str,
    *,
    limit: int = 5,
) -> list[Location]:
    """Find candidate locations by exact name first, then substring search."""
    normalized = name.strip().lower()
    if not normalized:
        return []

    exact = await session.execute(
        select(Location)
        .where(func.lower(Location.name) == normalized)
        .order_by(Location.is_active.desc(), Location.name.asc())
        .limit(limit)
    )
    exact_rows = list(exact.scalars().all())
    if exact_rows:
        return exact_rows

    like = f"%{normalized}%"
    result = await session.execute(
        select(Location)
        .where(func.lower(Location.name).like(like))
        .order_by(Location.is_active.desc(), Location.name.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _find_duplicate_location(
    session: AsyncSession,
    payload: LocationCreate,
) -> Location | None:
    result = await session.execute(
        select(Location).where(
            func.lower(Location.name) == payload.name.lower(),
        )
    )
    candidates = list(result.scalars().all())
    for candidate in candidates:
        if round(candidate.latitude, 6) == round(payload.latitude, 6) and round(
            candidate.longitude, 6
        ) == round(payload.longitude, 6):
            return candidate
    return None


async def merge_location_change_request(
    session: AsyncSession,
    request: LocationChangeRequest,
    *,
    merged_by_user_id: int,
    force: bool = False,
) -> tuple[LocationChangeRequest, Location]:
    """Apply a pending request to `locations` and mark it as merged.

    Merge semantics:
    - create: validate the stored payload and insert one new Location;
    - update: apply only the whitelisted fields present in `proposed_changes`;
    - stale update protection: if the target location changed since the
      proposal was captured, require force=True before applying.
    """
    if request.status is not LocationChangeRequestStatus.PENDING:
        raise LocationChangeRequestConflictError("Only pending change requests can be merged")

    changes = _safe_changes(request.proposed_changes or {})
    if not changes:
        raise LocationChangeRequestConflictError("Change request has no proposed changes")

    if request.change_type is LocationChangeRequestType.CREATE:
        payload = _location_create_from_changes(changes)
        duplicate = await _find_duplicate_location(session, payload)
        if duplicate is not None and not force:
            raise LocationChangeRequestConflictError(
                f"Location already exists with id={duplicate.id}; use force=true to merge anyway"
            )
        location = Location(**payload.model_dump())
        session.add(location)
        await session.flush()

    else:
        if request.location_id is None:
            raise LocationChangeRequestConflictError("Update request has no location_id")
        location = await get_location(session, request.location_id)
        if location is None:
            raise LocationChangeRequestNotFoundError("Location not found")

        if (
            request.original_location_updated_at is not None
            and location.updated_at != request.original_location_updated_at
            and not force
        ):
            raise StaleLocationChangeRequestError(
                "Location changed after this request was created; use force=true to merge anyway"
            )

        for field, value in changes.items():
            setattr(location, field, _coerce_update_value(field, value))
        location.updated_at = datetime.now(UTC)
        await session.flush()

    request.status = LocationChangeRequestStatus.MERGED
    request.merged_location_id = location.id
    request.merged_by_user_id = merged_by_user_id
    request.merged_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(request)
    await session.refresh(location)
    return request, location
