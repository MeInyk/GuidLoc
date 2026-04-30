"""Pydantic schemas for the auth module."""

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    """Payload for password-based login."""

    email: EmailStr
    password: str


class Token(BaseModel):
    """JWT access token response."""

    access_token: str
    token_type: str = "bearer"
