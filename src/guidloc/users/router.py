"""HTTP routes for user profile management."""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.dependencies import get_current_user
from guidloc.common.database import get_session
from guidloc.users.models import User
from guidloc.users.schemas import UserRead, UserUpdate
from guidloc.users.service import update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserRead,
    summary="Get the current user's profile",
)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the authenticated user's profile."""
    return current_user


@router.patch(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Update the current user's profile",
)
async def patch_me(
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Apply partial updates to the authenticated user's profile."""
    return await update_user(session, current_user, payload)
