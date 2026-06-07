"""Pydantic schemas for locations."""

from datetime import datetime
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from guidloc.locations.models import (
    LocationCategory,
    LocationChangeRequestStatus,
    LocationChangeRequestType,
    PriceLevel,
)

LOCATION_CHANGE_FIELDS = {
    "name",
    "description",
    "address",
    "latitude",
    "longitude",
    "category",
    "price_level",
    "tags",
    "is_active",
}
REQUIRED_CREATE_CHANGE_FIELDS = {"name", "address", "latitude", "longitude", "category"}
NON_NULL_LOCATION_CHANGE_FIELDS = LOCATION_CHANGE_FIELDS - {"price_level"}


class LocationRead(BaseModel):
    """Public representation of a location."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    address: str
    latitude: float
    longitude: float
    category: LocationCategory
    price_level: PriceLevel | None
    tags: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LocationListItem(BaseModel):
    """Compact representation for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: str
    category: LocationCategory
    price_level: PriceLevel | None
    tags: list[str]


class LocationCreate(BaseModel):
    """Internal schema used by the seed script. Not exposed via HTTP."""

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    address: str = ""
    latitude: float
    longitude: float
    category: LocationCategory
    price_level: PriceLevel | None = None
    tags: list[str] = Field(default_factory=list)
    is_active: bool = True


class LocationProposalFields(BaseModel):
    """Whitelisted fields a user can propose for a new or existing location."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=20_000)
    address: str | None = Field(default=None, min_length=1, max_length=300)
    latitude: float | None = None
    longitude: float | None = None
    category: LocationCategory | None = None
    price_level: PriceLevel | None = None
    tags: list[str] | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def reject_nulls_for_non_nullable_location_fields(self) -> Self:
        null_fields = [
            field
            for field in NON_NULL_LOCATION_CHANGE_FIELDS
            if field in self.model_fields_set and getattr(self, field) is None
        ]
        if null_fields:
            joined = ", ".join(sorted(null_fields))
            raise ValueError(f"These fields cannot be null: {joined}")
        return self

    def to_changes(self) -> dict[str, Any]:
        """Return only explicitly provided fields, normalised for JSON storage."""
        data = self.model_dump(exclude_unset=True, mode="json")
        if "tags" in data and data["tags"] is not None:
            seen: set[str] = set()
            tags: list[str] = []
            for raw_tag in data["tags"]:
                tag = raw_tag.strip().lower()
                if not tag or tag in seen:
                    continue
                seen.add(tag)
                tags.append(tag)
            data["tags"] = tags
        return data


class LocationChangeRequestCreate(BaseModel):
    """Create a pending user proposal to add or update a location."""

    change_type: LocationChangeRequestType
    location_id: int | None = Field(default=None, ge=1)
    reason: str = Field(min_length=1, max_length=2000)
    proposed_changes: LocationProposalFields

    @model_validator(mode="after")
    def validate_by_change_type(self) -> Self:
        changes = self.proposed_changes.to_changes()
        if self.change_type is LocationChangeRequestType.CREATE:
            if self.location_id is not None:
                raise ValueError("location_id must be omitted when creating a new location")
            missing = sorted(REQUIRED_CREATE_CHANGE_FIELDS - changes.keys())
            if missing:
                joined = ", ".join(missing)
                raise ValueError(f"Missing required fields for new location: {joined}")

        if self.change_type is LocationChangeRequestType.UPDATE:
            if self.location_id is None:
                raise ValueError("location_id is required when updating an existing location")
            if not changes:
                raise ValueError("At least one proposed change is required")
        return self


class LocationChangeRequestRead(BaseModel):
    """Public representation of a location change request."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_by_user_id: int
    location_id: int | None
    change_type: LocationChangeRequestType
    status: LocationChangeRequestStatus
    reason: str
    proposed_changes: dict[str, Any]
    original_snapshot: dict[str, Any] | None
    original_location_updated_at: datetime | None
    merged_location_id: int | None
    merged_by_user_id: int | None
    merged_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LocationChangeRequestAmend(BaseModel):
    """Merge extra user-provided fields into a pending change request."""

    reason: str | None = Field(default=None, min_length=1, max_length=2000)
    proposed_changes: LocationProposalFields = Field(default_factory=LocationProposalFields)

    @model_validator(mode="after")
    def require_reason_or_changes(self) -> Self:
        if self.reason is None and not self.proposed_changes.to_changes():
            raise ValueError("Provide a reason or at least one proposed change")
        return self


class LocationChangeRequestMergeRequest(BaseModel):
    """Options for applying a pending change request."""

    force: bool = False


class LocationChangeRequestMergeResult(BaseModel):
    """Result of applying a change request to the real locations table."""

    change_request: LocationChangeRequestRead
    location: LocationRead
