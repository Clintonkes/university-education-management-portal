"""
academic.py — University structure and the academic calendar (Super Admin).

    save_faculty() / delete_faculty()
    save_department() / delete_department()
    create_session()        creates "2026/2027" AND its two semesters at once
    update_session() / delete_session()
    add_semester() / update_semester() / delete_semester()
    set_current_semester()  marks exactly one semester as current
    set_registration()      opens or closes course registration
    complete_semester() / reopen_semester()   mark a semester finished (or undo)
    complete_session()  / reopen_session()    mark a whole session finished (or undo)

DELETING IS DELIBERATELY CAREFUL
    Records that other records depend on cannot be deleted (a faculty that
    still has departments, a semester that already has registrations...).
    The error message says what must be moved or removed first, so academic
    history can never be lost by accident.

Only one semester is current at a time. The current semester drives the whole
portal: which courses students can register, which courses lecturers see
first, and which results show on dashboards.
"""

import re
from datetime import date

from ..extensions import db
from ..models import (
    AcademicSession, Course, CourseAllocation, CourseRegistration, Department, Faculty, Program,
    ResultSheet, Semester, SemesterTerm, User,
)
from ..models.mixins import utcnow
from . import audit
from .errors import ServiceError

SESSION_PATTERN = re.compile(r"^(\d{4})/(\d{4})$")


def _ensure_free(model, field: str, value: str, exclude_id: int | None, label: str) -> None:
    existing = db.session.scalar(db.select(model).filter_by(**{field: value}))
    if existing and existing.id != exclude_id:
        raise ServiceError(f"{label} '{value}' already exists.")


def save_faculty(actor: User, faculty: Faculty | None, *, name: str, code: str) -> Faculty:
    name, code = name.strip(), code.strip().upper()
    _ensure_free(Faculty, "name", name, faculty.id if faculty else None, "Faculty")
    _ensure_free(Faculty, "code", code, faculty.id if faculty else None, "Faculty code")
    is_new = faculty is None
    faculty = faculty or Faculty()
    faculty.name, faculty.code = name, code
    db.session.add(faculty)
    db.session.flush()
    audit.record(actor, "faculty.created" if is_new else "faculty.updated", f"Faculty {code} – {name} saved", faculty)
    return faculty


def save_department(actor: User, department: Department | None, *, name: str, code: str, faculty_id: int) -> Department:
    if db.session.get(Faculty, faculty_id) is None:
        raise ServiceError("Choose a valid faculty.")
    name, code = name.strip(), code.strip().upper()
    _ensure_free(Department, "name", name, department.id if department else None, "Department")
    _ensure_free(Department, "code", code, department.id if department else None, "Department code")
    is_new = department is None
    department = department or Department()
    department.name, department.code, department.faculty_id = name, code, faculty_id
    db.session.add(department)
    db.session.flush()
    audit.record(actor, "department.created" if is_new else "department.updated",
                 f"Department {code} – {name} saved", department)
    return department


def create_session(actor: User, name: str, start_date: date | None = None, end_date: date | None = None) -> AcademicSession:
    name = _validate_session_name(name)
    _validate_dates(start_date, end_date)

    session = AcademicSession(name=name, start_date=start_date, end_date=end_date)
    session.semesters = [Semester(term=SemesterTerm.FIRST), Semester(term=SemesterTerm.SECOND)]
    db.session.add(session)
    db.session.flush()
    audit.record(actor, "session.created", f"Created session {name} with two semesters", session)
    return session


def _validate_session_name(name: str, exclude_id: int | None = None) -> str:
    name = (name or "").strip()
    match = SESSION_PATTERN.match(name)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        raise ServiceError("Session name must look like 2026/2027 (two consecutive years).")
    existing = db.session.scalar(db.select(AcademicSession).filter_by(name=name))
    if existing and existing.id != exclude_id:
        raise ServiceError(f"Session {name} already exists.")
    return name


def _validate_dates(start: date | None, end: date | None) -> None:
    if start and end and end <= start:
        raise ServiceError("End date must be after the start date.")


def _count(query) -> int:
    return db.session.scalar(query) or 0


def semester_usage(semester: Semester) -> dict[str, int]:
    """How many records belong to a semester (used before deleting it)."""
    return {
        "registrations": _count(db.select(db.func.count(CourseRegistration.id)).filter_by(semester_id=semester.id)),
        "allocations": _count(db.select(db.func.count(CourseAllocation.id)).filter_by(semester_id=semester.id)),
        "result sheets": _count(db.select(db.func.count(ResultSheet.id)).filter_by(semester_id=semester.id)),
    }


def _in_use_message(what: str, usage: dict[str, int]) -> str | None:
    used = [f"{n} {label}" for label, n in usage.items() if n]
    return f"{what} cannot be deleted because it already has {', '.join(used)}." if used else None


def update_session(actor: User, session: AcademicSession, *, name: str, start_date: date | None,
                   end_date: date | None) -> AcademicSession:
    name = _validate_session_name(name, exclude_id=session.id)
    _validate_dates(start_date, end_date)
    old = session.name
    session.name, session.start_date, session.end_date = name, start_date, end_date
    audit.record(actor, "session.updated", f"Session {old} updated" + (f" (renamed to {name})" if old != name else ""),
                 session)
    return session


def delete_session(actor: User, session: AcademicSession) -> None:
    """Only an unused session can be deleted (no registrations, allocations or results)."""
    if session.is_current or any(s.is_current for s in session.semesters):
        raise ServiceError("The current session cannot be deleted. Make another semester current first.")
    usage: dict[str, int] = {}
    for semester in session.semesters:
        for label, n in semester_usage(semester).items():
            usage[label] = usage.get(label, 0) + n
    if message := _in_use_message(f"Session {session.name}", usage):
        raise ServiceError(message)
    audit.record(actor, "session.deleted", f"Deleted session {session.name}", session)
    db.session.delete(session)


