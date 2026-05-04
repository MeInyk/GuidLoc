"""End-to-end tests for the /chats/{chat_id}/send endpoint (echo provider)."""

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


async def _create_chat(client: AsyncClient, tokens: dict) -> dict:
    response = await client.post("/chats", headers=_headers(tokens), json={"title": "Chat"})
    assert response.status_code == 201
    return response.json()


async def test_send_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/chats/1/send", json={"content": "hi"})

    assert response.status_code == 401


async def test_send_for_unknown_chat_returns_404(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "send-unknown@example.com")

    response = await client.post(
        "/chats/999999/send",
        headers=_headers(tokens),
        json={"content": "hi"},
    )

    assert response.status_code == 404


async def test_send_for_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "send-alice@example.com")
    bob = await _register_and_login(client, "send-bob@example.com")
    chat = await _create_chat(client, alice)

    response = await client.post(
        f"/chats/{chat['id']}/send",
        headers=_headers(bob),
        json={"content": "intrusion"},
    )

    assert response.status_code == 404


async def test_send_validates_content(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "send-empty@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(
        f"/chats/{chat['id']}/send",
        headers=_headers(tokens),
        json={"content": ""},
    )

    assert response.status_code == 422


async def test_send_persists_user_and_assistant_messages(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "send-ok@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(
        f"/chats/{chat['id']}/send",
        headers=_headers(tokens),
        json={"content": "hello"},
    )

    assert response.status_code == 201
    body = response.json()

    assert body["user_message"]["chat_id"] == chat["id"]
    assert body["user_message"]["role"] == "user"
    assert body["user_message"]["content"] == "hello"

    assert body["assistant_message"]["chat_id"] == chat["id"]
    assert body["assistant_message"]["role"] == "assistant"
    assert body["assistant_message"]["content"] == "Echo: hello"

    assert body["assistant_message"]["id"] != body["user_message"]["id"]


async def test_send_appears_in_messages_listing(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "send-list@example.com")
    chat = await _create_chat(client, tokens)

    await client.post(
        f"/chats/{chat['id']}/send",
        headers=_headers(tokens),
        json={"content": "ping"},
    )

    listing = (await client.get(f"/chats/{chat['id']}/messages", headers=_headers(tokens))).json()
    roles = [m["role"] for m in listing]
    contents = [m["content"] for m in listing]
    assert roles == ["user", "assistant"]
    assert contents == ["ping", "Echo: ping"]
