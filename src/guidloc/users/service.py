"""Database operations for users."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.security import hash_password
from guidloc.users.models import User
from guidloc.users.schemas import UserCreate, UserUpdate


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    """Return a user by email or None."""
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    """Return a user by primary key or None."""
    return await session.get(User, user_id)


async def create_user(session: AsyncSession, payload: UserCreate) -> User:
    """Create and persist a new user with a hashed password."""
    user = User(
        email=payload.email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(session: AsyncSession, user: User, payload: UserUpdate) -> User:
    """Apply a partial update to the given user and persist the change."""
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)

    await session.commit()
    await session.refresh(user)
    return user
