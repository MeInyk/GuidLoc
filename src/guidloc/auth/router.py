"""HTTP routes for authentication."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.dependencies import get_current_user
from guidloc.auth.jwt import InvalidTokenError, TokenExpiredError
from guidloc.auth.schemas import LoginRequest, RefreshRequest, TokenPair
from guidloc.auth.security import verify_password
from guidloc.auth.service import (
    issue_token_pair,
    revoke_refresh_token,
    rotate_refresh_token,
)
from guidloc.common.database import get_session
from guidloc.users.models import User
from guidloc.users.schemas import UserCreate, UserRead
from guidloc.users.service import create_user, get_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: UserCreate,
    session: AsyncSession = Depends(get_session),
) -> User:
    """Create a new user account."""
    existing = await get_user_by_email(session, payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User with this email already exists",
        )
    return await create_user(session, payload)


@router.post(
    "/login",
    response_model=TokenPair,
    summary="Authenticate and receive an access + refresh token pair",
)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Verify credentials and return a token pair."""
    user = await get_user_by_email(session, payload.email)
    # Always return the same error to avoid leaking whether the email exists.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    return await issue_token_pair(session, user.id)


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Exchange a refresh token for a new token pair",
)
async def refresh(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> TokenPair:
    """Rotate the provided refresh token and return a new pair."""
    try:
        return await rotate_refresh_token(session, payload.refresh_token)
    except (TokenExpiredError, InvalidTokenError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        ) from exc


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the provided refresh token",
)
async def logout(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
) -> Response:
    """Revoke the given refresh token. Always returns 204."""
    await revoke_refresh_token(session, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead, summary="Get the current authenticated user")
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user
