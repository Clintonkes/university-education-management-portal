"""
accounts.py — Creating and managing user accounts.

Used by both Department Admins (for their own department) and the Super
Admin (for any department). Scope checks are done here as well as in routes,
so a department admin can never create or edit a user outside their
department even if a form is tampered with.

FUNCTIONS
    create_student / update_student
    create_lecturer / update_lecturer
    create_staff_admin        (Super Admin only: department admins, super admins)
    set_status                activate / deactivate / suspend
    change_role               move staff between Lecturer / Dept Admin / Super Admin
    reset_password
"""

import re

from ..extensions import db
from ..models import (
    AccountStatus, Department, LecturerProfile, Program, Role, StudentProfile, User,
)
from ..security.scope import can_access_department
from . import audit
from .errors import ServiceError

MIN_PASSWORD_LENGTH = 8


# --------------------------------------------------------------------------- #
#  Validation helpers
# --------------------------------------------------------------------------- #
def validate_password(password: str) -> None:
    """Simple strength rule: 8+ characters with at least one letter and one number."""
    if len(password or "") < MIN_PASSWORD_LENGTH:
        raise ServiceError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise ServiceError("Password must contain both letters and numbers.")


def _normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def _ensure_email_free(email: str, exclude_user_id: int | None = None) -> None:
    query = db.select(User).filter_by(email=email)
    existing = db.session.scalar(query)
    if existing and existing.id != exclude_user_id:
        raise ServiceError(f"The email {email} is already in use.")


def _ensure_unique(model, column_name: str, value: str, label: str, exclude_id: int | None = None) -> None:
    existing = db.session.scalar(db.select(model).filter_by(**{column_name: value}))
    if existing and existing.id != exclude_id:
        raise ServiceError(f"{label} {value} is already in use.")


def _department_or_error(actor: User, department_id: int | None) -> Department:
    department = db.session.get(Department, department_id) if department_id else None
    if department is None:
        raise ServiceError("Please choose a valid department.")
    if not can_access_department(department.id, actor):
        raise ServiceError("You can only manage records in your own department.")
    return department


def _program_or_error(actor: User, program_id: int | None) -> Program:
    program = db.session.get(Program, program_id) if program_id else None
    if program is None:
        raise ServiceError("Please choose a valid programme.")
    if not can_access_department(program.department_id, actor):
        raise ServiceError("You can only manage programmes in your own department.")
    return program


def _validate_level(level: int, program: Program) -> None:
    if level % 100 != 0 or not 100 <= level <= program.max_level:
        raise ServiceError(f"{program.name} runs from 100 to {program.max_level} Level.")


# --------------------------------------------------------------------------- #
#  Students
# --------------------------------------------------------------------------- #
def create_student(actor: User, *, email, password, first_name, last_name, matric_number,
                   program_id, level, entry_year, phone=None, gender=None) -> User:
    email = _normalise_email(email)
    matric_number = matric_number.strip().upper()
    _ensure_email_free(email)
    _ensure_unique(StudentProfile, "matric_number", matric_number, "Matric number")
    validate_password(password)
    program = _program_or_error(actor, program_id)
    _validate_level(level, program)

    user = User(
        email=email, first_name=first_name.strip(), last_name=last_name.strip(), phone=phone,
        role=Role.STUDENT, status=AccountStatus.ACTIVE,
        # A student's department always follows their programme's department.
        department_id=program.department_id,
    )
    user.set_password(password)
    user.student_profile = StudentProfile(
        matric_number=matric_number, program_id=program.id, level=level,
        entry_year=entry_year, gender=gender,
    )
    db.session.add(user)
    db.session.flush()
    audit.record(actor, "user.created", f"Created student {matric_number} ({user.full_name})", user)
    return user


def update_student(actor: User, student: User, *, email, first_name, last_name, matric_number,
                   program_id, level, entry_year, phone=None, gender=None) -> User:
    if student.role != Role.STUDENT or not student.student_profile:
        raise ServiceError("This account is not a student.")
    if not can_access_department(student.department_id, actor):
        raise ServiceError("You can only manage students in your own department.")

    email = _normalise_email(email)
    matric_number = matric_number.strip().upper()
    profile = student.student_profile
    _ensure_email_free(email, exclude_user_id=student.id)
    _ensure_unique(StudentProfile, "matric_number", matric_number, "Matric number", exclude_id=profile.id)
    program = _program_or_error(actor, program_id)
    _validate_level(level, program)

    student.email, student.first_name, student.last_name, student.phone = (
        email, first_name.strip(), last_name.strip(), phone)
    student.department_id = program.department_id
    profile.matric_number, profile.program_id, profile.level = matric_number, program.id, level
    profile.entry_year, profile.gender = entry_year, gender
    audit.record(actor, "user.updated", f"Updated student {matric_number}", student)
    return student


# --------------------------------------------------------------------------- #
#  Lecturers
# --------------------------------------------------------------------------- #
def create_lecturer(actor: User, *, email, password, first_name, last_name, staff_id,
                    department_id, title=None, rank=None, specialization=None, phone=None) -> User:
    email = _normalise_email(email)
    staff_id = staff_id.strip().upper()
    _ensure_email_free(email)
    _ensure_unique(LecturerProfile, "staff_id", staff_id, "Staff ID")
    validate_password(password)
    department = _department_or_error(actor, department_id)

    user = User(
        email=email, first_name=first_name.strip(), last_name=last_name.strip(), phone=phone,
        role=Role.LECTURER, status=AccountStatus.ACTIVE, department_id=department.id,
    )
    user.set_password(password)
    user.lecturer_profile = LecturerProfile(
        staff_id=staff_id, title=title, rank=rank, specialization=specialization,
    )
    db.session.add(user)
    db.session.flush()
    audit.record(actor, "user.created", f"Created lecturer {staff_id} ({user.full_name})", user)
    return user


