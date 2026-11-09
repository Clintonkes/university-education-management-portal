"""
Workflow 3 — Departmental Result Approval (/admin/results).

    1. Department admin opens "Result Approval" and sees pending submissions.
    2. Selects a course.
    3. Reviews every student's CA, exam, total and grade, plus a summary.
    4. Approves  -> results become visible to students.
       Rejects   -> lecturer sees the feedback and can correct & resubmit.
       Reopens   -> (approved sheets only) sends back for authorised correction.

All three actions go through services/results.py, which re-checks department
scope and that the reviewer is not the person who submitted.
"""

from flask import redirect, render_template, request, url_for
from flask_login import current_user

from ...extensions import db
from ...models import AuditLog, Course, ResultSheet, ResultStatus
from ...security import Perm, ensure_department_access, permission_required
from ...services import results as result_service
from ...web import all_semesters, attempt, get_or_404, selected_semester
from . import bp
from .forms import ReviewForm
from .helpers import department_filter, limit_to


@bp.route("/results")
@permission_required(Perm.RESULTS_REVIEW)
def results():
    semester = selected_semester()
    status = request.args.get("status", ResultStatus.SUBMITTED.value)
    sheets = []
    if semester:
        query = (limit_to(db.select(ResultSheet).join(ResultSheet.course), Course.department_id, department_filter())
                 .where(ResultSheet.semester_id == semester.id).order_by(Course.code))
        if status != "all":
            query = query.where(ResultSheet.status == status)
        sheets = list(db.session.scalars(query))
    return render_template("admin/results.html", sheets=sheets, semester=semester, semesters=all_semesters(),
                           status=status, statuses=list(ResultStatus))


def _load_sheet(sheet_id: int) -> ResultSheet:
    sheet = get_or_404(ResultSheet, sheet_id)
    ensure_department_access(sheet.course.department_id)
    return sheet


@bp.route("/results/<int:sheet_id>")
@permission_required(Perm.RESULTS_REVIEW)
def results_review(sheet_id: int):
    sheet = _load_sheet(sheet_id)
    entries = sorted(sheet.entries, key=lambda e: e.registration.student.student_profile.matric_number)
    trail = list(db.session.scalars(
        db.select(AuditLog).where(AuditLog.entity_type == "ResultSheet", AuditLog.entity_id == sheet.id)
        .order_by(AuditLog.created_at.desc())))
    return render_template("admin/result_review.html", sheet=sheet, entries=entries, form=ReviewForm(),
                           summary=result_service.sheet_summary(sheet), trail=trail)


@bp.route("/results/<int:sheet_id>/decision", methods=["POST"])
@permission_required(Perm.RESULTS_REVIEW)
def results_decision(sheet_id: int):
    sheet = _load_sheet(sheet_id)
    form = ReviewForm()
    decision = request.form.get("decision")
    comment = form.comment.data or ""

    actions = {
        "approve": (lambda: result_service.approve(sheet, current_user, comment),
                    f"{sheet.course.code} results approved and published to students."),
        "reject": (lambda: result_service.reject(sheet, current_user, comment),
                   f"{sheet.course.code} results returned to the lecturer for correction."),
        "reopen": (lambda: result_service.reopen(sheet, current_user, comment),
                   f"{sheet.course.code} results reopened for correction."),
    }
    if form.validate_on_submit() and decision in actions:
        action, message = actions[decision]
        attempt(action, message)
    return redirect(url_for("admin.results_review", sheet_id=sheet.id))
