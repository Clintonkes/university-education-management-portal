"""
audit.py — A permanent diary of important actions.

Every result submission, approval, rejection, score change and admin change
writes one AuditLog row: WHO did WHAT to WHICH record, WHEN, and from WHERE
(IP address). Rows are only ever added, never edited — this is what makes the
system "traceable" as the business rules require.
"""

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .mixins import utcnow
from .user import User


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"), index=True)
    # A copy of the person's name and role at the time, so the entry still
    # reads correctly if their account is later deleted.
    actor_name: Mapped[str | None] = mapped_column(db.String(150))
    actor_role: Mapped[str | None] = mapped_column(db.String(20))
    action: Mapped[str] = mapped_column(db.String(60), nullable=False, index=True)  # e.g. "result.approved"
    entity_type: Mapped[str | None] = mapped_column(db.String(40))                  # e.g. "ResultSheet"
    entity_id: Mapped[int | None] = mapped_column()
    description: Mapped[str] = mapped_column(db.Text, nullable=False)
    ip_address: Mapped[str | None] = mapped_column(db.String(45))
    created_at: Mapped[datetime] = mapped_column(db.DateTime, default=utcnow, nullable=False, index=True)

    actor: Mapped[User | None] = relationship()

    @property
    def who(self) -> str:
        """Name of the person who did this (or 'System' for automatic actions)."""
        if self.actor is not None:
            return self.actor.display_name
        return self.actor_name or "System"

    @property
    def who_role(self) -> str:
        from .enums import Role
        role = self.actor.role if self.actor is not None else self.actor_role
        try:
            return Role(role).label if role else ""
        except ValueError:
            return role or ""
