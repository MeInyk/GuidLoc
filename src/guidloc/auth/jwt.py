"""JWT token creation and validation."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt

from guidloc.common.config import get_settings


class TokenError(Exception):
    """Base class for token-related errors."""


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""


class InvalidTokenError(TokenError):
    """Raised when a token is malformed or has an invalid signature."""


TokenType = Literal["access", "refresh"]


def _encode(
    *,
    subject: str | int,
    token_type: TokenType,
    lifetime: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "type": token_type,
        "jti": uuid.uuid4().hex,
    }
    if extra_claims:
        payload.update(extra_claims)
    encoded = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return encoded, payload


def create_access_token(
    subject: str | int,
    *,
    expires_in: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token."""
    settings = get_settings()
    lifetime = expires_in or timedelta(minutes=settings.access_token_expire_minutes)
    token, _ = _encode(
        subject=subject,
        token_type="access",
        lifetime=lifetime,
        extra_claims=extra_claims,
    )
    return token


def create_refresh_token(
    subject: str | int,
    *,
    expires_in: timedelta | None = None,
) -> tuple[str, dict[str, Any]]:
    """Create a signed JWT refresh token. Returns (token, payload)."""
    settings = get_settings()
    lifetime = expires_in or timedelta(days=settings.refresh_token_expire_days)
    return _encode(subject=subject, token_type="refresh", lifetime=lifetime)


def _decode(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError(f"{expected_type.capitalize()} token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise InvalidTokenError(f"Invalid {expected_type} token") from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError(f"Token type is not '{expected_type}'")

    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    return _decode(token, expected_type="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT refresh token."""
    return _decode(token, expected_type="refresh")
