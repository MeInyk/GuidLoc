"""Tests for JWT access token utilities."""

from datetime import timedelta

import jwt
import pytest

from guidloc.auth.jwt import (
    InvalidTokenError,
    TokenExpiredError,
    create_access_token,
    decode_access_token,
)
from guidloc.common.config import get_settings


def test_create_and_decode_access_token_roundtrip() -> None:
    token = create_access_token(subject=42)

    payload = decode_access_token(token)

    assert payload["sub"] == "42"
    assert payload["type"] == "access"
    assert "iat" in payload
    assert "exp" in payload


def test_extra_claims_are_included() -> None:
    token = create_access_token(subject="user-1", extra_claims={"role": "admin"})

    payload = decode_access_token(token)

    assert payload["role"] == "admin"
    assert payload["sub"] == "user-1"


def test_expired_token_raises_token_expired_error() -> None:
    token = create_access_token(subject=1, expires_in=timedelta(seconds=-1))

    with pytest.raises(TokenExpiredError):
        decode_access_token(token)


def test_invalid_signature_raises_invalid_token_error() -> None:
    settings = get_settings()
    token = jwt.encode(
        {"sub": "1", "type": "access"},
        "wrong-secret-key-that-is-at-least-32-bytes",
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_malformed_token_raises_invalid_token_error() -> None:
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt")


def test_wrong_token_type_raises_invalid_token_error() -> None:
    settings = get_settings()
    token = jwt.encode(
        {"sub": "1", "type": "refresh"},
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)
