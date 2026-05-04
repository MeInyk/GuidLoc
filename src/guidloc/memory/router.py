"""HTTP routes for user memory (frontend / debug)."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.dependencies import get_current_user
from guidloc.common.database import get_session
from guidloc.memory import service
from guidloc.memory.models import MemoryItemStatus, MemorySection
from guidloc.memory.schemas import (
    MemoryItemCreate,
    MemoryItemRead,
    MemoryItemUpdate,
    UserMemoryRead,
    UserProfileRead,
    UserProfileUpdate,
)
from guidloc.users.models import User

router = APIRouter(prefix="/users/me", tags=["memory"])


def _split_by_section(items: list) -> dict[MemorySection, list]:
    buckets: dict[MemorySection, list] = {s: [] for s in MemorySection}
    for item in items:
        buckets[item.section].append(item)
    return buckets


@router.get(
    "/memory",
    response_model=UserMemoryRead,
    summary="Get the full memory snapshot of the current user",
)
async def get_memory(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserMemoryRead:
    profile = await service.get_or_create_profile(session, current_user.id)
    items = await service.list_items(
        session,
        current_user.id,
        statuses=[MemoryItemStatus.POSSIBLE, MemoryItemStatus.CONFIRMED],
    )
    buckets = _split_by_section(items)
    return UserMemoryRead(
        profile=UserProfileRead.model_validate(profile),
        rules=[MemoryItemRead.model_validate(i) for i in buckets[MemorySection.RULE]],
        preferences=[MemoryItemRead.model_validate(i) for i in buckets[MemorySection.PREFERENCE]],
        user_info=[MemoryItemRead.model_validate(i) for i in buckets[MemorySection.USER_INFO]],
        notes=[MemoryItemRead.model_validate(i) for i in buckets[MemorySection.NOTE]],
    )


@router.patch(
    "/profile",
    response_model=UserProfileRead,
    summary="Update the static profile fields",
)
async def patch_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> UserProfileRead:
    profile = await service.update_profile(session, current_user.id, payload)
    return UserProfileRead.model_validate(profile)


@router.post(
    "/memory/items",
    response_model=MemoryItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dynamic memory item",
)
async def create_item(
    payload: MemoryItemCreate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemoryItemRead:
    item = await service.create_item(session, current_user.id, payload)
    return MemoryItemRead.model_validate(item)


@router.patch(
    "/memory/items/{item_id}",
    response_model=MemoryItemRead,
    summary="Update a dynamic memory item",
)
async def patch_item(
    item_id: int,
    payload: MemoryItemUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> MemoryItemRead:
    item = await service.get_item(session, current_user.id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    item = await service.update_item(session, item, payload)
    return MemoryItemRead.model_validate(item)


@router.delete(
    "/memory/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Permanently delete a dynamic memory item",
)
async def delete_item(
    item_id: int,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    item = await service.get_item(session, current_user.id, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    await service.delete_item(session, item)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
