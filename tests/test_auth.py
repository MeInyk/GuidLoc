"""End-to-end tests for the auth endpoints."""

from datetime import timedelta

from httpx import AsyncClient

from guidloc.auth.jwt import create_access_token


async def _register(
    client: AsyncClient,
    *,
    email: str = "alice@example.com",
    password: str = "Sup3rSecret!",
    first_name: str | None = "Alice",
    last_name: str | None = "Smith",
) -> dict:
    response = await client.post(
        "/auth/register",
        json={
            "email": email,
            "password": password,
            "first_name": first_name,
            "last_name": last_name,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_register_creates_user_and_returns_public_fields(client: AsyncClient) -> None:
    body = await _register(client)

    assert body["email"] == "alice@example.com"
    assert body["first_name"] == "Alice"
    assert body["last_name"] == "Smith"
    assert body["is_superuser"] is False
    assert "id" in body
    assert "created_at" in body
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_duplicate_email_returns_409(client: AsyncClient) -> None:
    await _register(client, email="dup@example.com")

    response = await client.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "AnotherPass1!"},
    )

    assert response.status_code == 409


async def test_register_short_password_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "weak@example.com", "password": "short"},
    )

    assert response.status_code == 422


async def test_register_invalid_email_returns_422(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": "Sup3rSecret!"},
    )

    assert response.status_code == 422


async def test_login_returns_access_token(client: AsyncClient) -> None:
    await _register(client, email="bob@example.com", password="Sup3rSecret!")

    response = await client.post(
        "/auth/login",
        json={"email": "bob@example.com", "password": "Sup3rSecret!"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert isinstance(body["access_token"], str)


async def test_login_wrong_password_returns_401(client: AsyncClient) -> None:
    await _register(client, email="carol@example.com", password="Sup3rSecret!")

    response = await client.post(
        "/auth/login",
        json={"email": "carol@example.com", "password": "WrongPass1!"},
    )

    assert response.status_code == 401


async def test_login_unknown_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login",
        json={"email": "ghost@example.com", "password": "Sup3rSecret!"},
    )

    assert response.status_code == 401


async def test_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_me_with_valid_token_returns_user(client: AsyncClient) -> None:
    user = await _register(client, email="dave@example.com", password="Sup3rSecret!")

    login = await client.post(
        "/auth/login",
        json={"email": "dave@example.com", "password": "Sup3rSecret!"},
    )
    token = login.json()["access_token"]

    response = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == user["id"]
    assert body["email"] == "dave@example.com"


async def test_me_with_expired_token_returns_401(client: AsyncClient) -> None:
    user = await _register(client, email="erin@example.com", password="Sup3rSecret!")
    expired = create_access_token(subject=user["id"], expires_in=timedelta(seconds=-1))

    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired}"},
    )

    assert response.status_code == 401


async def test_me_with_garbage_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer not-a-jwt"},
    )

    assert response.status_code == 401
