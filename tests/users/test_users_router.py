"""End-to-end tests for the /users/me endpoints."""

from httpx import AsyncClient


async def _register_and_login(
    client: AsyncClient,
    email: str = "user@example.com",
) -> tuple[dict, dict]:
    user = (
        await client.post(
            "/auth/register",
            json={
                "email": email,
                "password": "Sup3rSecret!",
                "first_name": "Old",
                "last_name": "Name",
            },
        )
    ).json()
    tokens = (
        await client.post(
            "/auth/login",
            json={"email": email, "password": "Sup3rSecret!"},
        )
    ).json()
    return user, tokens


def _auth_headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_get_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/users/me")

    assert response.status_code == 401


async def test_get_me_returns_current_user(client: AsyncClient) -> None:
    user, tokens = await _register_and_login(client, email="me@example.com")

    response = await client.get("/users/me", headers=_auth_headers(tokens))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user["id"]
    assert body["email"] == "me@example.com"
    assert "password_hash" not in body


async def test_patch_me_updates_first_and_last_name(client: AsyncClient) -> None:
    _, tokens = await _register_and_login(client, email="patch@example.com")

    response = await client.patch(
        "/users/me",
        headers=_auth_headers(tokens),
        json={"first_name": "Alice", "last_name": "Wonder"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "Alice"
    assert body["last_name"] == "Wonder"


async def test_patch_me_partial_update_keeps_other_fields(client: AsyncClient) -> None:
    _, tokens = await _register_and_login(client, email="partial@example.com")

    response = await client.patch(
        "/users/me",
        headers=_auth_headers(tokens),
        json={"first_name": "OnlyFirst"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["first_name"] == "OnlyFirst"
    assert body["last_name"] == "Name"


async def test_patch_me_can_clear_optional_field(client: AsyncClient) -> None:
    _, tokens = await _register_and_login(client, email="clear@example.com")

    response = await client.patch(
        "/users/me",
        headers=_auth_headers(tokens),
        json={"last_name": None},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["last_name"] is None
    assert body["first_name"] == "Old"


async def test_patch_me_rejects_too_long_value(client: AsyncClient) -> None:
    _, tokens = await _register_and_login(client, email="long@example.com")

    response = await client.patch(
        "/users/me",
        headers=_auth_headers(tokens),
        json={"first_name": "x" * 101},
    )

    assert response.status_code == 422


async def test_patch_me_ignores_unknown_fields(client: AsyncClient) -> None:
    _, tokens = await _register_and_login(client, email="extra@example.com")

    response = await client.patch(
        "/users/me",
        headers=_auth_headers(tokens),
        json={"is_superuser": True, "email": "hacker@example.com"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_superuser"] is False
    assert body["email"] == "extra@example.com"


async def test_patch_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.patch("/users/me", json={"first_name": "Nope"})

    assert response.status_code == 401
