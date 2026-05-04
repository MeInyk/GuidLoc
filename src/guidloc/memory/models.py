"""ORM models for user memory: a static profile and a list of dynamic items."""

from datetime import date
from enum import StrEnum

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from guidloc.common.database import Base
from guidloc.common.models import TimestampMixin


class MemorySection(StrEnum):
    """Logical group a dynamic memory item belongs to.

    - rule: things the user explicitly told the assistant to ALWAYS do
      (e.g. "always answer in Ukrainian", "never suggest seafood places").
    - preference: what the user likes / dislikes / avoids
      (e.g. "loves cheesecakes", "prefers quiet cafes").
    - user_info: concrete personal facts about the user or close people
      (e.g. "has a sister Anna", "allergic to peanuts").
    - note: short, often temporary reminders the user asked to keep
      (e.g. "wants to visit the new mall", "doctor appointment next Tuesday").
    """

    RULE = "rule"
    PREFERENCE = "preference"
    USER_INFO = "user_info"
    NOTE = "note"


class MemoryItemStatus(StrEnum):
    """Trust level of a dynamic memory item.

    - possible: a soft assumption inferred from one signal; only the
      orchestrator sees these. Recommendation agents must NOT use them.
    - confirmed: repeated or explicitly stated by the user; safe to use
      in recommendations.
    - archived: superseded or deleted; never returned to agents, kept
      only for analytics. Set by the backend when a delete is requested.
    """

    POSSIBLE = "possible"
    CONFIRMED = "confirmed"
    ARCHIVED = "archived"


class UserProfile(Base, TimestampMixin):
    """Static, single-row personal data for a user (no statuses)."""

    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    preferred_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    address_text: Mapped[str | None] = mapped_column(String(300), nullable=True)

    def __repr__(self) -> str:
        return f"<UserProfile user_id={self.user_id}>"


class UserMemoryItem(Base, TimestampMixin):
    """One dynamic memory fact for a user."""

    __tablename__ = "user_memory_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    section: Mapped[MemorySection] = mapped_column(
        SAEnum(MemorySection, name="memory_section", native_enum=False, length=20),
        nullable=False,
    )
    value: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[MemoryItemStatus] = mapped_column(
        SAEnum(MemoryItemStatus, name="memory_item_status", native_enum=False, length=20),
        nullable=False,
        default=MemoryItemStatus.POSSIBLE,
    )

    __table_args__ = (
        Index(
            "ix_user_memory_items_user_section_status",
            "user_id",
            "section",
            "status",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserMemoryItem id={self.id} user_id={self.user_id} "
            f"section={self.section} status={self.status}>"
        )
