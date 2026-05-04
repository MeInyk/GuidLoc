"""Database operations for user memory."""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.memory.models import (
    MemoryItemStatus,
    MemorySection,
    UserMemoryItem,
    UserProfile,
)
from guidloc.memory.schemas import (
    MemoryItemCreate,
    MemoryItemUpdate,
    UserProfileUpdate,
)


async def get_or_create_profile(session: AsyncSession, user_id: int) -> UserProfile:
    """Return the user's profile row, creating an empty one if missing."""
    result = await session.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = UserProfile(user_id=user_id)
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
    return profile


async def update_profile(
    session: AsyncSession, user_id: int, payload: UserProfileUpdate
) -> UserProfile:
    """Apply a partial update to the user's profile."""
    profile = await get_or_create_profile(session, user_id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile


async def list_items(
    session: AsyncSession,
    user_id: int,
    *,
    sections: Iterable[MemorySection] | None = None,
    statuses: Iterable[MemoryItemStatus] | None = None,
) -> list[UserMemoryItem]:
    """List a user's memory items, optionally filtered by section and status."""
    stmt = select(UserMemoryItem).where(UserMemoryItem.user_id == user_id)
    if sections is not None:
        stmt = stmt.where(UserMemoryItem.section.in_(list(sections)))
    if statuses is not None:
        stmt = stmt.where(UserMemoryItem.status.in_(list(statuses)))
    stmt = stmt.order_by(UserMemoryItem.section.asc(), UserMemoryItem.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_item(session: AsyncSession, user_id: int, item_id: int) -> UserMemoryItem | None:
    """Return a memory item only if it belongs to the user."""
    result = await session.execute(
        select(UserMemoryItem).where(
            UserMemoryItem.id == item_id, UserMemoryItem.user_id == user_id
        )
    )
    return result.scalar_one_or_none()


async def create_item(
    session: AsyncSession, user_id: int, payload: MemoryItemCreate
) -> UserMemoryItem:
    """Create a new dynamic memory item for the user."""
    item = UserMemoryItem(
        user_id=user_id,
        section=payload.section,
        value=payload.value,
        status=payload.status,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


async def update_item(
    session: AsyncSession, item: UserMemoryItem, payload: MemoryItemUpdate
) -> UserMemoryItem:
    """Apply a partial update to a memory item."""
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


async def archive_item(session: AsyncSession, item: UserMemoryItem) -> UserMemoryItem:
    """Soft-delete: move an item to the archived status."""
    item.status = MemoryItemStatus.ARCHIVED
    await session.commit()
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, item: UserMemoryItem) -> None:
    """Hard-delete a memory item (used by the REST debug endpoint)."""
    await session.delete(item)
    await session.commit()
