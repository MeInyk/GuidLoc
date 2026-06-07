"""Tests for the propose_location_change tool implementation."""

from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.agents.location_change_tools import (
    amend_location_change_request_impl,
    cancel_location_change_request_impl,
    propose_location_change_impl,
    read_my_location_change_requests_impl,
)
from guidloc.locations.models import LocationCategory, LocationChangeRequestStatus, PriceLevel
from guidloc.locations.schemas import LocationCreate
from guidloc.locations.service import create_location, list_location_change_requests
from guidloc.users.models import User


async def _make_user(session: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_tool_reports_missing_fields_for_new_location(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tool-missing@example.com")

    result = await propose_location_change_impl(
        db_session,
        user.id,
        change_type="create",
        reason="User wants to add a place",
        name="New Place",
    )

    assert "Missing required fields" in result
    assert "latitude" in result
    assert "longitude" in result


async def test_tool_creates_update_request_by_location_name(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tool-update@example.com")
    location = await create_location(
        db_session,
        LocationCreate(
            name="Alpha Cafe",
            description="Specialty coffee",
            address="1 Alpha St",
            latitude=48.29,
            longitude=25.93,
            category=LocationCategory.CAFE,
            price_level=PriceLevel.LOW,
            tags=["wifi"],
        ),
    )

    result = await propose_location_change_impl(
        db_session,
        user.id,
        change_type="update",
        reason="User says the place is closed",
        location_name="Alpha Cafe",
        is_active=False,
    )

    assert "Created location change request" in result
    requests = await list_location_change_requests(
        db_session,
        created_by_user_id=user.id,
        status=LocationChangeRequestStatus.PENDING,
    )
    assert len(requests) == 1
    assert requests[0].location_id == location.id
    assert requests[0].proposed_changes == {"is_active": False}
    assert requests[0].reason == "User says the place is closed"


async def test_tool_amends_existing_pending_request(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tool-amend@example.com")
    result = await propose_location_change_impl(
        db_session,
        user.id,
        change_type="create",
        reason="Missing place",
        name="Followup Cafe",
        address="1 Followup St",
        latitude=48.29,
        longitude=25.93,
        category="cafe",
    )
    assert "Created location change request" in result
    request = (
        await list_location_change_requests(
            db_session,
            created_by_user_id=user.id,
            status=LocationChangeRequestStatus.PENDING,
        )
    )[0]

    amend_result = await amend_location_change_request_impl(
        db_session,
        user.id,
        request_id=request.id,
        price_level="high",
        tags=["Coffee", "coffee", "quiet"],
    )

    assert f"id={request.id}" in amend_result
    requests = await list_location_change_requests(
        db_session,
        created_by_user_id=user.id,
        status=LocationChangeRequestStatus.PENDING,
    )
    assert len(requests) == 1
    assert requests[0].proposed_changes["price_level"] == "high"
    assert requests[0].proposed_changes["tags"] == ["coffee", "quiet"]


async def test_tool_reads_only_current_users_requests(db_session: AsyncSession) -> None:
    alice = await _make_user(db_session, "tool-read-alice@example.com")
    bob = await _make_user(db_session, "tool-read-bob@example.com")
    await propose_location_change_impl(
        db_session,
        alice.id,
        change_type="create",
        reason="Alice place",
        name="Alice Cafe",
        address="1 Alice St",
        latitude=48.29,
        longitude=25.93,
        category="cafe",
    )
    await propose_location_change_impl(
        db_session,
        bob.id,
        change_type="create",
        reason="Bob place",
        name="Bob Cafe",
        address="1 Bob St",
        latitude=48.3,
        longitude=25.94,
        category="cafe",
    )

    result = await read_my_location_change_requests_impl(db_session, alice.id)

    assert "Alice place" in result
    assert "Bob place" not in result


async def test_tool_cancels_pending_request(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tool-cancel@example.com")
    await propose_location_change_impl(
        db_session,
        user.id,
        change_type="create",
        reason="Mistake",
        name="Cancel Cafe",
        address="1 Cancel St",
        latitude=48.29,
        longitude=25.93,
        category="cafe",
    )
    request = (
        await list_location_change_requests(
            db_session,
            created_by_user_id=user.id,
            status=LocationChangeRequestStatus.PENDING,
        )
    )[0]

    result = await cancel_location_change_request_impl(db_session, user.id, request_id=request.id)

    assert f"id={request.id}" in result
    assert "cancelled" in result
    cancelled = await list_location_change_requests(
        db_session,
        created_by_user_id=user.id,
        status=LocationChangeRequestStatus.CANCELLED,
    )
    assert len(cancelled) == 1
