"""
catalogue.py — Programmes, courses and course allocations.

    save_program()     create or update a programme
    save_course()      create or update a course and the programmes it is offered to
    allocate_course()  assign a lecturer to a course for a semester
    remove_allocation()

All functions check that the admin is allowed to manage the department
involved (department admins: own department only; super admin: any).
"""

from flask import current_app

from ..extensions import db
from ..models import (
    AccountStatus, Course, CourseAllocation, Department, Program, ResultStatus, Role, Semester,
    SemesterTerm, User,
)
from ..security.scope import can_access_department
from . import audit
from .errors import ServiceError
from .results import find_sheet


def _check_department(actor: User, department_id: int | None) -> Department:
    department = db.session.get(Department, department_id) if department_id else None
    if department is None:
        raise ServiceError("Please choose a valid department.")
    if not can_access_department(department.id, actor):
        raise ServiceError("You can only manage your own department.")
    return department


def _ensure_code_free(model, code: str, exclude_id: int | None, label: str) -> None:
    existing = db.session.scalar(db.select(model).filter_by(code=code))
    if existing and existing.id != exclude_id:
        raise ServiceError(f"{label} code {code} is already in use.")


# --------------------------------------------------------------------------- #
#  Programmes
# --------------------------------------------------------------------------- #
def save_program(actor: User, program: Program | None, *, name, code, degree, duration_years, department_id) -> Program:
    if program is not None and not can_access_department(program.department_id, actor):
        raise ServiceError("You can only manage programmes in your own department.")
    department = _check_department(actor, department_id)
    code = code.strip().upper()
    _ensure_code_free(Program, code, program.id if program else None, "Programme")
    if not 1 <= int(duration_years) <= 7:
        raise ServiceError("Programme duration must be between 1 and 7 years.")

    is_new = program is None
    program = program or Program()
    program.name, program.code, program.degree = name.strip(), code, degree.strip()
    program.duration_years, program.department_id = int(duration_years), department.id
    db.session.add(program)
    db.session.flush()
    audit.record(actor, "program.created" if is_new else "program.updated",
                 f"{'Created' if is_new else 'Updated'} programme {code} – {program.name}", program)
    return program


# --------------------------------------------------------------------------- #
#  Courses
# --------------------------------------------------------------------------- #
def save_course(actor: User, course: Course | None, *, code, title, units, level, semester_term,
                department_id, program_ids, description=None, is_active=True) -> Course:
    if course is not None and not can_access_department(course.department_id, actor):
        raise ServiceError("You can only manage courses in your own department.")
    department = _check_department(actor, department_id)

    # Normalise the code to the "CSC 201" style so duplicates are caught.
    code = " ".join(code.upper().split())
    _ensure_code_free(Course, code, course.id if course else None, "Course")
    if not 1 <= int(units) <= 6:
        raise ServiceError("Course units must be between 1 and 6.")
    if int(level) not in current_app.config["ACADEMIC_LEVELS"]:
        raise ServiceError("Choose a valid level.")
    if semester_term not in set(SemesterTerm):
        raise ServiceError("Choose first or second semester.")

    programs = list(db.session.scalars(db.select(Program).where(Program.id.in_(program_ids or []))))
    if not programs:
        raise ServiceError("Select at least one programme that offers this course.")
    # NOTE: a department may offer the courses it OWNS to programmes in other
    # departments (e.g. MTH 101 taken by Computer Science students). It still
    # cannot edit the other department's courses, students or programmes.

    is_new = course is None
    course = course or Course()
    course.code, course.title, course.units, course.level = code, title.strip(), int(units), int(level)
    course.semester_term, course.department_id = semester_term, department.id
    course.description, course.is_active, course.programs = description or None, bool(is_active), programs
    db.session.add(course)
    db.session.flush()
    audit.record(actor, "course.created" if is_new else "course.updated",
                 f"{'Created' if is_new else 'Updated'} course {code} – {course.title}", course)
    return course


# --------------------------------------------------------------------------- #
#  Course allocation (who teaches what)
# --------------------------------------------------------------------------- #
def allocate_course(actor: User, *, course_id: int, lecturer_id: int, semester: Semester | None) -> CourseAllocation:
    if semester is None:
        raise ServiceError("Set a current semester before allocating courses.")
    course = db.session.get(Course, course_id)
    if course is None or not can_access_department(course.department_id, actor):
        raise ServiceError("Choose a course from your department.")
    if course.semester_term != semester.term:
        raise ServiceError(f"{course.code} is a {course.term_label} course and cannot be allocated in the {semester.term_label}.")

    lecturer = db.session.get(User, lecturer_id)
    if lecturer is None or lecturer.role != Role.LECTURER or lecturer.status != AccountStatus.ACTIVE:
        raise ServiceError("Choose an active lecturer.")
    if not can_access_department(lecturer.department_id, actor):
        raise ServiceError("You can only allocate lecturers from your own department.")

    allocation = db.session.scalar(
        db.select(CourseAllocation).filter_by(course_id=course.id, semester_id=semester.id))
    sheet = find_sheet(course.id, semester.id)
    if allocation and sheet and not sheet.status_enum.is_editable:
        raise ServiceError(f"{course.code} results are already {sheet.status_enum.label.lower()}; the lecturer cannot be changed now.")

    if allocation is None:
        allocation = CourseAllocation(course_id=course.id, semester_id=semester.id, lecturer_id=lecturer.id)
        db.session.add(allocation)
        action = "allocation.created"
    else:
        allocation.lecturer_id = lecturer.id
        action = "allocation.changed"
    if sheet is not None:
        sheet.lecturer_id = lecturer.id  # draft sheet moves to the new lecturer
    db.session.flush()
    audit.record(actor, action, f"{course.code} ({semester.name}) assigned to {lecturer.display_name}", allocation)
    return allocation


def remove_allocation(actor: User, allocation: CourseAllocation) -> None:
    if not can_access_department(allocation.course.department_id, actor):
        raise ServiceError("You can only manage your own department's allocations.")
    sheet = find_sheet(allocation.course_id, allocation.semester_id)
    if sheet is not None and (sheet.status != ResultStatus.DRAFT or any(e.is_complete for e in sheet.entries)):
        raise ServiceError("Scores have already been entered for this course; reassign it instead of removing it.")
    if sheet is not None:
        db.session.delete(sheet)
    db.session.delete(allocation)
    audit.record(actor, "allocation.removed",
                 f"Removed {allocation.course.code} allocation from {allocation.lecturer.display_name}")
