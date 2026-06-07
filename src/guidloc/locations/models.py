"""ORM models for locations."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, String, Text
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


class LocationChangeRequestType(StrEnum):
    """Kind of change a user proposed for the locations database."""

    CREATE = "create"
    UPDATE = "update"


class LocationChangeRequestStatus(StrEnum):
    """Review lifecycle for a user-submitted location change."""

    PENDING = "pending"
    MERGED = "merged"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


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


class LocationChangeRequest(Base, TimestampMixin):
    """A user-submitted request to add or update a location.

    The request stores a whitelisted patch in `proposed_changes`. Merging is
    intentionally explicit and separate from creation so chat submissions never
    mutate the public locations table directly.
    """

    __tablename__ = "location_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    change_type: Mapped[LocationChangeRequestType] = mapped_column(
        SAEnum(
            LocationChangeRequestType,
            name="location_change_request_type",
            native_enum=False,
            length=20,
        ),
        nullable=False,
    )
    status: Mapped[LocationChangeRequestStatus] = mapped_column(
        SAEnum(
            LocationChangeRequestStatus,
            name="location_change_request_status",
            native_enum=False,
            length=20,
        ),
        default=LocationChangeRequestStatus.PENDING,
        index=True,
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_changes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    original_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    original_location_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    merged_location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    merged_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_location_change_requests_status_type",
            "status",
            "change_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<LocationChangeRequest id={self.id} type={self.change_type} status={self.status}>"
