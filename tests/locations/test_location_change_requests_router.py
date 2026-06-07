"""Tests for user-submitted location change requests."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.locations.models import Location, LocationCategory, PriceLevel
from guidloc.locations.schemas import LocationCreate
from guidloc.locations.service import create_location


async def _register_and_login(client: AsyncClient, email: str) -> tuple[dict, dict]:
    user = (
        await client.post(
            "/auth/register",
            json={"email": email, "password": "Sup3rSecret!"},
        )
    ).json()
    tokens = (
        await client.post(
            "/auth/login",
            json={"email": email, "password": "Sup3rSecret!"},
        )
    ).json()
    return user, tokens


def _headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
def sample_location_payload() -> LocationCreate:
    return LocationCreate(
        name="Alpha Cafe",
        description="Specialty coffee",
        address="1 Alpha St",
        latitude=48.29,
        longitude=25.93,
        category=LocationCategory.CAFE,
        price_level=PriceLevel.LOW,
        tags=["wifi", "quiet"],
    )


async def test_create_change_request_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/location-change-requests",
        json={
            "change_type": "create",
            "reason": "Missing place",
            "proposed_changes": {
                "name": "New Cafe",
                "address": "10 New St",
                "latitude": 48.3,
                "longitude": 25.94,
                "category": "cafe",
            },
        },
    )

    assert response.status_code == 401


async def test_create_change_request_stores_user_and_pending_status(
    client: AsyncClient,
) -> None:
    user, tokens = await _register_and_login(client, "proposal-create@example.com")

    response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "create",
            "reason": "This place is missing from GuidLoc",
            "proposed_changes": {
                "name": "New Cafe",
                "address": "10 New St",
                "latitude": 48.3,
                "longitude": 25.94,
                "category": "cafe",
                "tags": [" Coffee ", "coffee", "quiet"],
            },
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["created_by_user_id"] == user["id"]
    assert body["change_type"] == "create"
    assert body["status"] == "pending"
    assert body["proposed_changes"]["tags"] == ["coffee", "quiet"]


async def test_create_location_request_validates_required_fields(
    client: AsyncClient,
) -> None:
    _, tokens = await _register_and_login(client, "proposal-invalid@example.com")

    response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "create",
            "reason": "Missing place",
            "proposed_changes": {"name": "Only Name"},
        },
    )

    assert response.status_code == 422
    assert "Missing required fields" in response.text


async def test_merge_create_request_creates_location(
    client: AsyncClient,
) -> None:
    _, tokens = await _register_and_login(client, "proposal-merge-create@example.com")
    create_response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "create",
            "reason": "A newly opened cafe",
            "proposed_changes": {
                "name": "Fresh Cafe",
                "description": "Small espresso bar",
                "address": "7 Fresh St",
                "latitude": 48.31,
                "longitude": 25.95,
                "category": "cafe",
                "price_level": "low",
                "tags": ["coffee"],
            },
        },
    )
    request_id = create_response.json()["id"]

    merge_response = await client.post(
        f"/location-change-requests/{request_id}/merge",
        headers=_headers(tokens),
        json={},
    )

    assert merge_response.status_code == 200
    body = merge_response.json()
    assert body["change_request"]["status"] == "merged"
    assert body["location"]["name"] == "Fresh Cafe"
    assert body["location"]["price_level"] == "low"

    location_id = body["location"]["id"]
    location_response = await client.get(f"/locations/{location_id}")
    assert location_response.status_code == 200
    assert location_response.json()["address"] == "7 Fresh St"


async def test_merge_update_request_applies_only_proposed_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_location_payload: LocationCreate,
) -> None:
    _, tokens = await _register_and_login(client, "proposal-merge-update@example.com")
    location = await create_location(db_session, sample_location_payload)
    create_response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "update",
            "location_id": location.id,
            "reason": "User says the address and tags changed",
            "proposed_changes": {
                "address": "99 Updated St",
                "tags": ["updated", "quiet"],
            },
        },
    )

    merge_response = await client.post(
        f"/location-change-requests/{create_response.json()['id']}/merge",
        headers=_headers(tokens),
        json={},
    )

    assert merge_response.status_code == 200
    body = merge_response.json()["location"]
    assert body["name"] == "Alpha Cafe"
    assert body["description"] == "Specialty coffee"
    assert body["address"] == "99 Updated St"
    assert body["category"] == "cafe"
    assert body["price_level"] == "low"
    assert body["tags"] == ["updated", "quiet"]


async def test_merge_update_request_detects_stale_location(
    client: AsyncClient,
    db_session: AsyncSession,
    sample_location_payload: LocationCreate,
) -> None:
    _, tokens = await _register_and_login(client, "proposal-stale@example.com")
    location = await create_location(db_session, sample_location_payload)
    create_response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "update",
            "location_id": location.id,
            "reason": "User says the address changed",
            "proposed_changes": {"address": "99 Updated St"},
        },
    )

    latest_location = await db_session.get(Location, location.id)
    assert latest_location is not None
    latest_location.address = "Changed before review"
    latest_location.updated_at = datetime.now(UTC) + timedelta(seconds=5)
    await db_session.commit()

    merge_response = await client.post(
        f"/location-change-requests/{create_response.json()['id']}/merge",
        headers=_headers(tokens),
        json={},
    )

    assert merge_response.status_code == 409
    assert "force=true" in merge_response.json()["detail"]


async def test_list_my_change_requests_returns_only_current_user_requests(
    client: AsyncClient,
) -> None:
    _, alice = await _register_and_login(client, "proposal-list-alice@example.com")
    _, bob = await _register_and_login(client, "proposal-list-bob@example.com")

    await client.post(
        "/location-change-requests",
        headers=_headers(alice),
        json={
            "change_type": "create",
            "reason": "Alice place",
            "proposed_changes": {
                "name": "Alice Cafe",
                "address": "1 Alice St",
                "latitude": 48.3,
                "longitude": 25.94,
                "category": "cafe",
            },
        },
    )
    await client.post(
        "/location-change-requests",
        headers=_headers(bob),
        json={
            "change_type": "create",
            "reason": "Bob place",
            "proposed_changes": {
                "name": "Bob Cafe",
                "address": "1 Bob St",
                "latitude": 48.31,
                "longitude": 25.95,
                "category": "cafe",
            },
        },
    )

    response = await client.get(
        "/users/me/location-change-requests",
        headers=_headers(alice),
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["reason"] == "Alice place"


async def test_amend_my_pending_create_request_merges_extra_fields(
    client: AsyncClient,
) -> None:
    _, tokens = await _register_and_login(client, "proposal-amend@example.com")
    create_response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "create",
            "reason": "Missing place",
            "proposed_changes": {
                "name": "Patch Cafe",
                "address": "10 Patch St",
                "latitude": 48.3,
                "longitude": 25.94,
                "category": "cafe",
            },
        },
    )
    request_id = create_response.json()["id"]

    amend_response = await client.patch(
        f"/users/me/location-change-requests/{request_id}",
        headers=_headers(tokens),
        json={
            "proposed_changes": {
                "price_level": "high",
                "tags": [" Coffee ", "coffee", "quiet"],
            }
        },
    )

    assert amend_response.status_code == 200
    body = amend_response.json()
    assert body["id"] == request_id
    assert body["status"] == "pending"
    assert body["change_type"] == "create"
    assert body["proposed_changes"] == {
        "name": "Patch Cafe",
        "address": "10 Patch St",
        "latitude": 48.3,
        "longitude": 25.94,
        "category": "cafe",
        "price_level": "high",
        "tags": ["coffee", "quiet"],
    }


async def test_other_user_cannot_amend_or_cancel_request(client: AsyncClient) -> None:
    _, alice = await _register_and_login(client, "proposal-owner@example.com")
    _, bob = await _register_and_login(client, "proposal-intruder@example.com")
    create_response = await client.post(
        "/location-change-requests",
        headers=_headers(alice),
        json={
            "change_type": "create",
            "reason": "Alice request",
            "proposed_changes": {
                "name": "Private Cafe",
                "address": "1 Private St",
                "latitude": 48.3,
                "longitude": 25.94,
                "category": "cafe",
            },
        },
    )
    request_id = create_response.json()["id"]

    amend_response = await client.patch(
        f"/users/me/location-change-requests/{request_id}",
        headers=_headers(bob),
        json={"proposed_changes": {"price_level": "high"}},
    )
    cancel_response = await client.post(
        f"/users/me/location-change-requests/{request_id}/cancel",
        headers=_headers(bob),
    )

    assert amend_response.status_code == 404
    assert cancel_response.status_code == 404


async def test_cancel_my_pending_request_blocks_merge(client: AsyncClient) -> None:
    _, tokens = await _register_and_login(client, "proposal-cancel@example.com")
    create_response = await client.post(
        "/location-change-requests",
        headers=_headers(tokens),
        json={
            "change_type": "create",
            "reason": "User changed their mind",
            "proposed_changes": {
                "name": "Cancel Cafe",
                "address": "1 Cancel St",
                "latitude": 48.3,
                "longitude": 25.94,
                "category": "cafe",
            },
        },
    )
    request_id = create_response.json()["id"]

    cancel_response = await client.post(
        f"/users/me/location-change-requests/{request_id}/cancel",
        headers=_headers(tokens),
    )

    assert cancel_response.status_code == 200
    assert cancel_response.json()["status"] == "cancelled"

    merge_response = await client.post(
        f"/location-change-requests/{request_id}/merge",
        headers=_headers(tokens),
        json={},
    )
    assert merge_response.status_code == 409
    assert "Only pending" in merge_response.json()["detail"]
