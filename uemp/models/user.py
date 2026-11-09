"""
user.py — People who use the portal.

TABLES IN THIS FILE
    User             one row per login account (all four roles)
    StudentProfile   extra details only students have (matric no., program, level)
    LecturerProfile  extra details only lecturers have (staff ID, rank)

DESIGN NOTE
    We keep a single "users" table for login and roles, then attach a profile
    table for role-specific details. This keeps authentication in one place
    while letting each role grow its own fields without touching the others.

SECURITY NOTE
    Passwords are never stored. We store a salted hash (scrypt via Werkzeug),
    which cannot be turned back into the original password.
"""

from datetime import date, datetime, timedelta

from flask import current_app
from flask_login import UserMixin
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from .academic import Department, Program
from .enums import AccountStatus, Role
from .mixins import TimestampMixin, utcnow


class User(UserMixin, TimestampMixin, db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(db.String(150), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    first_name: Mapped[str] = mapped_column(db.String(60), nullable=False)
    last_name: Mapped[str] = mapped_column(db.String(60), nullable=False)
    phone: Mapped[str | None] = mapped_column(db.String(20))
    role: Mapped[str] = mapped_column(db.String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(db.String(20), default=AccountStatus.ACTIVE, nullable=False)

    # Students, lecturers and department admins belong to one department.
    # Super admins work across the whole university, so this can be empty.
    department_id: Mapped[int | None] = mapped_column(db.ForeignKey("departments.id"), index=True)

    # Login safety: count wrong passwords and lock the account for a while.
    failed_logins: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(db.DateTime)
    last_login_at: Mapped[datetime | None] = mapped_column(db.DateTime)

    department: Mapped[Department | None] = relationship()
    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    lecturer_profile: Mapped["LecturerProfile | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    # ---- Password helpers --------------------------------------------------
    def set_password(self, raw_password: str) -> None:
        """Hash and store a new password (scrypt by default; tests use a faster method)."""
        method = current_app.config.get("PASSWORD_HASH_METHOD", "scrypt")
        self.password_hash = generate_password_hash(raw_password, method=method)

    def check_password(self, raw_password: str) -> bool:
        """True if the typed password matches the stored hash."""
        return check_password_hash(self.password_hash, raw_password)

    # ---- Lockout helpers ---------------------------------------------------
    def is_locked(self) -> bool:
        return bool(self.locked_until and self.locked_until > utcnow())

    def register_failed_login(self, max_attempts: int, lock_minutes: int) -> None:
        """Count a wrong password; lock the account once the limit is reached."""
        self.failed_logins += 1
        if self.failed_logins >= max_attempts:
            self.locked_until = utcnow() + timedelta(minutes=lock_minutes)
            self.failed_logins = 0

    def register_successful_login(self) -> None:
        self.failed_logins = 0
        self.locked_until = None
        self.last_login_at = utcnow()

    # ---- Role helpers ------------------------------------------------------
    @property
    def is_active(self) -> bool:
        """Flask-Login refuses to log in (or keep logged in) inactive users."""
        return self.status == AccountStatus.ACTIVE

    def has_role(self, *roles: Role) -> bool:
        return self.role in roles

    @property
    def role_label(self) -> str:
        return Role(self.role).label

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        """Name with academic title for lecturers, e.g. 'Dr. Ada Obi'."""
        if self.lecturer_profile and self.lecturer_profile.title:
            return f"{self.lecturer_profile.title} {self.full_name}"
        return self.full_name

    @property
    def initials(self) -> str:
        return (self.first_name[:1] + self.last_name[:1]).upper()

    def __repr__(self) -> str:
        return f"<User {self.email} ({self.role})>"


class StudentProfile(TimestampMixin, db.Model):
    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), unique=True, nullable=False)
    matric_number: Mapped[str] = mapped_column(db.String(30), unique=True, nullable=False, index=True)
    program_id: Mapped[int] = mapped_column(db.ForeignKey("programs.id"), nullable=False, index=True)
    level: Mapped[int] = mapped_column(nullable=False, index=True)  # 100, 200, ...
    entry_year: Mapped[int] = mapped_column(nullable=False)

    # Fields the student is allowed to update themselves.
    address: Mapped[str | None] = mapped_column(db.String(255))
    date_of_birth: Mapped[date | None] = mapped_column(db.Date)
    gender: Mapped[str | None] = mapped_column(db.String(10))
    next_of_kin: Mapped[str | None] = mapped_column(db.String(120))
    next_of_kin_phone: Mapped[str | None] = mapped_column(db.String(20))

    user: Mapped[User] = relationship(back_populates="student_profile")
    program: Mapped[Program] = relationship()

    def __repr__(self) -> str:
        return f"<Student {self.matric_number}>"


class LecturerProfile(TimestampMixin, db.Model):
    __tablename__ = "lecturer_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(db.ForeignKey("users.id"), unique=True, nullable=False)
    staff_id: Mapped[str] = mapped_column(db.String(30), unique=True, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(db.String(20))       # Dr., Prof., Mr., Mrs.
    rank: Mapped[str | None] = mapped_column(db.String(60))        # e.g. Senior Lecturer
    specialization: Mapped[str | None] = mapped_column(db.String(120))

    user: Mapped[User] = relationship(back_populates="lecturer_profile")

    def __repr__(self) -> str:
        return f"<Lecturer {self.staff_id}>"
