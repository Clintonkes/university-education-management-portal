"""
Reports (/admin/reports) — "Student lists, course registration reports and
academic performance summaries".

The page has three tabs. Each tab can also be downloaded as a CSV file.
Department admins see their department; the Super Admin sees everything
(and can filter by department).
"""

from flask import abort, render_template, request

from ...extensions import db
from ...models import Role, StudentProfile, User
from ...services import reports as report_service
from ...web import all_semesters, csv_response, selected_semester
from ...security import Perm, permission_required
from . import bp
from .helpers import department_filter, limit_to

TABS = ("students", "registrations", "performance")


def _student_rows(dept_ids):
    query = (db.select(User).join(User.student_profile).where(User.role == Role.STUDENT)
             .order_by(StudentProfile.level, StudentProfile.matric_number))
    query = limit_to(query, User.department_id, dept_ids)
    if level := request.args.get("level", type=int):
        query = query.where(StudentProfile.level == level)
    return list(db.session.scalars(query))


@bp.route("/reports")
@permission_required(Perm.REPORTS_VIEW)
def reports():
    tab = request.args.get("tab", "students")
    if tab not in TABS:
        abort(404)
    semester = selected_semester()
    dept_ids = department_filter()

    context = {"tab": tab, "semester": semester, "semesters": all_semesters()}
    if tab == "students":
        context["students"] = _student_rows(dept_ids)
        context["levels"] = report_service.students_per_level(dept_ids)
    elif tab == "registrations" and semester:
        context["rows"] = report_service.course_registration_report(dept_ids, semester)
    elif tab == "performance" and semester:
        context["rows"] = report_service.performance_report(dept_ids, semester)
        context["distribution"] = report_service.grade_distribution(dept_ids, semester)
    return render_template("admin/reports.html", **context)


@bp.route("/reports/<tab>.csv")
@permission_required(Perm.REPORTS_VIEW)
def reports_csv(tab: str):
    semester = selected_semester()
    dept_ids = department_filter()

    if tab == "students":
        rows = [[u.student_profile.matric_number, u.full_name, u.email, u.department.name if u.department else "",
                 u.student_profile.program.name, u.student_profile.level, u.status] for u in _student_rows(dept_ids)]
        return csv_response("student_list.csv",
                            ["Matric No", "Name", "Email", "Department", "Programme", "Level", "Status"], rows)

    if semester is None:
        abort(404)
    if tab == "registrations":
        rows = [[r["course"].code, r["course"].title, r["course"].units, r["course"].level,
                 r["lecturer"].display_name if r["lecturer"] else "Unallocated", r["students"]]
                for r in report_service.course_registration_report(dept_ids, semester)]
        return csv_response("course_registrations.csv",
                            ["Course", "Title", "Units", "Level", "Lecturer", "Students"], rows)
    if tab == "performance":
        rows = [[r["sheet"].course.code, r["sheet"].course.title, r["students"], r["average"], r["pass_rate"],
                 " ".join(f"{g}:{n}" for g, n in sorted(r["grades"].items()))]
                for r in report_service.performance_report(dept_ids, semester)]
        return csv_response("performance_summary.csv",
                            ["Course", "Title", "Students", "Average", "Pass rate %", "Grades"], rows)
    abort(404)
