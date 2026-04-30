"""End-to-end tests for the /chats endpoints."""

from httpx import AsyncClient


async def _register_and_login(client: AsyncClient, email: str) -> dict:
    await client.post(
        "/auth/register",
        json={"email": email, "password": "Sup3rSecret!"},
    )
    return (
        await client.post(
            "/auth/login",
            json={"email": email, "password": "Sup3rSecret!"},
        )
    ).json()


def _headers(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _create_chat(client: AsyncClient, tokens: dict, title: str = "My chat") -> dict:
    response = await client.post(
        "/chats",
        headers=_headers(tokens),
        json={"title": title},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_chat_returns_201(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "alice@example.com")

    body = await _create_chat(client, tokens, title="Trip to Chernivtsi")

    assert body["title"] == "Trip to Chernivtsi"
    assert body["is_pinned"] is False
    assert "id" in body


async def test_create_chat_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/chats", json={"title": "Anon"})

    assert response.status_code == 401


async def test_create_chat_validates_title_length(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "valid@example.com")

    response = await client.post(
        "/chats",
        headers=_headers(tokens),
        json={"title": ""},
    )

    assert response.status_code == 422


async def test_list_chats_returns_only_user_chats(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "alice2@example.com")
    bob = await _register_and_login(client, "bob@example.com")

    await _create_chat(client, alice, "Alice 1")
    await _create_chat(client, alice, "Alice 2")
    await _create_chat(client, bob, "Bob only")

    response = await client.get("/chats", headers=_headers(alice))

    assert response.status_code == 200
    titles = [c["title"] for c in response.json()]
    assert sorted(titles) == ["Alice 1", "Alice 2"]


async def test_list_chats_orders_pinned_first(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "order@example.com")
    first = await _create_chat(client, tokens, "First")
    second = await _create_chat(client, tokens, "Second")

    pin = await client.patch(
        f"/chats/{second['id']}",
        headers=_headers(tokens),
        json={"is_pinned": True},
    )
    assert pin.status_code == 200

    response = await client.get("/chats", headers=_headers(tokens))

    assert response.status_code == 200
    chats = response.json()
    assert chats[0]["id"] == second["id"]
    assert chats[1]["id"] == first["id"]


async def test_get_chat_returns_chat(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "get@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.get(f"/chats/{chat['id']}", headers=_headers(tokens))

    assert response.status_code == 200
    assert response.json()["id"] == chat["id"]


async def test_get_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "alice3@example.com")
    bob = await _register_and_login(client, "bob2@example.com")
    chat = await _create_chat(client, alice, "Alice private")

    response = await client.get(f"/chats/{chat['id']}", headers=_headers(bob))

    assert response.status_code == 404


async def test_get_unknown_chat_returns_404(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "unknown@example.com")

    response = await client.get("/chats/999999", headers=_headers(tokens))

    assert response.status_code == 404


async def test_patch_chat_renames_and_pins(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "patch@example.com")
    chat = await _create_chat(client, tokens, "Old name")

    response = await client.patch(
        f"/chats/{chat['id']}",
        headers=_headers(tokens),
        json={"title": "New name", "is_pinned": True},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New name"
    assert body["is_pinned"] is True


async def test_patch_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "alice4@example.com")
    bob = await _register_and_login(client, "bob3@example.com")
    chat = await _create_chat(client, alice, "Alice")

    response = await client.patch(
        f"/chats/{chat['id']}",
        headers=_headers(bob),
        json={"title": "Hijacked"},
    )

    assert response.status_code == 404


async def test_delete_chat_returns_204(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "delete@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.delete(f"/chats/{chat['id']}", headers=_headers(tokens))
    assert response.status_code == 204

    follow_up = await client.get(f"/chats/{chat['id']}", headers=_headers(tokens))
    assert follow_up.status_code == 404


async def test_delete_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "alice5@example.com")
    bob = await _register_and_login(client, "bob4@example.com")
    chat = await _create_chat(client, alice, "Alice")

    response = await client.delete(f"/chats/{chat['id']}", headers=_headers(bob))
    assert response.status_code == 404

    # Confirm Alice's chat is still there.
    still_there = await client.get(f"/chats/{chat['id']}", headers=_headers(alice))
    assert still_there.status_code == 200
