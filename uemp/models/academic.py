"""
academic.py — The university's structure and calendar.

TABLES IN THIS FILE
    Faculty          e.g. "Faculty of Science"
    Department       belongs to one Faculty   e.g. "Computer Science"
    Program          belongs to one Department e.g. "B.Sc. Computer Science"
    AcademicSession  a school year            e.g. "2025/2026"
    Semester         belongs to one Session   e.g. "First Semester 2025/2026"

HOW THEY CONNECT
    Faculty 1──* Department 1──* Program
    AcademicSession 1──* Semester (a first and/or a second)
"""

from datetime import date, datetime

from sqlalchemy import UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .enums import SemesterTerm
from .mixins import TimestampMixin


class Faculty(TimestampMixin, db.Model):
    __tablename__ = "faculties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(db.String(12), unique=True, nullable=False)

    departments: Mapped[list["Department"]] = relationship(
        back_populates="faculty", order_by="Department.name"
    )

    def __repr__(self) -> str:
        return f"<Faculty {self.code}>"


class Department(TimestampMixin, db.Model):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(120), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(db.String(12), unique=True, nullable=False)
    faculty_id: Mapped[int] = mapped_column(db.ForeignKey("faculties.id"), nullable=False, index=True)

    faculty: Mapped[Faculty] = relationship(back_populates="departments")
    programs: Mapped[list["Program"]] = relationship(
        back_populates="department", order_by="Program.name"
    )

    def __repr__(self) -> str:
        return f"<Department {self.code}>"


class Program(TimestampMixin, db.Model):
    """A degree programme a student is admitted into."""

    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(150), nullable=False)
    code: Mapped[str] = mapped_column(db.String(20), unique=True, nullable=False)
    degree: Mapped[str] = mapped_column(db.String(20), default="B.Sc.", nullable=False)
    duration_years: Mapped[int] = mapped_column(default=4, nullable=False)
    department_id: Mapped[int] = mapped_column(db.ForeignKey("departments.id"), nullable=False, index=True)

    department: Mapped[Department] = relationship(back_populates="programs")

    @property
    def max_level(self) -> int:
        """Highest level for this programme, e.g. a 4-year course ends at 400 Level."""
        return self.duration_years * 100

    def __repr__(self) -> str:
        return f"<Program {self.code}>"


class AcademicSession(TimestampMixin, db.Model):
    __tablename__ = "academic_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(20), unique=True, nullable=False)  # "2025/2026"
    start_date: Mapped[date | None] = mapped_column(db.Date)
    end_date: Mapped[date | None] = mapped_column(db.Date)
    is_current: Mapped[bool] = mapped_column(default=False, nullable=False)
    # A completed session is closed: its semesters are finished and locked.
    is_completed: Mapped[bool] = mapped_column(default=False, server_default=false(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(db.DateTime)

    semesters: Mapped[list["Semester"]] = relationship(
        back_populates="session", order_by="Semester.term", cascade="all, delete-orphan"
    )

    @property
    def status_label(self) -> str:
        if self.is_completed:
            return "Completed"
        if self.is_current:
            return "Current"
        return "Upcoming"

    def __repr__(self) -> str:
        return f"<Session {self.name}>"


class Semester(TimestampMixin, db.Model):
    __tablename__ = "semesters"
    __table_args__ = (
        # A session cannot have two "first" semesters.
        UniqueConstraint("session_id", "term", name="uq_semester_session_term"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(db.ForeignKey("academic_sessions.id"), nullable=False)
    term: Mapped[str] = mapped_column(db.String(10), nullable=False)  # SemesterTerm value
    # Only ONE semester in the whole system is "current" at any time.
    is_current: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Students can only add/drop courses while this is True.
    registration_open: Mapped[bool] = mapped_column(default=False, nullable=False)
    # Optional calendar dates for the semester.
    start_date: Mapped[date | None] = mapped_column(db.Date)
    end_date: Mapped[date | None] = mapped_column(db.Date)
    # A completed semester is finished: registration stays closed for good.
    is_completed: Mapped[bool] = mapped_column(default=False, server_default=false(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(db.DateTime)

    session: Mapped[AcademicSession] = relationship(back_populates="semesters")

    @property
    def term_label(self) -> str:
        return SemesterTerm(self.term).label

    @property
    def status_label(self) -> str:
        """Plain-English state shown on the sessions page."""
        if self.is_completed:
            return "Completed"
        if self.is_current:
            return "Current"
        return "Not started"

    @property
    def name(self) -> str:
        """Full display name, e.g. 'First Semester 2025/2026'."""
        return f"{self.term_label} {self.session.name}"

    @classmethod
    def current(cls) -> "Semester | None":
        """Return the semester marked as current, or None if none is set."""
        return db.session.scalar(db.select(cls).filter_by(is_current=True))

    def __repr__(self) -> str:
        return f"<Semester {self.term} {self.session_id}>"
