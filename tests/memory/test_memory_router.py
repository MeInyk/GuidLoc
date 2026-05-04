"""End-to-end tests for /users/me/memory and /users/me/profile."""

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


def _h(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_memory_requires_auth(client: AsyncClient) -> None:
    assert (await client.get("/users/me/memory")).status_code == 401
    assert (await client.patch("/users/me/profile", json={})).status_code == 401
    assert (
        await client.post("/users/me/memory/items", json={"section": "note", "value": "x"})
    ).status_code == 401


async def test_memory_starts_empty(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "mem-empty@example.com")

    response = await client.get("/users/me/memory", headers=_h(tokens))

    assert response.status_code == 200
    body = response.json()
    assert body["profile"]["preferred_name"] is None
    assert body["rules"] == []
    assert body["preferences"] == []
    assert body["user_info"] == []
    assert body["notes"] == []


async def test_patch_profile_updates_fields(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "mem-profile@example.com")

    response = await client.patch(
        "/users/me/profile",
        headers=_h(tokens),
        json={"preferred_name": "Oleh", "phone": "+380000000000"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["preferred_name"] == "Oleh"
    assert body["phone"] == "+380000000000"

    snapshot = (await client.get("/users/me/memory", headers=_h(tokens))).json()
    assert snapshot["profile"]["preferred_name"] == "Oleh"


async def test_create_update_delete_item(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "mem-item@example.com")

    created = await client.post(
        "/users/me/memory/items",
        headers=_h(tokens),
        json={"section": "preference", "value": "loves cheesecakes"},
    )
    assert created.status_code == 201
    item = created.json()
    assert item["section"] == "preference"
    assert item["status"] == "possible"

    updated = await client.patch(
        f"/users/me/memory/items/{item['id']}",
        headers=_h(tokens),
        json={"status": "confirmed"},
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "confirmed"

    snapshot = (await client.get("/users/me/memory", headers=_h(tokens))).json()
    assert any(p["id"] == item["id"] for p in snapshot["preferences"])

    deleted = await client.delete(f"/users/me/memory/items/{item['id']}", headers=_h(tokens))
    assert deleted.status_code == 204

    snapshot = (await client.get("/users/me/memory", headers=_h(tokens))).json()
    assert snapshot["preferences"] == []


async def test_archived_items_are_not_returned(client: AsyncClient) -> None:
    tokens = await _register_and_login(client, "mem-archived@example.com")

    created = (
        await client.post(
            "/users/me/memory/items",
            headers=_h(tokens),
            json={"section": "note", "value": "doctor on Friday", "status": "confirmed"},
        )
    ).json()
    await client.patch(
        f"/users/me/memory/items/{created['id']}",
        headers=_h(tokens),
        json={"status": "archived"},
    )

    snapshot = (await client.get("/users/me/memory", headers=_h(tokens))).json()
    assert snapshot["notes"] == []


async def test_other_users_item_is_404(client: AsyncClient) -> None:
    alice = await _register_and_login(client, "mem-alice@example.com")
    bob = await _register_and_login(client, "mem-bob@example.com")
    item = (
        await client.post(
            "/users/me/memory/items",
            headers=_h(alice),
            json={"section": "note", "value": "x"},
        )
    ).json()

    assert (
        await client.patch(
            f"/users/me/memory/items/{item['id']}",
            headers=_h(bob),
            json={"value": "y"},
        )
    ).status_code == 404
    assert (
        await client.delete(f"/users/me/memory/items/{item['id']}", headers=_h(bob))
    ).status_code == 404
