"""End-to-end tests for the /chats/{chat_id}/generate endpoint (echo provider)."""

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


async def test_generate_requires_auth(client: AsyncClient) -> None:
    response = await client.post("/chats/1/generate")

    assert response.status_code == 401


async def test_generate_for_unknown_chat_returns_404(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "gen-unknown@example.com")

    response = await client.post("/chats/999999/generate", headers=_headers(tokens))

    assert response.status_code == 404


async def test_generate_for_other_users_chat_returns_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "gen-alice@example.com")
    bob = await _register_and_login(client, "gen-bob@example.com")
    chat = await _create_chat(client, alice)
    await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(alice),
        json={"role": "user", "content": "hi"},
    )

    response = await client.post(f"/chats/{chat['id']}/generate", headers=_headers(bob))

    assert response.status_code == 404


async def test_generate_for_empty_chat_returns_400(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "gen-empty@example.com")
    chat = await _create_chat(client, tokens)

    response = await client.post(f"/chats/{chat['id']}/generate", headers=_headers(tokens))

    assert response.status_code == 400


async def test_generate_creates_assistant_message(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "gen-ok@example.com")
    chat = await _create_chat(client, tokens)
    await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(tokens),
        json={"role": "user", "content": "hello"},
    )

    response = await client.post(f"/chats/{chat['id']}/generate", headers=_headers(tokens))

    assert response.status_code == 201
    body = response.json()
    assert body["chat_id"] == chat["id"]
    assert body["role"] == "assistant"
    assert body["content"] == "Echo: hello"


async def test_generated_message_appears_in_listing(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "gen-list@example.com")
    chat = await _create_chat(client, tokens)
    await client.post(
        f"/chats/{chat['id']}/messages",
        headers=_headers(tokens),
        json={"role": "user", "content": "ping"},
    )

    await client.post(f"/chats/{chat['id']}/generate", headers=_headers(tokens))

    listing = (await client.get(f"/chats/{chat['id']}/messages", headers=_headers(tokens))).json()
    roles = [m["role"] for m in listing]
    assert roles == ["user", "assistant"]
    assert listing[1]["content"] == "Echo: ping"
