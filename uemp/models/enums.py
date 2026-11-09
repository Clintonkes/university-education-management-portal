"""
enums.py — Fixed lists of allowed values (roles, statuses, semesters).

WHAT THIS FILE DOES
    Gives names to values that are stored as text in the database, e.g. a
    user's role is stored as "student" but in code we write Role.STUDENT.

WHY
    Using named constants avoids typos ("studnet") and gives one place to see
    every possible value. StrEnum members behave like normal strings, so they
    can be saved to and compared with database columns directly.
"""

from enum import StrEnum


class Role(StrEnum):
    """The four user levels required by the brief."""

    STUDENT = "student"
    LECTURER = "lecturer"
    DEPT_ADMIN = "dept_admin"
    SUPER_ADMIN = "super_admin"

    @property
    def label(self) -> str:
        """Human friendly name shown in the interface."""
        return {
            Role.STUDENT: "Student",
            Role.LECTURER: "Lecturer",
            Role.DEPT_ADMIN: "Department Admin",
            Role.SUPER_ADMIN: "Super Admin",
        }[self]


class AccountStatus(StrEnum):
    """Only ACTIVE accounts can sign in."""

    ACTIVE = "active"
    INACTIVE = "inactive"      # switched off, e.g. graduated / left
    SUSPENDED = "suspended"    # blocked for disciplinary or security reasons


class SemesterTerm(StrEnum):
    """Every academic session has a first and second semester."""

    FIRST = "first"
    SECOND = "second"

    @property
    def label(self) -> str:
        return "First Semester" if self is SemesterTerm.FIRST else "Second Semester"


class ResultStatus(StrEnum):
    """
    The life cycle of a course's result sheet:

        DRAFT ──submit──▶ SUBMITTED ──approve──▶ APPROVED
          ▲                   │                     │
          └──── RETURNED ◀────┘ reject              │ reopen (authorised)
                   ▲                                │
                   └────────────────────────────────┘
    """

    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    RETURNED = "returned"      # rejected or re-opened; lecturer can edit again

    @property
    def label(self) -> str:
        return {
            ResultStatus.DRAFT: "Draft",
            ResultStatus.SUBMITTED: "Awaiting Review",
            ResultStatus.APPROVED: "Approved",
            ResultStatus.RETURNED: "Returned for Correction",
        }[self]

    @property
    def is_editable(self) -> bool:
        """Lecturers may only change scores while the sheet is draft/returned."""
        return self in (ResultStatus.DRAFT, ResultStatus.RETURNED)
