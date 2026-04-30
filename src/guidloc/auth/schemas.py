"""Pydantic schemas for the auth module."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Payload for password-based login."""

    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    """Payload for refresh and logout endpoints."""

    refresh_token: str


class Token(BaseModel):
    """Single access token response (kept for backward compatibility)."""

    access_token: str
    token_type: str = "bearer"


class TokenPair(BaseModel):
    """Access + refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