def update_lecturer(actor: User, lecturer: User, *, email, first_name, last_name, staff_id,
                    department_id, title=None, rank=None, specialization=None, phone=None) -> User:
    if not lecturer.lecturer_profile:
        raise ServiceError("This account has no lecturer profile.")
    if not can_access_department(lecturer.department_id, actor):
        raise ServiceError("You can only manage lecturers in your own department.")

    email = _normalise_email(email)
    staff_id = staff_id.strip().upper()
    profile = lecturer.lecturer_profile
    _ensure_email_free(email, exclude_user_id=lecturer.id)
    _ensure_unique(LecturerProfile, "staff_id", staff_id, "Staff ID", exclude_id=profile.id)
    department = _department_or_error(actor, department_id)

    lecturer.email, lecturer.first_name, lecturer.last_name, lecturer.phone = (
        email, first_name.strip(), last_name.strip(), phone)
    lecturer.department_id = department.id
    profile.staff_id, profile.title, profile.rank, profile.specialization = staff_id, title, rank, specialization
    audit.record(actor, "user.updated", f"Updated lecturer {staff_id}", lecturer)
    return lecturer


# --------------------------------------------------------------------------- #
#  Administrators (Super Admin only)
# --------------------------------------------------------------------------- #
def create_staff_admin(actor: User, *, role, email, password, first_name, last_name,
                       department_id=None, phone=None) -> User:
    if actor.role != Role.SUPER_ADMIN:
        raise ServiceError("Only the Super Admin can create administrator accounts.")
    if role not in (Role.DEPT_ADMIN, Role.SUPER_ADMIN):
        raise ServiceError("Choose Department Admin or Super Admin.")
    email = _normalise_email(email)
    _ensure_email_free(email)
    validate_password(password)
    if role == Role.DEPT_ADMIN:
        department_id = _department_or_error(actor, department_id).id
    else:
        department_id = None

    user = User(email=email, first_name=first_name.strip(), last_name=last_name.strip(), phone=phone,
                role=role, status=AccountStatus.ACTIVE, department_id=department_id)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    audit.record(actor, "user.created", f"Created {Role(role).label} account for {email}", user)
    return user


# --------------------------------------------------------------------------- #
#  Status, role and password
# --------------------------------------------------------------------------- #
def set_status(actor: User, user: User, status: str) -> User:
    if status not in set(AccountStatus):
        raise ServiceError("Unknown account status.")
    if user.id == actor.id:
        raise ServiceError("You cannot change the status of your own account.")
    if not can_access_department(user.department_id, actor) or (
        user.role in (Role.DEPT_ADMIN, Role.SUPER_ADMIN) and actor.role != Role.SUPER_ADMIN
    ):
        raise ServiceError("You are not allowed to change this account.")
    old = user.status
    user.status = status
    audit.record(actor, "user.status_changed", f"{user.email}: status {old} → {status}", user)
    return user


STAFF_ROLES = (Role.LECTURER, Role.DEPT_ADMIN, Role.SUPER_ADMIN)


def change_role(actor: User, user: User, new_role: str, department_id: int | None = None) -> User:
    """
    Move a staff member between staff roles. Student accounts keep the student
    role because their academic records depend on it.
    """
    if actor.role != Role.SUPER_ADMIN:
        raise ServiceError("Only the Super Admin can change roles.")
    if user.id == actor.id:
        raise ServiceError("You cannot change your own role.")
    if user.role not in STAFF_ROLES or new_role not in STAFF_ROLES:
        raise ServiceError("Roles can only be changed between staff roles.")
    if new_role == Role.LECTURER and not user.lecturer_profile:
        raise ServiceError("Create a lecturer profile first (Admin → Lecturers) before assigning the lecturer role.")

    if new_role == Role.SUPER_ADMIN:
        department_id = user.department_id  # keep for reference, not used for scoping
    else:
        department_id = _department_or_error(actor, department_id or user.department_id).id

    old = user.role
    user.role, user.department_id = new_role, department_id
    audit.record(actor, "user.role_changed", f"{user.email}: role {old} → {new_role}", user)
    return user


def reset_password(actor: User, user: User, new_password: str) -> User:
    """Set a new password. Users may change their own; admins may reset others in scope."""
    validate_password(new_password)
    is_self = actor.id == user.id
    if not is_self:
        if actor.role not in (Role.DEPT_ADMIN, Role.SUPER_ADMIN):
            raise ServiceError("You are not allowed to change this account.")
        if not can_access_department(user.department_id, actor):
            raise ServiceError("You are not allowed to change this account.")
        if user.role in (Role.DEPT_ADMIN, Role.SUPER_ADMIN) and actor.role != Role.SUPER_ADMIN:
            raise ServiceError("Only the Super Admin can reset administrator passwords.")
    user.set_password(new_password)
    user.failed_logins, user.locked_until = 0, None
    action = "user.password_changed" if is_self else "user.password_reset"
    audit.record(actor, action, f"Password {'changed' if is_self else 'reset'} for {user.email}", user)
    return user
