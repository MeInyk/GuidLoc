"""Pydantic schemas for the user memory module."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from guidloc.memory.models import MemoryItemStatus, MemorySection


class UserProfileRead(BaseModel):
    """Static user profile fields (no statuses)."""

    model_config = ConfigDict(from_attributes=True)

    preferred_name: str | None = None
    date_of_birth: date | None = None
    phone: str | None = None
    address_text: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    """Partial update of the static profile."""

    preferred_name: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=40)
    address_text: str | None = Field(default=None, max_length=300)


class MemoryItemRead(BaseModel):
    """Public representation of a dynamic memory item."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    section: MemorySection
    value: str
    status: MemoryItemStatus
    created_at: datetime
    updated_at: datetime


class MemoryItemCreate(BaseModel):
    """Payload for creating a dynamic memory item."""

    section: MemorySection
    value: str = Field(min_length=1, max_length=2000)
    status: MemoryItemStatus = MemoryItemStatus.POSSIBLE


class MemoryItemUpdate(BaseModel):
    """Partial update of a dynamic memory item."""

    value: str | None = Field(default=None, min_length=1, max_length=2000)
    status: MemoryItemStatus | None = None


class UserMemoryRead(BaseModel):
    """Composite view of all of a user's memory."""

    profile: UserProfileRead
    rules: list[MemoryItemRead]
    preferences: list[MemoryItemRead]
    user_info: list[MemoryItemRead]
    notes: list[MemoryItemRead]
