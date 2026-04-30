"""End-to-end tests for refresh and logout endpoints."""

from httpx import AsyncClient


async def _register_and_login(
    client: AsyncClient,
    email: str = "user@example.com",
) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!"},
    )
    response = await client.post(
        "/auth/login",
        json={"email": email, "password": "Sup3rSecret!"},
    )
    assert response.status_code == 200
    return response.json()


async def test_refresh_returns_new_token_pair(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["access_token"]
    assert new_tokens["refresh_token"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


async def test_refresh_with_access_token_returns_401(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )

    assert response.status_code == 401


async def test_refresh_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": "not-a-jwt"},
    )

    assert response.status_code == 401


async def test_old_refresh_token_cannot_be_reused(client: AsyncClient) -> None:
    tokens = await _register_and_login(client)

    first = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert first.status_code == 200

    second = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert second.status_code == 401


async def test_reuse_of_revoked_token_revokes_all_active_tokens(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, email="reuse@example.com")

    rotated = (
        await client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    ).json()

    replay = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert replay.status_code == 401

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert response.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, email="logout@example.com")

    response = await client.post(
        "/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 204

    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 401


async def test_logout_with_invalid_token_is_idempotent(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/logout",
        json={"refresh_token": "not-a-jwt"},
    )
    assert response.status_code == 204
