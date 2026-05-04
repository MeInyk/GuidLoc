"""Unit tests for memory agent tools — call inner impls via the service layer."""

from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.memory import service
from guidloc.memory.models import MemoryItemStatus, MemorySection
from guidloc.memory.schemas import MemoryItemCreate, UserProfileUpdate
from guidloc.users.models import User


async def _make_user(session: AsyncSession, email: str) -> User:
    user = User(email=email, password_hash="x")
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def test_get_or_create_profile_is_idempotent(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tools-1@example.com")

    p1 = await service.get_or_create_profile(db_session, user.id)
    p2 = await service.get_or_create_profile(db_session, user.id)

    assert p1.id == p2.id


async def test_update_profile_partial(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tools-2@example.com")
    await service.update_profile(
        db_session, user.id, UserProfileUpdate(preferred_name="Olia", phone="+380")
    )
    profile = await service.update_profile(db_session, user.id, UserProfileUpdate(phone="+381"))

    assert profile.preferred_name == "Olia"
    assert profile.phone == "+381"


async def test_archive_item_hides_from_default_listing(db_session: AsyncSession) -> None:
    user = await _make_user(db_session, "tools-3@example.com")
    item = await service.create_item(
        db_session,
        user.id,
        MemoryItemCreate(
            section=MemorySection.PREFERENCE,
            value="likes coffee",
            status=MemoryItemStatus.CONFIRMED,
        ),
    )

    await service.archive_item(db_session, item)

    visible = await service.list_items(
        db_session,
        user.id,
        statuses=[MemoryItemStatus.POSSIBLE, MemoryItemStatus.CONFIRMED],
    )
    assert visible == []
    archived = await service.list_items(db_session, user.id, statuses=[MemoryItemStatus.ARCHIVED])
    assert len(archived) == 1
