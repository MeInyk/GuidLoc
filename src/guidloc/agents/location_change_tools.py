"""Tools for user-submitted location change requests."""

import json
import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from agents import RunContextWrapper, function_tool
from guidloc.agents.base import AgentContext
from guidloc.locations.models import (
    LocationChangeRequest,
    LocationChangeRequestStatus,
    LocationChangeRequestType,
)
from guidloc.locations.schemas import (
    REQUIRED_CREATE_CHANGE_FIELDS,
    LocationChangeRequestAmend,
    LocationChangeRequestCreate,
    LocationProposalFields,
)
from guidloc.locations.service import (
    LocationChangeRequestConflictError,
    LocationChangeRequestNotFoundError,
    create_location_change_request,
    find_locations_for_change,
    list_location_change_requests,
)
from guidloc.locations.service import (
    amend_location_change_request as amend_location_change_request_record,
)
from guidloc.locations.service import (
    cancel_location_change_request as cancel_location_change_request_record,
)

logger = logging.getLogger("guidloc.agents.tools")


def _provided_location_changes(
    *,
    name: str | None,
    description: str | None,
    address: str | None,
    latitude: float | None,
    longitude: float | None,
    category: str | None,
    price_level: str | None,
    tags: list[str] | None,
    is_active: bool | None,
) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    values = {
        "name": name,
        "description": description,
        "address": address,
        "latitude": latitude,
        "longitude": longitude,
        "category": category,
        "price_level": price_level,
        "tags": tags,
        "is_active": is_active,
    }
    for field, value in values.items():
        if value is not None:
            changes[field] = value
    return changes


def _format_candidates(candidates) -> str:
    lines = [
        f"id={loc.id} name={loc.name!r} address={loc.address or 'no address'}" for loc in candidates
    ]
    return "; ".join(lines)


def _parse_status(status: str | None) -> LocationChangeRequestStatus | None:
    if not status:
        return None
    return LocationChangeRequestStatus(status.lower())


def _format_change_request(request: LocationChangeRequest) -> str:
    target = (
        f"location_id={request.location_id}" if request.location_id is not None else "new location"
    )
    changes = json.dumps(request.proposed_changes or {}, ensure_ascii=False, sort_keys=True)
    return (
        f"- id={request.id} type={request.change_type.value} status={request.status.value} "
        f"target={target} reason={request.reason!r} changes={changes}"
    )


async def _resolve_location_id(
    session: AsyncSession,
    *,
    location_id: int | None,
    location_name: str | None,
) -> tuple[int | None, str | None]:
    if location_id is not None:
        return location_id, None

    if not location_name:
        return None, "For an update, provide location_id or location_name."

    candidates = await find_locations_for_change(session, location_name)
    if not candidates:
        return (
            None,
            f"No existing location found for {location_name!r}. Ask whether this is a new place.",
        )
    if len(candidates) > 1:
        return (
            None,
            "Multiple matching locations found. Ask the user which one they mean: "
            f"{_format_candidates(candidates)}.",
        )
    return candidates[0].id, None


