"""
results.py — Workflows 2 & 3: Result entry, submission and approval.

LECTURER SIDE (Workflow 2)
    open_sheet()   -> find or create the course's result sheet and make sure
                      every registered student has a row on it.
    save_scores()  -> validate CA/exam marks, compute total + grade, then either
                      keep as DRAFT or SUBMIT for departmental review.

DEPARTMENT SIDE (Workflow 3)
    approve()      -> SUBMITTED → APPROVED   (students can now see results)
    reject()       -> SUBMITTED → RETURNED   (lecturer gets feedback, can fix)
    reopen()       -> APPROVED  → RETURNED   (authorised correction after approval)

CORRECTION REQUESTS (lecturer asks, department decides)
    request_correction()  lecturer asks to edit SUBMITTED or APPROVED results
    grant_correction()    -> RETURNED, so the lecturer can edit and resubmit
    decline_correction()  results stay locked; the lecturer sees the reason

RULES ENFORCED HERE (not only in the pages)
    * Only the lecturer allocated to the course that semester may enter scores.
    * Scores can only change while the sheet is DRAFT or RETURNED.
    * Every student must have both scores before submitting.
    * Only an admin for the course's department (or super admin) may review.
    * Nobody can approve a sheet they submitted themselves.
    * A reason is required to reject or reopen.
    * Every submission, approval, rejection, reopening and score change is
      written to the audit log.
"""

from flask import current_app

from ..extensions import db
from ..models import (
    Course, CourseAllocation, CourseRegistration, ResultEntry, ResultSheet, ResultStatus,
    Semester, User,
)
from ..models.mixins import utcnow
from ..security.scope import can_access_department
from . import audit
from .errors import ServiceError
from .grading import grade_for


# --------------------------------------------------------------------------- #
#  Lecturer helpers
# --------------------------------------------------------------------------- #
def allocations_for_lecturer(lecturer: User, semester: Semester | None = None) -> list[CourseAllocation]:
    """Courses assigned to a lecturer (optionally in one semester)."""
    query = (
        db.select(CourseAllocation)
        .join(CourseAllocation.course)
        .where(CourseAllocation.lecturer_id == lecturer.id)
        .order_by(CourseAllocation.semester_id.desc(), Course.code)
    )
    if semester is not None:
        query = query.where(CourseAllocation.semester_id == semester.id)
    return list(db.session.scalars(query))


def get_allocation(lecturer: User, allocation_id: int) -> CourseAllocation:
    """Return the allocation only if it belongs to this lecturer (Rule 3)."""
    allocation = db.session.get(CourseAllocation, allocation_id)
    if allocation is None or allocation.lecturer_id != lecturer.id:
        raise ServiceError("You are not assigned to this course.")
    return allocation


def registrations_for_course(course_id: int, semester_id: int) -> list[CourseRegistration]:
    """Students registered for a course in a semester, sorted by matric number."""
    from ..models import StudentProfile  # local import keeps the top of file short

    from sqlalchemy.orm import contains_eager

    query = (
        db.select(CourseRegistration)
        .join(User, CourseRegistration.student_id == User.id)
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(CourseRegistration.course_id == course_id)
        .where(CourseRegistration.semester_id == semester_id)
        .order_by(StudentProfile.matric_number)
        .options(contains_eager(CourseRegistration.student).contains_eager(User.student_profile))
    )
    return list(db.session.scalars(query).unique())


def with_entry_details():
    """
    Load a sheet's rows with each student's registration, account and profile
    in a few queries in total. Without this, every row costs about 3 extra
    queries (a class of 200 would mean ~600 database round trips per page).
    """
    from sqlalchemy.orm import joinedload, selectinload

    from ..models import StudentProfile

    return selectinload(ResultSheet.entries).joinedload(ResultEntry.registration).options(
        joinedload(CourseRegistration.student).joinedload(User.student_profile).joinedload(StudentProfile.program),
        joinedload(CourseRegistration.course),
    )


def find_sheet(course_id: int, semester_id: int) -> ResultSheet | None:
    return db.session.scalar(db.select(ResultSheet).filter_by(course_id=course_id, semester_id=semester_id)
                             .options(with_entry_details()))


