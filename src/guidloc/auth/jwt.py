"""JWT token creation and validation."""

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from guidloc.common.config import get_settings


class TokenError(Exception):
    """Base class for token-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""


class InvalidTokenError(TokenError):
    """Raised when a token is malformed or has an invalid signature."""


def create_access_token(
    subject: str | int,
    *,
    expires_in: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token.

    Args:
        subject: User identifier placed in the `sub` claim.
        expires_in: Optional custom lifetime. Defaults to settings value.
        extra_claims: Optional additional claims to include in the payload.

    Returns:
        Encoded JWT as a string.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    lifetime = expires_in or timedelta(minutes=settings.access_token_expire_minutes)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token.

    Raises:
        TokenExpiredError: If the token has expired.
        InvalidTokenError: If the token is malformed or has an invalid signature.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError("Invalid access token") from exc

    if payload.get("type") != "access":
        raise InvalidTokenError("Token type is not 'access'")

    return payload
