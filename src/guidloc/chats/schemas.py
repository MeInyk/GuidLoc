"""Pydantic schemas for chats."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from guidloc.chats.models import MessageRole


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


class MessageCreate(BaseModel):
    """Payload for creating a message."""

    role: MessageRole = MessageRole.USER
    content: str = Field(min_length=1, max_length=20_000)


class MessageRead(BaseModel):
    """Public representation of a message."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    chat_id: int
    role: MessageRole
    content: str
    created_at: datetime


class SendMessageRequest(BaseModel):
    """Payload for sending a user message and getting an assistant reply in one call."""

    content: str = Field(min_length=1, max_length=20_000)


class SendMessageResponse(BaseModel):
    """Result of /chats/{id}/send: the persisted user message and assistant reply."""

    user_message: MessageRead
    assistant_message: MessageRead
