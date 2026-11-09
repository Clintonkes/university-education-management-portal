"""
mixins.py — Small reusable pieces shared by many models.

TimestampMixin adds "created_at" and "updated_at" columns so we always know
when a record was created and last changed (useful for audits and support).
"""

from datetime import datetime, timezone

from sqlalchemy.orm import Mapped, mapped_column

from ..extensions import db


def utcnow() -> datetime:
    """Current time in UTC. We always store UTC to avoid time-zone confusion."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
