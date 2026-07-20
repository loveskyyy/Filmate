"""SQLAlchemy declarative base."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DEFAULT_USER_ID = 1


class Base(DeclarativeBase):
    pass


def utc_now() -> datetime:
    return datetime.now(UTC)


def dt_to_iso(val: datetime | None) -> str | None:
    """Convert datetime to ISO string for JSON serialization."""
    return val.isoformat() if val else None


class TimestampMixin:
    """Unified created/updated timestamps."""

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class UserOwnedMixin:
    """User ownership marker."""

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        server_default=str(DEFAULT_USER_ID),
        index=True,
    )
