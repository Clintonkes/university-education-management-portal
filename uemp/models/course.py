"""
course.py — Courses, who teaches them, and who registered for them.

TABLES IN THIS FILE
    Course              a course in the catalogue, e.g. "CSC 201 – Data Structures"
    course_programs     link table: which programmes a course is offered to
    CourseAllocation    which lecturer teaches a course in a given semester
    CourseRegistration  which student registered a course in a given semester

KEY RULES ENFORCED BY THE DATABASE
    * A course code is unique.
    * A course has at most one lecturer per semester.
    * A student cannot register the same course twice in the same semester
      (unique constraint) — the service layer also checks this first so the
      user gets a friendly message instead of an error.
"""

from sqlalchemy import UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..extensions import db
from .academic import Department, Program, Semester
from .enums import SemesterTerm
from .mixins import TimestampMixin
from .user import User

# Many-to-many link: a course can be offered to several programmes, and a
# programme takes many courses. e.g. GST 101 is offered to every programme.
course_programs = db.Table(
    "course_programs",
    db.Column("course_id", db.ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True),
    db.Column("program_id", db.ForeignKey("programs.id", ondelete="CASCADE"), primary_key=True),
)


class Course(TimestampMixin, db.Model):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(db.String(15), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(db.String(150), nullable=False)
    units: Mapped[int] = mapped_column(nullable=False)          # credit units
    level: Mapped[int] = mapped_column(nullable=False, index=True)
    semester_term: Mapped[str] = mapped_column(db.String(10), nullable=False)  # first/second
    description: Mapped[str | None] = mapped_column(db.Text)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    # The department that owns (manages) this course.
    department_id: Mapped[int] = mapped_column(db.ForeignKey("departments.id"), nullable=False, index=True)

    department: Mapped[Department] = relationship()
    programs: Mapped[list[Program]] = relationship(secondary=course_programs)

    @property
    def term_label(self) -> str:
        return SemesterTerm(self.semester_term).label

    def __repr__(self) -> str:
        return f"<Course {self.code}>"


class CourseAllocation(TimestampMixin, db.Model):
    """Assigns ONE lecturer to teach a course during ONE semester."""

    __tablename__ = "course_allocations"
    __table_args__ = (UniqueConstraint("course_id", "semester_id", name="uq_allocation_course_semester"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(db.ForeignKey("courses.id"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(db.ForeignKey("semesters.id"), nullable=False, index=True)
    lecturer_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False, index=True)

    course: Mapped[Course] = relationship()
    semester: Mapped[Semester] = relationship()
    lecturer: Mapped[User] = relationship()


class CourseRegistration(TimestampMixin, db.Model):
    """A student taking a course in a semester. Results hang off this row."""

    __tablename__ = "course_registrations"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", "semester_id", name="uq_registration_once_per_semester"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(db.ForeignKey("courses.id"), nullable=False, index=True)
    semester_id: Mapped[int] = mapped_column(db.ForeignKey("semesters.id"), nullable=False, index=True)
    # Set by administrators: why the student is taking the course, and a note.
    registration_type: Mapped[str] = mapped_column(db.String(20), default="regular",
                                                   server_default=text("'regular'"), nullable=False)
    remarks: Mapped[str | None] = mapped_column(db.Text)

    student: Mapped[User] = relationship()
    course: Mapped[Course] = relationship()
    semester: Mapped[Semester] = relationship()
    result: Mapped["ResultEntry | None"] = relationship(  # noqa: F821  (defined in result.py)
        back_populates="registration", uselist=False
    )

    TYPES = {"regular": "Regular", "carryover": "Carry-over (resit)", "elective": "Elective"}

    @property
    def type_label(self) -> str:
        return self.TYPES.get(self.registration_type, self.registration_type.title())
