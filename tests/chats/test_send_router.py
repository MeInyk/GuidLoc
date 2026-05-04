"""End-to-end tests for the streaming /chats/{chat_id}/send endpoint."""

import json

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
    response = await client.post(
        "/chats",
        headers=_headers(tokens),
        json={"title": "Chat"},
    )
    assert response.status_code == 201
    return response.json()


async def _collect_sse(client: AsyncClient, url: str, headers, json_body):
    """POST to an SSE endpoint and collect (event, data) tuples."""
    events: list[tuple[str, dict]] = []
    async with client.stream(
        "POST",
        url,
        headers=headers,
        json=json_body,
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        event_name = "message"
        data_buf: list[str] = []
        async for line in response.aiter_lines():
            if line == "":
                if data_buf:
                    events.append((event_name, json.loads("".join(data_buf))))
                event_name = "message"
                data_buf = []
                continue
            if line.startswith("event:"):
                event_name = line[len("event:") :].strip()
            elif line.startswith("data:"):
                data_buf.append(line[len("data:") :].lstrip())
        # flush trailing frame if no final blank line
        if data_buf:
            events.append((event_name, json.loads("".join(data_buf))))
    return events


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


async def test_send_streams_user_delta_done(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "send-ok@example.com")
    chat = await _create_chat(client, tokens)

    events = await _collect_sse(
        client,
        f"/chats/{chat['id']}/send",
        _headers(tokens),
        {"content": "hello"},
    )

    types = [t for t, _ in events]
    assert types[0] == "user_message"
    assert "delta" in types
    assert types[-1] == "done"
    assert "error" not in types

    user_msg = events[0][1]["message"]
    assert user_msg["chat_id"] == chat["id"]
    assert user_msg["role"] == "user"
    assert user_msg["content"] == "hello"

    delta_text = "".join(d["text"] for t, d in events if t == "delta")
    assert delta_text == "Echo: hello"

    done_msg = events[-1][1]["assistant_message"]
    assert done_msg["chat_id"] == chat["id"]
    assert done_msg["role"] == "assistant"
    assert done_msg["content"] == "Echo: hello"
    assert done_msg["id"] != user_msg["id"]


async def test_send_appears_in_messages_listing(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "send-list@example.com")
    chat = await _create_chat(client, tokens)

    await _collect_sse(
        client,
        f"/chats/{chat['id']}/send",
        _headers(tokens),
        {"content": "ping"},
    )

    listing = (
        await client.get(
            f"/chats/{chat['id']}/messages",
            headers=_headers(tokens),
        )
    ).json()
    assert [m["role"] for m in listing] == ["user", "assistant"]
    assert [m["content"] for m in listing] == ["ping", "Echo: ping"]