def load_sheet(sheet_id: int) -> ResultSheet | None:
    return db.session.scalar(db.select(ResultSheet).filter_by(id=sheet_id).options(with_entry_details()))


def open_sheet(allocation: CourseAllocation) -> ResultSheet:
    """
    Get the result sheet for an allocated course, creating it if needed, and
    add an empty row for any student who registered since it was created.
    """
    sheet = find_sheet(allocation.course_id, allocation.semester_id)
    if sheet is None:
        sheet = ResultSheet(
            course_id=allocation.course_id,
            semester_id=allocation.semester_id,
            lecturer_id=allocation.lecturer_id,
            status=ResultStatus.DRAFT,
        )
        db.session.add(sheet)
    elif sheet.status_enum.is_editable and sheet.lecturer_id != allocation.lecturer_id:
        # Course was re-allocated to a new lecturer before results were final.
        sheet.lecturer_id = allocation.lecturer_id

    if sheet.status_enum.is_editable:
        have_rows = {entry.registration_id for entry in sheet.entries}
        for registration in registrations_for_course(allocation.course_id, allocation.semester_id):
            if registration.id not in have_rows:
                sheet.entries.append(ResultEntry(registration=registration))
    db.session.flush()
    return sheet


def _parse_score(raw, maximum: float, label: str, who: str) -> float | None:
    """Turn the text typed in a score box into a number, or None if blank."""
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = float(str(raw).strip())
    except ValueError:
        raise ServiceError(f"{label} for {who} must be a number.") from None
    if value < 0 or value > maximum:
        raise ServiceError(f"{label} for {who} must be between 0 and {maximum:g}.")
    return round(value, 2)


def _fmt(value) -> str:
    return "—" if value is None else f"{value:g}"


def save_scores(sheet: ResultSheet, scores: dict[int, tuple], lecturer: User, submit: bool = False) -> ResultSheet:
    """
    Save CA and exam scores for a sheet.

    `scores` maps entry ID -> (ca_text, exam_text) exactly as typed in the form.
    If `submit` is True the sheet moves to SUBMITTED and becomes read-only.
    """
    # Rule 3: only the currently allocated lecturer.
    allocation = db.session.scalar(
        db.select(CourseAllocation).filter_by(course_id=sheet.course_id, semester_id=sheet.semester_id)
    )
    if allocation is None or allocation.lecturer_id != lecturer.id or sheet.lecturer_id != lecturer.id:
        raise ServiceError("You are not assigned to this course.")
    if not sheet.status_enum.is_editable:
        raise ServiceError(f"These results are '{sheet.status_enum.label}' and can no longer be edited.")

    max_ca = current_app.config["MAX_CA_SCORE"]
    max_exam = current_app.config["MAX_EXAM_SCORE"]
    changes: list[str] = []

    for entry in sheet.entries:
        if entry.id not in scores:
            continue
        who = entry.registration.student.student_profile.matric_number
        ca_raw, exam_raw = scores[entry.id]
        ca = _parse_score(ca_raw, max_ca, "CA score", who)
        exam = _parse_score(exam_raw, max_exam, "Exam score", who)

        if (ca, exam) != (entry.ca_score, entry.exam_score):
            # Only log a change if a previous value existed (i.e. a modification).
            if entry.ca_score is not None or entry.exam_score is not None:
                changes.append(
                    f"{who}: CA {_fmt(entry.ca_score)}→{_fmt(ca)}, Exam {_fmt(entry.exam_score)}→{_fmt(exam)}"
                )
            entry.ca_score, entry.exam_score = ca, exam

        # Total and grade are only calculated once both parts are present.
        if entry.is_complete:
            entry.total = round(entry.ca_score + entry.exam_score, 2)
            entry.grade, entry.grade_point = grade_for(entry.total)
        else:
            entry.total = entry.grade = entry.grade_point = None

    code = sheet.course.code
    if changes:
        audit.record(lecturer, "result.modified",
                     f"{code} ({sheet.semester.name}) scores changed — " + "; ".join(changes), sheet)

    if submit:
        if not sheet.entries:
            raise ServiceError("There are no registered students on this sheet to submit.")
        missing = [e.registration.student.student_profile.matric_number for e in sheet.entries if not e.is_complete]
        if missing:
            raise ServiceError(f"Enter both CA and exam scores for every student before submitting. Missing: {', '.join(missing[:5])}"
                               + (" …" if len(missing) > 5 else ""))
        sheet.status = ResultStatus.SUBMITTED
        sheet.submitted_at = utcnow()
        audit.record(lecturer, "result.submitted",
                     f"Submitted {code} results ({len(sheet.entries)} students) for {sheet.semester.name}", sheet)
    else:
        audit.record(lecturer, "result.draft_saved", f"Saved draft scores for {code} ({sheet.semester.name})", sheet)
    return sheet


