"""
result.py — Examination results and their approval status.

TABLES IN THIS FILE
    ResultSheet   one per (course, semester). Holds the approval STATUS and
                  who submitted / reviewed it. Think of it as the paper score
                  sheet a lecturer hands to the department.
    ResultEntry   one row per student on that sheet: CA, exam, total, grade.

WHY A SEPARATE "SHEET"
    Approval happens for a whole course at once, not student by student. Putting
    the status on the sheet means one approval updates every student's result
    and makes the rule "students only see approved results" a single check.
"""

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .academic import Semester
from .course import Course, CourseRegistration
from .enums import ResultStatus
from .mixins import TimestampMixin
from .user import User


class ResultSheet(TimestampMixin, db.Model):
    __tablename__ = "result_sheets"
    __table_args__ = (UniqueConstraint("course_id", "semester_id", name="uq_sheet_course_semester"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(db.ForeignKey("courses.id"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(db.ForeignKey("semesters.id"), nullable=False, index=True)
    lecturer_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(db.String(20), default=ResultStatus.DRAFT, nullable=False, index=True)

    submitted_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    # Feedback from the department admin when rejecting / reopening.
    review_comment: Mapped[str | None] = mapped_column(db.Text)
    # A lecturer may ask permission to correct results after submitting them.
    correction_requested_at: Mapped[datetime | None] = mapped_column(db.DateTime)
    correction_reason: Mapped[str | None] = mapped_column(db.Text)

    course: Mapped[Course] = relationship()
    semester: Mapped[Semester] = relationship()
    lecturer: Mapped[User] = relationship(foreign_keys=[lecturer_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    entries: Mapped[list["ResultEntry"]] = relationship(
        back_populates="sheet", cascade="all, delete-orphan"
    )

    @property
    def status_enum(self) -> ResultStatus:
        return ResultStatus(self.status)

    @property
    def correction_pending(self) -> bool:
        """True while a lecturer's request to edit locked results awaits a decision."""
        return self.correction_requested_at is not None


class ResultEntry(TimestampMixin, db.Model):
    __tablename__ = "result_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    sheet_id: Mapped[int] = mapped_column(db.ForeignKey("result_sheets.id"), nullable=False, index=True)
    # One result per registration: a student cannot have two results for the
    # same course in the same semester.
    registration_id: Mapped[int] = mapped_column(
        db.ForeignKey("course_registrations.id"), unique=True, nullable=False
    )
    ca_score: Mapped[float | None] = mapped_column(db.Float)
    exam_score: Mapped[float | None] = mapped_column(db.Float)
    total: Mapped[float | None] = mapped_column(db.Float)
    grade: Mapped[str | None] = mapped_column(db.String(2))
    grade_point: Mapped[float | None] = mapped_column(db.Float)

    sheet: Mapped[ResultSheet] = relationship(back_populates="entries")
    registration: Mapped[CourseRegistration] = relationship(back_populates="result")

    @property
    def is_complete(self) -> bool:
        return self.ca_score is not None and self.exam_score is not None
