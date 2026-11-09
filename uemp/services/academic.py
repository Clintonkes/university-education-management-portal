"""
academic.py — University structure and the academic calendar (Super Admin).

    save_faculty()          create / update a faculty
    save_department()       create / update a department inside a faculty
    create_session()        creates "2026/2027" AND its two semesters at once
    set_current_semester()  marks exactly one semester as current
    set_registration()      opens or closes course registration

Only one semester is current at a time. The current semester drives the whole
portal: which courses students can register, which courses lecturers see
first, and which results show on dashboards.
"""

import re
from datetime import date

from ..extensions import db
from ..models import AcademicSession, Department, Faculty, Semester, SemesterTerm, User
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
    name = (name or "").strip()
    match = SESSION_PATTERN.match(name)
    if not match or int(match.group(2)) != int(match.group(1)) + 1:
        raise ServiceError("Session name must look like 2026/2027 (two consecutive years).")
    if db.session.scalar(db.select(AcademicSession).filter_by(name=name)):
        raise ServiceError(f"Session {name} already exists.")
    if start_date and end_date and end_date <= start_date:
        raise ServiceError("End date must be after the start date.")

    session = AcademicSession(name=name, start_date=start_date, end_date=end_date)
    session.semesters = [Semester(term=SemesterTerm.FIRST), Semester(term=SemesterTerm.SECOND)]
    db.session.add(session)
    db.session.flush()
    audit.record(actor, "session.created", f"Created session {name} with two semesters", session)
    return session


def set_current_semester(actor: User, semester: Semester) -> Semester:
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
    semester.registration_open = is_open
    state = "opened" if is_open else "closed"
    audit.record(actor, f"registration.{state}", f"Course registration {state} for {semester.name}", semester)
    return semester
