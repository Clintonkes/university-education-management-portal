"""
registration.py — Workflow 1: Student Course Registration.

STEP BY STEP
    1. Student logs in (handled by auth).
    2. We look up the student's department, programme and level.
    3. `eligible_courses()` lists courses the student may take this semester.
    4. Student ticks courses and submits.
    5. `register_courses()` checks every rule below, then saves.
    6. The courses appear on the student's dashboard.
    7. Department admins see them in Admin → Registrations.

RULES CHECKED (Business rules 1 and 2)
    * Registration must be OPEN for the current semester.
    * A course must be active, offered to the student's programme, at the
      student's level, and in the current semester (first/second).
    * The same course cannot be registered twice in one semester.
    * Total units cannot exceed MAX_UNITS_PER_SEMESTER.
    * A student can only register for themselves — routes always pass the
      logged-in user, never a student ID from the browser.
"""

from flask import current_app

from ..extensions import db
from ..models import Course, CourseRegistration, Program, Semester, User
from . import audit
from .errors import ServiceError


def _profile_or_error(student: User):
    if not student.student_profile:
        raise ServiceError("Your student record is incomplete. Please contact your department.")
    return student.student_profile


def eligible_courses(student: User, semester: Semester) -> list[Course]:
    """Courses this student is allowed to register in the given semester."""
    profile = _profile_or_error(student)
    query = (
        db.select(Course)
        .where(Course.is_active.is_(True))
        .where(Course.level == profile.level)
        .where(Course.semester_term == semester.term)
        .where(Course.programs.any(Program.id == profile.program_id))
        .order_by(Course.code)
    )
    return list(db.session.scalars(query))


def registrations_for(student: User, semester: Semester) -> list[CourseRegistration]:
    """Courses the student has already registered in the given semester."""
    query = (
        db.select(CourseRegistration)
        .join(CourseRegistration.course)
        .where(CourseRegistration.student_id == student.id)
        .where(CourseRegistration.semester_id == semester.id)
        .order_by(Course.code)
    )
    return list(db.session.scalars(query))


def register_courses(student: User, course_ids: list[int], semester: Semester | None) -> list[CourseRegistration]:
    """
    Register the selected courses for the logged-in student.
    Either ALL selected courses are registered or NONE are (no half results).
    """
    if semester is None:
        raise ServiceError("There is no active semester at the moment.")
    if not semester.registration_open:
        raise ServiceError("Course registration is closed for this semester.")

    # Remove repeated IDs (e.g. a course ticked twice by a tampered form).
    requested = list(dict.fromkeys(int(cid) for cid in course_ids))
    if not requested:
        raise ServiceError("Select at least one course to register.")

    eligible = {course.id: course for course in eligible_courses(student, semester)}
    not_allowed = [cid for cid in requested if cid not in eligible]
    if not_allowed:
        # Someone sent an ID that is not on their list — never trust the browser.
        raise ServiceError("One or more selected courses are not available to you this semester.")

    existing = registrations_for(student, semester)
    already = {reg.course_id for reg in existing}
    duplicates = [eligible[cid].code for cid in requested if cid in already]
    if duplicates:
        raise ServiceError(f"You have already registered: {', '.join(duplicates)}.")

    current_units = sum(reg.course.units for reg in existing)
    new_units = sum(eligible[cid].units for cid in requested)
    limit = current_app.config["MAX_UNITS_PER_SEMESTER"]
    if current_units + new_units > limit:
        raise ServiceError(
            f"This would bring you to {current_units + new_units} units. "
            f"The maximum is {limit} units per semester."
        )

    created = []
    for cid in requested:
        registration = CourseRegistration(student_id=student.id, course_id=cid, semester_id=semester.id)
        db.session.add(registration)
        created.append(registration)

    codes = ", ".join(eligible[cid].code for cid in requested)
    audit.record(student, "registration.created", f"Registered {codes} for {semester.name}")
    return created


def drop_course(student: User, registration_id: int) -> CourseRegistration:
    """Remove one of the student's own registrations while registration is open."""
    registration = db.session.get(CourseRegistration, registration_id)
    # Same message whether it doesn't exist or belongs to someone else, so we
    # don't reveal other students' records.
    if registration is None or registration.student_id != student.id:
        raise ServiceError("Registration not found.")
    if not registration.semester.registration_open:
        raise ServiceError("Course registration is closed, so courses can no longer be dropped.")
    if registration.result is not None and registration.result.is_complete:
        raise ServiceError("Scores have already been recorded for this course; it cannot be dropped.")

    if registration.result is not None:
        db.session.delete(registration.result)
    db.session.delete(registration)
    audit.record(student, "registration.dropped",
                 f"Dropped {registration.course.code} for {registration.semester.name}")
    return registration