# --------------------------------------------------------------------------- #
#  Department review helpers
# --------------------------------------------------------------------------- #
def _check_reviewer(sheet: ResultSheet, reviewer: User) -> None:
    """Rules 5 & 'cannot approve own results'."""
    if not can_access_department(sheet.course.department_id, reviewer):
        raise ServiceError("You can only review results for your own department.")
    if sheet.lecturer_id == reviewer.id:
        raise ServiceError("You cannot review results that you submitted yourself.")


def _clear_request(sheet: ResultSheet) -> None:
    sheet.correction_requested_at = None
    sheet.correction_reason = None


def approve(sheet: ResultSheet, reviewer: User, comment: str | None = None) -> ResultSheet:
    _check_reviewer(sheet, reviewer)
    if sheet.status != ResultStatus.SUBMITTED:  # Rule 4: must be submitted first
        raise ServiceError("Only submitted results can be approved.")
    if sheet.correction_pending:
        raise ServiceError("The lecturer has asked to correct these results. Allow or refuse the request first.")
    sheet.status = ResultStatus.APPROVED
    sheet.reviewed_by_id = reviewer.id
    sheet.reviewed_at = utcnow()
    sheet.review_comment = (comment or "").strip() or None
    audit.record(reviewer, "result.approved",
                 f"Approved {sheet.course.code} results for {sheet.semester.name}", sheet)
    return sheet


def reject(sheet: ResultSheet, reviewer: User, comment: str) -> ResultSheet:
    _check_reviewer(sheet, reviewer)
    if sheet.status != ResultStatus.SUBMITTED:
        raise ServiceError("Only submitted results can be rejected.")
    if not (comment or "").strip():
        raise ServiceError("Please explain what the lecturer needs to correct.")
    sheet.status = ResultStatus.RETURNED
    sheet.reviewed_by_id = reviewer.id
    sheet.reviewed_at = utcnow()
    sheet.review_comment = comment.strip()
    _clear_request(sheet)
    audit.record(reviewer, "result.rejected",
                 f"Returned {sheet.course.code} results for correction: {comment.strip()}", sheet)
    return sheet


def reopen(sheet: ResultSheet, reviewer: User, reason: str) -> ResultSheet:
    """Authorised reopening of APPROVED results so the lecturer can correct them."""
    _check_reviewer(sheet, reviewer)
    if sheet.status != ResultStatus.APPROVED:
        raise ServiceError("Only approved results can be reopened.")
    if not (reason or "").strip():
        raise ServiceError("A reason is required to reopen approved results.")
    sheet.status = ResultStatus.RETURNED
    sheet.reviewed_by_id = reviewer.id
    sheet.reviewed_at = utcnow()
    sheet.review_comment = f"Reopened: {reason.strip()}"
    _clear_request(sheet)
    audit.record(reviewer, "result.reopened",
                 f"Reopened approved {sheet.course.code} results: {reason.strip()}", sheet)
    return sheet


