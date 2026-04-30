"""Pydantic schemas for chats."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChatCreate(BaseModel):
    """Payload for creating a chat."""

    title: str = Field(min_length=1, max_length=200)


class ChatUpdate(BaseModel):
    """Payload for partial chat updates."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    is_pinned: bool | None = None


class ChatRead(BaseModel):
    """Public representation of a chat."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    is_pinned: bool
    created_at: datetime
    updated_at: datetime