async def propose_location_change_impl(
    session: AsyncSession,
    user_id: int,
    *,
    change_type: str,
    reason: str,
    location_id: int | None = None,
    location_name: str | None = None,
    name: str | None = None,
    description: str | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    category: str | None = None,
    price_level: str | None = None,
    tags: list[str] | None = None,
    is_active: bool | None = None,
) -> str:
    """Plain implementation used by the OpenAI tool and direct tests."""
    try:
        change_type_enum = LocationChangeRequestType(change_type.lower())
    except ValueError:
        allowed = ", ".join(t.value for t in LocationChangeRequestType)
        return f"Unknown change_type '{change_type}'. Allowed: {allowed}."

    changes = _provided_location_changes(
        name=name,
        description=description,
        address=address,
        latitude=latitude,
        longitude=longitude,
        category=category,
        price_level=price_level,
        tags=tags,
        is_active=is_active,
    )

    if change_type_enum is LocationChangeRequestType.CREATE:
        missing = sorted(REQUIRED_CREATE_CHANGE_FIELDS - set(changes))
        if missing:
            return "Missing required fields for new location: " + ", ".join(missing) + "."

    if change_type_enum is LocationChangeRequestType.UPDATE:
        resolved_id, error = await _resolve_location_id(
            session,
            location_id=location_id,
            location_name=location_name,
        )
        if error:
            return error
        location_id = resolved_id

    try:
        payload = LocationChangeRequestCreate(
            change_type=change_type_enum,
            location_id=location_id,
            reason=reason,
            proposed_changes=LocationProposalFields.model_validate(changes),
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        return f"Could not create location change request: {first.get('msg', str(exc))}."

    try:
        request = await create_location_change_request(session, user_id, payload)
    except LocationChangeRequestNotFoundError as exc:
        return str(exc)

    target = f" location_id={request.location_id}" if request.location_id else ""
    return (
        f"Created location change request id={request.id} "
        f"type={request.change_type.value}{target} status={request.status.value}."
    )


async def read_my_location_change_requests_impl(
    session: AsyncSession,
    user_id: int,
    *,
    status: str | None = None,
    limit: int = 10,
) -> str:
    """Return a compact list of the current user's submitted requests."""
    try:
        status_enum = _parse_status(status)
    except ValueError:
        allowed = ", ".join(s.value for s in LocationChangeRequestStatus)
        return f"Unknown status '{status}'. Allowed: {allowed}."

    bounded_limit = max(1, min(limit, 20))
    requests = await list_location_change_requests(
        session,
        created_by_user_id=user_id,
        status=status_enum,
    )
    requests = requests[:bounded_limit]

    if not requests:
        qualifier = f" with status={status_enum.value}" if status_enum else ""
        return f"No location change requests found{qualifier}."

    lines = [_format_change_request(request) for request in requests]
    return "\n".join(lines)


async def amend_location_change_request_impl(
    session: AsyncSession,
    user_id: int,
    *,
    request_id: int,
    reason: str | None = None,
    name: str | None = None,
    description: str | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    category: str | None = None,
    price_level: str | None = None,
    tags: list[str] | None = None,
    is_active: bool | None = None,
) -> str:
    """Merge extra fields into one of the user's pending requests."""
    changes = _provided_location_changes(
        name=name,
        description=description,
        address=address,
        latitude=latitude,
        longitude=longitude,
        category=category,
        price_level=price_level,
        tags=tags,
        is_active=is_active,
    )

    try:
        payload = LocationChangeRequestAmend(
            reason=reason,
            proposed_changes=LocationProposalFields.model_validate(changes),
        )
    except ValidationError as exc:
        first = exc.errors()[0]
        return f"Could not amend location change request: {first.get('msg', str(exc))}."

    try:
        request = await amend_location_change_request_record(session, user_id, request_id, payload)
    except LocationChangeRequestNotFoundError as exc:
        return str(exc)
    except LocationChangeRequestConflictError as exc:
        return str(exc)
    except ValidationError as exc:
        first = exc.errors()[0]
        return f"Could not amend location change request: {first.get('msg', str(exc))}."

    return (
        f"Amended location change request id={request.id} "
        f"type={request.change_type.value} status={request.status.value}."
    )


async def cancel_location_change_request_impl(
    session: AsyncSession,
    user_id: int,
    *,
    request_id: int,
) -> str:
    """Cancel one of the user's pending requests."""
    try:
        request = await cancel_location_change_request_record(session, user_id, request_id)
    except LocationChangeRequestNotFoundError as exc:
        return str(exc)
    except LocationChangeRequestConflictError as exc:
        return str(exc)

    return f"Cancelled location change request id={request.id} status={request.status.value}."


@function_tool
async def propose_location_change(
    ctx: RunContextWrapper[AgentContext],
    change_type: str,
    reason: str,
    location_id: int | None = None,
    location_name: str | None = None,
    name: str | None = None,
    description: str | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    category: str | None = None,
    price_level: str | None = None,
    tags: list[str] | None = None,
    is_active: bool | None = None,
) -> str:
    """Create a pending request for admins to add or update a location.

    Use this ONLY after the user explicitly wants to report/add/change a
    location, or after they confirmed they want to notify admins about wrong
    location data.

    change_type:
    - "create" for a new place. Required fields: name, address, latitude,
      longitude, category. Optional: description, price_level, tags, is_active.
    - "update" for an existing place. Provide location_id if known; otherwise
      provide location_name and this tool will try to resolve it. Include only
      the fields the user says changed. For a closed place, pass is_active=false.

    Supported fields are only: name, description, address, latitude, longitude,
    category, price_level, tags, is_active. This tool does not accept photos,
    images, menus, opening hours, phone numbers, websites or social links.

    Always include reason: the user's short explanation of why they proposed
    this change. This tool only creates a review request; it never updates the
    public locations database directly.
    """
    logger.info(
        "tool=propose_location_change user_id=%s change_type=%s location_id=%s location_name=%r",
        ctx.context.user_id,
        change_type,
        location_id,
        location_name,
    )
    async with ctx.context.db_lock:
        result = await propose_location_change_impl(
            ctx.context.session,
            ctx.context.user_id,
            change_type=change_type,
            reason=reason,
            location_id=location_id,
            location_name=location_name,
            name=name,
            description=description,
            address=address,
            latitude=latitude,
            longitude=longitude,
            category=category,
            price_level=price_level,
            tags=tags,
            is_active=is_active,
        )
    logger.info("tool=propose_location_change result=%r", result)
    return result


@function_tool
async def read_my_location_change_requests(
    ctx: RunContextWrapper[AgentContext],
    status: str | None = None,
    limit: int = 10,
) -> str:
    """Read location change requests submitted by the current user.

    Use when the user asks to see/check their own submitted location requests,
    or before amending/cancelling when you need to verify request id/status.

    Optional status filter: pending, merged, rejected, cancelled.
    Returns compact lines with request id, type, status, target, reason and
    proposed changes. This tool never returns other users' requests.
    """
    logger.info(
        "tool=read_my_location_change_requests user_id=%s status=%s limit=%s",
        ctx.context.user_id,
        status,
        limit,
    )
    async with ctx.context.db_lock:
        result = await read_my_location_change_requests_impl(
            ctx.context.session,
            ctx.context.user_id,
            status=status,
            limit=limit,
        )
    logger.info("tool=read_my_location_change_requests result=%r", result[:200])
    return result


@function_tool
async def amend_location_change_request(
    ctx: RunContextWrapper[AgentContext],
    request_id: int,
    reason: str | None = None,
    name: str | None = None,
    description: str | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    category: str | None = None,
    price_level: str | None = None,
    tags: list[str] | None = None,
    is_active: bool | None = None,
) -> str:
    """Add or correct fields on the current user's existing pending request.

    Use this for follow-up messages like "рівень ціни високий" after you
    already created a request and have its request_id. IMPORTANT: request_id is
    the location-change request id, not a real location_id. This tool can amend
    only the current user's pending requests.

    Supported fields are only: name, description, address, latitude, longitude,
    category, price_level, tags, is_active. It does not accept photos/images or
    other unsupported fields.
    """
    logger.info(
        "tool=amend_location_change_request user_id=%s request_id=%s",
        ctx.context.user_id,
        request_id,
    )
    async with ctx.context.db_lock:
        result = await amend_location_change_request_impl(
            ctx.context.session,
            ctx.context.user_id,
            request_id=request_id,
            reason=reason,
            name=name,
            description=description,
            address=address,
            latitude=latitude,
            longitude=longitude,
            category=category,
            price_level=price_level,
            tags=tags,
            is_active=is_active,
        )
    logger.info("tool=amend_location_change_request result=%r", result)
    return result


@function_tool
async def cancel_location_change_request(
    ctx: RunContextWrapper[AgentContext],
    request_id: int,
) -> str:
    """Cancel one of the current user's pending location change requests.

    Use only when the user says they made a mistake, changed their mind, or
    explicitly asks to cancel/delete/withdraw a submitted request. If the user
    does not provide a clear request id, call read_my_location_change_requests
    first and ask which pending request they mean.
    """
    logger.info(
        "tool=cancel_location_change_request user_id=%s request_id=%s",
        ctx.context.user_id,
        request_id,
    )
    async with ctx.context.db_lock:
        result = await cancel_location_change_request_impl(
            ctx.context.session,
            ctx.context.user_id,
            request_id=request_id,
        )
    logger.info("tool=cancel_location_change_request result=%r", result)
    return result
