"""HTTP routes for authentication."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.dependencies import get_current_user
from guidloc.auth.jwt import create_access_token
from guidloc.auth.schemas import LoginRequest, Token
from guidloc.auth.security import verify_password
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


@router.post("/login", response_model=Token, summary="Authenticate and receive a JWT")
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_session),
) -> Token:
    """Verify credentials and return an access token."""
    user = await get_user_by_email(session, payload.email)
    # Always return the same error to avoid leaking whether the email exists.
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    access_token = create_access_token(subject=user.id)
    return Token(access_token=access_token)


@router.get("/me", response_model=UserRead, summary="Get the current authenticated user")
async def me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user
