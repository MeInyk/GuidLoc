"""Authentication and refresh token service."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from guidloc.auth.jwt import (
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from guidloc.auth.models import RefreshToken
from guidloc.auth.schemas import TokenPair


async def issue_token_pair(session: AsyncSession, user_id: int) -> TokenPair:
    """Issue a fresh access + refresh token pair and persist the refresh jti."""
    refresh_token, payload = create_refresh_token(subject=user_id)
    record = RefreshToken(
        jti=payload["jti"],
        user_id=user_id,
        expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
    )
    session.add(record)
    await session.commit()

    access_token = create_access_token(subject=user_id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


async def rotate_refresh_token(session: AsyncSession, refresh_token: str) -> TokenPair:
    """Validate, revoke and replace a refresh token. Detects token reuse."""
    payload = decode_refresh_token(refresh_token)
    jti = payload.get("jti")
    sub = payload.get("sub")
    if not jti or not sub:
        raise InvalidTokenError("Refresh token is missing required claims")

    user_id = int(sub)
    record = (
        await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalar_one_or_none()

    if record is None:
        raise InvalidTokenError("Refresh token is not recognized")

    if record.revoked_at is not None:
        # Reuse of a revoked token: revoke all active tokens for this user.
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()
        raise InvalidTokenError("Refresh token has already been used")

    record.revoked_at = datetime.now(UTC)
    await session.commit()

    return await issue_token_pair(session, user_id)


async def revoke_refresh_token(session: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token. Idempotent: unknown/expired tokens silently pass."""
    try:
        payload = decode_refresh_token(refresh_token)
    except InvalidTokenError:
        return

    jti = payload.get("jti")
    if not jti:
        return

    record = (
        await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    ).scalar_one_or_none()
    if record is None or record.revoked_at is not None:
        return

    record.revoked_at = datetime.now(UTC)
    await session.commit()
