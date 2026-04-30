import asyncio

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.users.models import User


async def test_create_user_persists_fields(db_session: AsyncSession) -> None:
    user = User(
        email="alice@example.com",
        password_hash="hashed",
        first_name="Alice",
        last_name="Smith",
    )
    db_session.add(user)
    await db_session.commit()

    fetched = (
        await db_session.execute(select(User).where(User.email == "alice@example.com"))
    ).scalar_one()

    assert fetched.id is not None
    assert fetched.email == "alice@example.com"
    assert fetched.first_name == "Alice"
    assert fetched.last_name == "Smith"
    assert fetched.is_superuser is False
    assert fetched.password_hash == "hashed"
    assert fetched.created_at is not None
    assert fetched.updated_at is not None


async def test_email_must_be_unique(db_session: AsyncSession) -> None:
    db_session.add(User(email="dup@example.com", password_hash="x"))
    await db_session.commit()

    db_session.add(User(email="dup@example.com", password_hash="y"))

    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_updated_at_changes_on_update(db_session: AsyncSession) -> None:
    user = User(email="bob@example.com", password_hash="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    initial_updated_at = user.updated_at

    # SQLite stores timestamps with second precision, so wait a moment.
    await asyncio.sleep(1.1)

    user.first_name = "Bob"
    await db_session.commit()
    await db_session.refresh(user)

    assert user.updated_at >= initial_updated_at
    assert user.first_name == "Bob"


async def test_is_superuser_defaults_to_false(db_session: AsyncSession) -> None:
    user = User(email="carol@example.com", password_hash="x")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    assert user.is_superuser is False