# --------------------------------------------------------------------------- #
#  Correction requests: "I submitted, but I need to fix something"
# --------------------------------------------------------------------------- #
def request_correction(sheet: ResultSheet, lecturer: User, reason: str) -> ResultSheet:
    """The lecturer asks the department for permission to edit locked results."""
    if sheet.lecturer_id != lecturer.id:
        raise ServiceError("You are not assigned to this course.")
    if sheet.status not in (ResultStatus.SUBMITTED, ResultStatus.APPROVED):
        raise ServiceError("You can still edit these results; no permission is needed.")
    if sheet.correction_pending:
        raise ServiceError("You have already asked. Please wait for the department's decision.")
    reason = (reason or "").strip()
    if len(reason) < 10:
        raise ServiceError("Please explain what needs correcting (at least 10 characters).")
    sheet.correction_requested_at = utcnow()
    sheet.correction_reason = reason
    audit.record(lecturer, "result.correction_requested",
                 f"Asked to correct {sheet.course.code} ({sheet.semester.name}) results: {reason}", sheet)
    return sheet


def grant_correction(sheet: ResultSheet, reviewer: User, comment: str | None = None) -> ResultSheet:
    """Allow the correction: the sheet goes back to the lecturer for editing."""
    _check_reviewer(sheet, reviewer)
    if not sheet.correction_pending:
        raise ServiceError("There is no correction request to answer.")
    was = sheet.status_enum.label.lower()
    note = (comment or "").strip()
    sheet.status = ResultStatus.RETURNED
    sheet.reviewed_by_id = reviewer.id
    sheet.reviewed_at = utcnow()
    sheet.review_comment = f"Correction allowed: {sheet.correction_reason}" + (f" — {note}" if note else "")
    _clear_request(sheet)
    audit.record(reviewer, "result.correction_granted",
                 f"Allowed the lecturer to correct {sheet.course.code} results (were {was})", sheet)
    return sheet


def decline_correction(sheet: ResultSheet, reviewer: User, reason: str) -> ResultSheet:
    _check_reviewer(sheet, reviewer)
    if not sheet.correction_pending:
        raise ServiceError("There is no correction request to answer.")
    if not (reason or "").strip():
        raise ServiceError("Please tell the lecturer why the request is refused.")
    sheet.review_comment = f"Correction request refused: {reason.strip()}"
    sheet.reviewed_by_id = reviewer.id
    sheet.reviewed_at = utcnow()
    _clear_request(sheet)
    audit.record(reviewer, "result.correction_declined",
                 f"Refused correction of {sheet.course.code} results: {reason.strip()}", sheet)
    return sheet


def sheet_summary(sheet: ResultSheet) -> dict:
    """
    Performance numbers for one course's sheet (shown to lecturers and admins).

        average    = sum of totals ÷ number of students with both scores
        pass rate  = students whose grade point is above 0 ÷ students scored × 100
        median     = the middle total when totals are sorted
        spread     = standard deviation: how far totals are from the average
    """
    from statistics import median, pstdev

    complete = [e for e in sheet.entries if e.is_complete]
    totals = [e.total for e in complete]
    grades: dict[str, int] = {}
    for entry in complete:
        grades[entry.grade] = grades.get(entry.grade, 0) + 1
    passed = sum(1 for e in complete if (e.grade_point or 0) > 0)
    ranked = sorted(complete, key=lambda e: e.total, reverse=True)
    by_level: dict[int, list[float]] = {}
    for entry in complete:
        by_level.setdefault(entry.registration.student.student_profile.level, []).append(entry.total)
    return {
        "students": len(sheet.entries),
        "scored": len(complete),
        "missing": len(sheet.entries) - len(complete),
        "average": round(sum(totals) / len(totals), 1) if totals else None,
        "median": round(median(totals), 1) if totals else None,
        "spread": round(pstdev(totals), 1) if len(totals) > 1 else None,
        "highest": max(totals, default=None),
        "lowest": min(totals, default=None),
        "passed": passed,
        "failed": len(complete) - passed,
        "pass_rate": round(100 * passed / len(complete)) if complete else None,
        "grades": grades,
        "top": ranked[:3],
        "bottom": [e for e in ranked[-3:][::-1] if e not in ranked[:3]],
        "by_level": {level: round(sum(v) / len(v), 1) for level, v in sorted(by_level.items())},
    }
