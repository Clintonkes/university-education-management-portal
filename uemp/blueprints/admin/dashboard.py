"""
Department dashboard (/admin/).

Shows headline numbers, results waiting for review and recent activity for the
admin's department, followed by the full Department Report.

The Super Admin picks a department from the drop-down: the page then shows
THAT department's dashboard and report. Without a choice, it shows a
side-by-side comparison of every department.
"""

from flask import render_template
from sqlalchemy import or_

from ...extensions import db
from ...models import AuditLog, Course, Department, ResultSheet, ResultStatus, Semester, User
from ...security import is_university_wide
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
                 .where(ResultSheet.semester_id == semester.id,
                        or_(ResultSheet.status == ResultStatus.SUBMITTED, ResultSheet.correction_requested_at.is_not(None)))
                 .order_by(ResultSheet.submitted_at))
        pending = list(db.session.scalars(query))

    # Recent actions by people in this department (or anywhere, for super admin).
    activity_q = db.select(AuditLog).join(AuditLog.actor).order_by(AuditLog.created_at.desc()).limit(8)
    if dept_ids is not None:
        activity_q = activity_q.where(User.department_id.in_(dept_ids))

    # One department in view (always for a dept admin; when picked for the super admin)?
    department = db.session.get(Department, dept_ids[0]) if dept_ids and len(dept_ids) == 1 else None
    show_comparison = is_university_wide() and department is None

    return render_template(
        "admin/dashboard.html",
        department=department,
        report=reports.department_report(dept_ids, semester) if department else None,
        comparison=reports.department_comparison(semester) if show_comparison else None,
        semester=semester,
        counts=reports.overview_counts(dept_ids, semester),
        status_breakdown=reports.result_status_breakdown(dept_ids, semester),
        levels=reports.students_per_level(dept_ids),
        pending=pending,
        activity=list(db.session.scalars(activity_q)),
    )
