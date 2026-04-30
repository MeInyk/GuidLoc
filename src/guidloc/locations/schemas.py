"""Pydantic schemas for locations."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from guidloc.locations.models import LocationCategory, PriceLevel


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
