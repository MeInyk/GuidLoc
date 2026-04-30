"""End-to-end tests for the /chats/{chat_id}/messages endpoints."""

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


async def _create_chat(client: AsyncClient, tokens: dict, title: str = "Chat") -> dict:
    response = await client.post("/chats", headers=_headers(tokens), json={"title": title})
    assert response.status_code == 201, response.text
    return response.json()


async def test_post_message_returns_201(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "msg1@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(tokens),
        json={"role": "user", "content": "Hello there"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["chat_id"] == chat["id"]
    assert body["role"] == "user"
    assert body["content"] == "Hello there"
    assert "id" in body
    assert "created_at" in body


async def test_post_message_defaults_to_user_role(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "msg2@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(tokens),
        json={"content": "no role specified"},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"


async def test_post_message_validates_content(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "msg3@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(tokens),
        json={"role": "user", "content": ""},
    )

    assert response.status_code == 422


async def test_post_message_rejects_invalid_role(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "msg4@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(tokens),
        json={"role": "admin", "content": "hi"},
    )

    assert response.status_code == 422


async def test_post_message_to_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "alice-msg@example.com")
    bob = await _register_and_login(client, "bob-msg@example.com")
    chat = await _create_chat(client, alice, "Alice private")

    response = await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(bob),
        json={"role": "user", "content": "intrusion"},
    )

    assert response.status_code == 404


async def test_post_message_requires_auth(client: AsyncClient) -> None:
    response = await client.post(
        "/chats/1/messages",
        json={"role": "user", "content": "anon"},
    )

    assert response.status_code == 401


async def test_list_messages_returns_messages_in_order(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "list@example.com")
    chat = await _create_chat(client, tokens)

    for content in ["one", "two", "three"]:
        await client.post(
            f"/chats/{chat['id']}/messages",
            headers=_headers(tokens),
            json={"role": "user", "content": content},
        )

    response = await client.get(f"/chats/{chat['id']}/messages", headers=_headers(tokens))

    assert response.status_code == 200
    contents = [m["content"] for m in response.json()]
    assert contents == ["one", "two", "three"]


async def test_list_messages_for_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "alice-list@example.com")
    bob = await _register_and_login(client, "bob-list@example.com")
    chat = await _create_chat(client, alice, "Alice")

    response = await client.get(f"/chats/{chat['id']}/messages", headers=_headers(bob))

    assert response.status_code == 404


async def test_creating_message_bumps_chat_in_listing(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "bump@example.com")
    first = await _create_chat(client, tokens, "First")
    second = await _create_chat(client, tokens, "Second")

    # Post into the older chat. It should bubble up to the top of the list.
    await client.post(
        f"/chats/{first['id']}/messages",
        headers=_headers(tokens),
        json={"role": "user", "content": "ping"},
    )

    response = await client.get("/chats", headers=_headers(tokens))
    assert response.status_code == 200
    chats = response.json()
    # No pinning -> ordered by updated_at desc, so the chat we just touched is first.
    assert chats[0]["id"] == first["id"]
    assert chats[1]["id"] == second["id"]


async def test_list_messages_for_unknown_chat_returns_404(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "missing@example.com")

    response = await client.get("/chats/999999/messages", headers=_headers(tokens))

    assert response.status_code == 404


async def test_messages_isolated_between_chats(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "iso@example.com")
    a = await _create_chat(client, tokens, "A")
    b = await _create_chat(client, tokens, "B")

    await client.post(
        f"/chats/{a['id']}/messages",
        headers=_headers(tokens),
        json={"role": "user", "content": "in A"},
    )

    response = await client.get(f"/chats/{b['id']}/messages", headers=_headers(tokens))

    assert response.status_code == 200
    assert response.json() == []
