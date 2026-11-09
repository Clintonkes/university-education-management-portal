"""
Department dashboard (/admin/).

Shows headline numbers, results waiting for review and recent activity for the
admin's department. The Super Admin sees the same page across all departments.
"""

from flask import render_template

from ...extensions import db
from ...models import AuditLog, Course, ResultSheet, ResultStatus, Semester, User
from ...services import reports
from . import bp
from .helpers import department_filter, limit_to


@bp.route("/")
def dashboard():
    semester = Semester.current()
    dept_ids = department_filter()

    pending = []
    if semester:
        query = (limit_to(db.select(ResultSheet).join(ResultSheet.course), Course.department_id, dept_ids)
                 .where(ResultSheet.semester_id == semester.id, ResultSheet.status == ResultStatus.SUBMITTED)
                 .order_by(ResultSheet.submitted_at))
        pending = list(db.session.scalars(query))

    # Recent actions by people in this department (or anywhere, for super admin).
    activity_q = db.select(AuditLog).join(AuditLog.actor).order_by(AuditLog.created_at.desc()).limit(8)
    if dept_ids is not None:
        activity_q = activity_q.where(User.department_id.in_(dept_ids))

    return render_template(
        "admin/dashboard.html",
        semester=semester,
        counts=reports.overview_counts(dept_ids, semester),
        status_breakdown=reports.result_status_breakdown(dept_ids, semester),
        levels=reports.students_per_level(dept_ids),
        pending=pending,
        activity=list(db.session.scalars(activity_q)),
    )