def add_semester(actor: User, session: AcademicSession, term: str) -> Semester:
    """Add a missing First or Second semester to a session (e.g. after deleting one)."""
    if term not in set(SemesterTerm):
        raise ServiceError("Choose First or Second semester.")
    if any(s.term == term for s in session.semesters):
        raise ServiceError(f"{session.name} already has a {SemesterTerm(term).label}.")
    if session.is_completed:
        raise ServiceError(f"{session.name} is completed. Reopen it before adding a semester.")
    semester = Semester(term=term)
    session.semesters.append(semester)
    db.session.flush()
    audit.record(actor, "semester.created", f"Added {semester.name}", semester)
    return semester


def update_semester(actor: User, semester: Semester, *, start_date: date | None, end_date: date | None) -> Semester:
    _validate_dates(start_date, end_date)
    session = semester.session
    for value in (start_date, end_date):
        if value and ((session.start_date and value < session.start_date) or (session.end_date and value > session.end_date)):
            raise ServiceError(f"Semester dates must fall within the session ({session.start_date or '…'} to "
                               f"{session.end_date or '…'}).")
    semester.start_date, semester.end_date = start_date, end_date
    audit.record(actor, "semester.updated", f"Dates updated for {semester.name}", semester)
    return semester


def delete_semester(actor: User, semester: Semester) -> None:
    if semester.is_current:
        raise ServiceError("The current semester cannot be deleted. Make another semester current first.")
    if message := _in_use_message(semester.name, semester_usage(semester)):
        raise ServiceError(message)
    audit.record(actor, "semester.deleted", f"Deleted {semester.name}", semester)
    semester.session.semesters.remove(semester)
    db.session.delete(semester)


def complete_semester(actor: User, semester: Semester) -> Semester:
    """Mark a semester finished. Registration closes and cannot be reopened."""
    if semester.is_completed:
        raise ServiceError(f"{semester.name} is already completed.")
    semester.is_completed = True
    semester.completed_at = utcnow()
    semester.registration_open = False
    audit.record(actor, "semester.completed", f"{semester.name} marked as completed", semester)
    return semester


def reopen_semester(actor: User, semester: Semester) -> Semester:
    if not semester.is_completed:
        raise ServiceError(f"{semester.name} is not completed.")
    semester.is_completed = False
    semester.completed_at = None
    if semester.session.is_completed:  # a session cannot be complete while a semester is open
        semester.session.is_completed = False
        semester.session.completed_at = None
    audit.record(actor, "semester.reopened", f"{semester.name} reopened", semester)
    return semester


def complete_session(actor: User, session: AcademicSession) -> AcademicSession:
    """A session is completed once every one of its semesters is completed."""
    if session.is_completed:
        raise ServiceError(f"{session.name} is already completed.")
    open_semesters = [s.term_label for s in session.semesters if not s.is_completed]
    if open_semesters:
        raise ServiceError(f"Complete these semesters first: {', '.join(open_semesters)}.")
    if not session.semesters:
        raise ServiceError(f"{session.name} has no semesters.")
    session.is_completed = True
    session.completed_at = utcnow()
    audit.record(actor, "session.completed", f"Session {session.name} marked as completed", session)
    return session


def reopen_session(actor: User, session: AcademicSession) -> AcademicSession:
    if not session.is_completed:
        raise ServiceError(f"{session.name} is not completed.")
    session.is_completed = False
    session.completed_at = None
    audit.record(actor, "session.reopened", f"Session {session.name} reopened", session)
    return session


def delete_faculty(actor: User, faculty: Faculty) -> None:
    if faculty.departments:
        raise ServiceError(f"{faculty.name} still has {len(faculty.departments)} department(s). "
                           "Delete or move them first.")
    audit.record(actor, "faculty.deleted", f"Deleted faculty {faculty.code} – {faculty.name}", faculty)
    db.session.delete(faculty)


def delete_department(actor: User, department: Department) -> None:
    usage = {
        "programmes": _count(db.select(db.func.count(Program.id)).filter_by(department_id=department.id)),
        "courses": _count(db.select(db.func.count(Course.id)).filter_by(department_id=department.id)),
        "user accounts": _count(db.select(db.func.count(User.id)).filter_by(department_id=department.id)),
    }
    if message := _in_use_message(department.name, usage):
        raise ServiceError(message + " Remove or move them first.")
    audit.record(actor, "department.deleted", f"Deleted department {department.code} – {department.name}", department)
    db.session.delete(department)


def set_current_semester(actor: User, semester: Semester) -> Semester:
    if semester.is_completed:
        raise ServiceError(f"{semester.name} is completed. Reopen it before making it current.")
    # Switch every other semester (and session) off, then switch this one on.
    db.session.execute(db.update(Semester).values(is_current=False))
    db.session.execute(db.update(AcademicSession).values(is_current=False))
    semester.is_current = True
    semester.session.is_current = True
    audit.record(actor, "semester.current_set", f"Current semester set to {semester.name}", semester)
    return semester


def set_registration(actor: User, semester: Semester, is_open: bool) -> Semester:
    if is_open and not semester.is_current:
        raise ServiceError("Registration can only be opened for the current semester.")
    if is_open and semester.is_completed:
        raise ServiceError(f"{semester.name} is completed, so registration cannot be reopened.")
    semester.registration_open = is_open
    state = "opened" if is_open else "closed"
    audit.record(actor, f"registration.{state}", f"Course registration {state} for {semester.name}", semester)
    return semester
