"""ORM models for locations."""

from enum import StrEnum

from sqlalchemy import JSON, Boolean, Float, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from guidloc.common.database import Base
from guidloc.common.models import TimestampMixin


class LocationCategory(StrEnum):
    """High-level location categories used for filtering and routing."""

    CAFE = "cafe"
    RESTAURANT = "restaurant"
    BAR = "bar"
    PARK = "park"
    MUSEUM = "museum"
    GALLERY = "gallery"
    ATTRACTION = "attraction"
    SHOP = "shop"
    HOTEL = "hotel"
    ENTERTAINMENT = "entertainment"
    OTHER = "other"


class PriceLevel(StrEnum):
    """Approximate price band for visitors."""

    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Location(Base, TimestampMixin):
    """A place in Chernivtsi the assistant can recommend."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    address: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[LocationCategory] = mapped_column(
        SAEnum(LocationCategory, name="location_category", native_enum=False, length=30),
        index=True,
        nullable=False,
    )
    price_level: Mapped[PriceLevel | None] = mapped_column(
        SAEnum(PriceLevel, name="price_level", native_enum=False, length=20),
        nullable=True,
    )
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    def __repr__(self) -> str:
        return f"<Location id={self.id} name={self.name!r} category={self.category}>"
