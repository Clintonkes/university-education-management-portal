"""
Super Admin routes — Workflow 4: Super Admin Management.

    /super/                      university-wide dashboard
    /super/faculties             faculties and their departments (create, edit, delete)
    /super/sessions              academic sessions and semesters:
                                   create / edit / delete, make current,
                                   open / close registration, mark completed
    /super/sessions/<id>         everything that happened in one session
    /super/semesters/<id>        everything that happened in one semester
    /super/users                 every account: status, role, password
    /super/roles                 the role → permission matrix (RBAC)
    /super/audit                 audit trail of all important actions

Department-level tools (students, lecturers, courses, results, reports) are in
the shared `admin` blueprint, where the Super Admin sees all departments.
"""

from datetime import datetime, timedelta

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from ...extensions import db
from ...models import (
    AcademicSession, AccountStatus, AuditLog, Course, CourseAllocation, CourseRegistration, Department,
    Faculty, ResultSheet, ResultStatus, Role, Semester, SemesterTerm, User,
)
from ...services import audit_text
from ...security.permissions import PERMISSION_DESCRIPTIONS, ROLE_PERMISSIONS
from ...services import academic, accounts, reports
from ...models.mixins import utcnow
from ...web import attempt, get_or_404
from . import bp
from .forms import AdminUserForm, DepartmentForm, FacultyForm, RoleForm, SemesterForm, SessionForm


def _department_choices(blank_label: str = "— None —"):
    departments = db.session.scalars(db.select(Department).order_by(Department.name))
    return [(0, blank_label)] + [(d.id, f"{d.name} ({d.code})") for d in departments]


# --------------------------------------------------------------------------- #
#  Dashboard
# --------------------------------------------------------------------------- #
@bp.route("/")
def dashboard():
    semester = Semester.current()
    recent = list(db.session.scalars(db.select(AuditLog).order_by(AuditLog.created_at.desc()).limit(10)))
    return render_template(
        "superadmin/dashboard.html",
        semester=semester,
        counts=reports.overview_counts(None, semester),
        status_breakdown=reports.result_status_breakdown(None, semester),
        per_department=reports.students_per_department(None),
        distribution=reports.grade_distribution(None, semester) if semester else {},
        recent=recent,
        describe=audit_text.describe,
    )


# --------------------------------------------------------------------------- #
#  Faculties & departments
# --------------------------------------------------------------------------- #
@bp.route("/faculties")
def faculties():
    all_faculties = list(db.session.scalars(db.select(Faculty).order_by(Faculty.name)))
    return render_template("superadmin/faculties.html", faculties=all_faculties)


def _faculty_form_page(faculty: Faculty | None):
    form = FacultyForm(obj=faculty)
    if form.validate_on_submit():
        if attempt(lambda: academic.save_faculty(current_user, faculty, name=form.name.data, code=form.code.data),
                   "Faculty saved."):
            return redirect(url_for("superadmin.faculties"))
    return render_template("shared/form_page.html", form=form, back_url=url_for("superadmin.faculties"),
                           title=f"Edit {faculty.name}" if faculty else "New faculty")


@bp.route("/faculties/new", methods=["GET", "POST"])
def faculties_new():
    return _faculty_form_page(None)


@bp.route("/faculties/<int:faculty_id>/edit", methods=["GET", "POST"])
def faculties_edit(faculty_id: int):
    return _faculty_form_page(get_or_404(Faculty, faculty_id))


def _department_form_page(department: Department | None):
    form = DepartmentForm(obj=department)
    form.faculty_id.choices = [(f.id, f.name) for f in db.session.scalars(db.select(Faculty).order_by(Faculty.name))]
    if request.method == "GET" and department is None and request.args.get("faculty_id"):
        form.faculty_id.data = request.args.get("faculty_id", type=int)
    if form.validate_on_submit():
        if attempt(lambda: academic.save_department(current_user, department, name=form.name.data,
                                                    code=form.code.data, faculty_id=form.faculty_id.data),
                   "Department saved."):
            return redirect(url_for("superadmin.faculties"))
    return render_template("shared/form_page.html", form=form, back_url=url_for("superadmin.faculties"),
                           title=f"Edit {department.name}" if department else "New department")


@bp.route("/faculties/departments/new", methods=["GET", "POST"])
def faculties_department_new():
    return _department_form_page(None)


@bp.route("/faculties/departments/<int:department_id>/edit", methods=["GET", "POST"])
def faculties_department_edit(department_id: int):
    return _department_form_page(get_or_404(Department, department_id))


@bp.route("/faculties/<int:faculty_id>/delete", methods=["POST"])
def faculties_delete(faculty_id: int):
    faculty = get_or_404(Faculty, faculty_id)
    name = faculty.name
    attempt(lambda: academic.delete_faculty(current_user, faculty), f"{name} deleted.")
    return redirect(url_for("superadmin.faculties"))


@bp.route("/faculties/departments/<int:department_id>/delete", methods=["POST"])
def faculties_department_delete(department_id: int):
    department = get_or_404(Department, department_id)
    name = department.name
    attempt(lambda: academic.delete_department(current_user, department), f"{name} department deleted.")
    return redirect(url_for("superadmin.faculties"))


# --------------------------------------------------------------------------- #
#  Sessions & semesters
# --------------------------------------------------------------------------- #
@bp.route("/sessions", methods=["GET", "POST"])
def sessions():
    form = SessionForm()
    if form.validate_on_submit():
        if attempt(lambda: academic.create_session(current_user, form.name.data, form.start_date.data,
                                                   form.end_date.data),
                   "Session created with First and Second semesters."):
            return redirect(url_for("superadmin.sessions"))
    show = request.args.get("show", "all")
    query = db.select(AcademicSession).order_by(AcademicSession.name.desc())
    if show == "active":
        query = query.where(AcademicSession.is_completed.is_(False))
    elif show == "completed":
        query = query.where(AcademicSession.is_completed.is_(True))
    all_sessions = list(db.session.scalars(query))
    usage = {sem.id: academic.semester_usage(sem) for s in all_sessions for sem in s.semesters}
    return render_template("superadmin/sessions.html", form=form, sessions=all_sessions, usage=usage, show=show,
                           terms=list(SemesterTerm))


# Semester buttons: one endpoint, one "action" each. Kept as a table so the
# list of possible actions is easy to read.
SEMESTER_ACTIONS = {
    "make_current": (academic.set_current_semester, "{name} is now the current semester."),
    "open": (lambda actor, sem: academic.set_registration(actor, sem, True), "Registration opened for {name}."),
    "close": (lambda actor, sem: academic.set_registration(actor, sem, False), "Registration closed for {name}."),
    "complete": (academic.complete_semester, "{name} marked as completed."),
    "reopen": (academic.reopen_semester, "{name} reopened."),
}


@bp.route("/sessions/semester/<int:semester_id>", methods=["POST"])
def sessions_semester(semester_id: int):
    """Semester buttons: make current, open/close registration, complete/reopen."""
    semester = get_or_404(Semester, semester_id)
    action = request.form.get("action")
    if action not in SEMESTER_ACTIONS:
        abort(400)
    function, message = SEMESTER_ACTIONS[action]
    if attempt(lambda: function(current_user, semester), message.format(name=semester.name)) and action == "complete":
        unapproved = db.session.scalar(db.select(db.func.count(ResultSheet.id)).where(
            ResultSheet.semester_id == semester.id, ResultSheet.status != ResultStatus.APPROVED)) or 0
        if unapproved:
            flash(f"Note: {unapproved} result sheet(s) in {semester.name} are not approved yet.", "warning")
    return redirect(request.form.get("next") or url_for("superadmin.sessions"))


@bp.route("/sessions/<int:session_id>/action", methods=["POST"])
def sessions_action(session_id: int):
    """Session buttons: complete / reopen / delete / add a missing semester."""
    session = get_or_404(AcademicSession, session_id)
    action = request.form.get("action")
    name = session.name
    if action == "complete":
        attempt(lambda: academic.complete_session(current_user, session), f"Session {name} marked as completed.")
    elif action == "reopen":
        attempt(lambda: academic.reopen_session(current_user, session), f"Session {name} reopened.")
    elif action == "delete":
        if attempt(lambda: academic.delete_session(current_user, session), f"Session {name} deleted."):
            return redirect(url_for("superadmin.sessions"))
    elif action == "add_semester":
        term = request.form.get("term", "")
        attempt(lambda: academic.add_semester(current_user, session, term), "Semester added.")
    else:
        abort(400)
    return redirect(request.form.get("next") or url_for("superadmin.sessions"))


@bp.route("/sessions/<int:session_id>/edit", methods=["GET", "POST"])
def sessions_edit(session_id: int):
    session = get_or_404(AcademicSession, session_id)
    form = SessionForm(obj=session)
    form.submit.label.text = "Save session"
    if form.validate_on_submit():
        if attempt(lambda: academic.update_session(current_user, session, name=form.name.data,
                                                   start_date=form.start_date.data, end_date=form.end_date.data),
                   "Session updated."):
            return redirect(url_for("superadmin.sessions"))
    return render_template("shared/form_page.html", form=form, title=f"Edit session {session.name}",
                           back_url=url_for("superadmin.sessions"))


@bp.route("/semesters/<int:semester_id>/edit", methods=["GET", "POST"])
def semesters_edit(semester_id: int):
    semester = get_or_404(Semester, semester_id)
    form = SemesterForm(obj=semester)
    if form.validate_on_submit():
        if attempt(lambda: academic.update_semester(current_user, semester, start_date=form.start_date.data,
                                                    end_date=form.end_date.data), "Semester dates saved."):
            return redirect(url_for("superadmin.sessions"))
    return render_template("shared/form_page.html", form=form, title=f"Edit {semester.name}",
                           back_url=url_for("superadmin.sessions"),
                           intro="Optional calendar dates for this semester (they must fall within the session).")


@bp.route("/semesters/<int:semester_id>/delete", methods=["POST"])
def semesters_delete(semester_id: int):
    semester = get_or_404(Semester, semester_id)
    name = semester.name
    attempt(lambda: academic.delete_semester(current_user, semester), f"{name} deleted.")
    return redirect(url_for("superadmin.sessions"))


def _semester_activity(semester: Semester) -> dict:
    """Everything that happened in one semester, for the semester page."""
    count = lambda q: db.session.scalar(q) or 0  # noqa: E731
    registrations = count(db.select(db.func.count(CourseRegistration.id)).filter_by(semester_id=semester.id))
    students = count(db.select(db.func.count(db.distinct(CourseRegistration.student_id)))
                     .filter_by(semester_id=semester.id))
    sheets = list(db.session.scalars(db.select(ResultSheet).join(ResultSheet.course)
                                     .where(ResultSheet.semester_id == semester.id).order_by(Course.code)))
    allocations = count(db.select(db.func.count(CourseAllocation.id)).filter_by(semester_id=semester.id))
    per_department = list(db.session.execute(
        db.select(Department.name, db.func.count(CourseRegistration.id))
        .join(User, User.id == CourseRegistration.student_id).join(Department, Department.id == User.department_id)
        .where(CourseRegistration.semester_id == semester.id).group_by(Department.name).order_by(Department.name)))
    status_counts: dict[str, int] = {}
    for sheet in sheets:
        status_counts[sheet.status] = status_counts.get(sheet.status, 0) + 1
    return {"registrations": registrations, "students": students, "allocations": allocations,
            "sheets": sheets, "status_counts": status_counts, "per_department": per_department}


def _activity_log(semesters: list[Semester], session: AcademicSession | None = None):
    """
    Audit entries that belong to these semesters: actions on the semester
    itself, on its result sheets, allocations and registrations, plus any
    entry whose description names the semester (e.g. "Registered CSC 201
    for First Semester 2026/2027").
    """
    ids = [s.id for s in semesters]
    names = [s.name for s in semesters]
    sheet_ids = db.select(ResultSheet.id).where(ResultSheet.semester_id.in_(ids))
    allocation_ids = db.select(CourseAllocation.id).where(CourseAllocation.semester_id.in_(ids))
    registration_ids = db.select(CourseRegistration.id).where(CourseRegistration.semester_id.in_(ids))
    conditions = [
        (AuditLog.entity_type == "Semester") & AuditLog.entity_id.in_(ids),
        (AuditLog.entity_type == "ResultSheet") & AuditLog.entity_id.in_(sheet_ids),
        (AuditLog.entity_type == "CourseAllocation") & AuditLog.entity_id.in_(allocation_ids),
        (AuditLog.entity_type == "CourseRegistration") & AuditLog.entity_id.in_(registration_ids),
    ] + [AuditLog.description.contains(name) for name in names]
    if session is not None:
        conditions.append((AuditLog.entity_type == "AcademicSession") & (AuditLog.entity_id == session.id))
    query = db.select(AuditLog).where(or_(*conditions)).order_by(AuditLog.created_at.desc())
    if category := request.args.get("category"):
        query = query.where(AuditLog.action.in_(audit_text.codes_in(category)))
    return db.paginate(query, per_page=25)


@bp.route("/semesters/<int:semester_id>")
def semesters_view(semester_id: int):
    semester = get_or_404(Semester, semester_id)
    return render_template("superadmin/period_view.html", semester=semester, session=semester.session,
                           semesters=[semester], activity=_semester_activity(semester),
                           log=_activity_log([semester]), categories=audit_text.CATEGORIES, describe=audit_text.describe)


@bp.route("/sessions/<int:session_id>")
def sessions_view(session_id: int):
    session = get_or_404(AcademicSession, session_id)
    per_semester = [(sem, _semester_activity(sem)) for sem in session.semesters]
    return render_template("superadmin/period_view.html", semester=None, session=session,
                           semesters=session.semesters, per_semester=per_semester,
                           log=_activity_log(session.semesters, session), categories=audit_text.CATEGORIES,
                           describe=audit_text.describe)


# --------------------------------------------------------------------------- #
#  User accounts
# --------------------------------------------------------------------------- #
@bp.route("/users")
def users():
    query = (db.select(User).order_by(User.role, User.last_name)
             .options(joinedload(User.lecturer_profile), joinedload(User.department)))
    if role := request.args.get("role"):
        query = query.where(User.role == role)
    if status := request.args.get("status"):
        query = query.where(User.status == status)
    if department_id := request.args.get("department_id", type=int):
        query = query.where(User.department_id == department_id)
    if search := request.args.get("q", "").strip():
        like = f"%{search}%"
        query = query.where(or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like)))
    if request.args.get("locked") == "1":
        query = query.where(User.locked_until > utcnow())
    page = db.paginate(query, per_page=25)
    departments = list(db.session.scalars(db.select(Department).order_by(Department.name)))
    return render_template("superadmin/users.html", page=page, roles=list(Role), statuses=list(AccountStatus),
                           departments=departments)


@bp.route("/users/new-admin", methods=["GET", "POST"])
def users_new():
    form = AdminUserForm()
    form.department_id.choices = _department_choices()
    if form.validate_on_submit():
        if attempt(lambda: accounts.create_staff_admin(
                current_user, role=form.role.data, email=form.email.data, password=form.password.data,
                first_name=form.first_name.data, last_name=form.last_name.data,
                department_id=form.department_id.data or None), "Administrator account created."):
            return redirect(url_for("superadmin.users"))
    return render_template("shared/form_page.html", form=form, title="New administrator account",
                           back_url=url_for("superadmin.users"),
                           intro="Students and lecturers are added from the Students and Lecturers pages, "
                                 "where their academic details are captured.")


@bp.route("/users/<int:user_id>/role", methods=["GET", "POST"])
def users_role(user_id: int):
    user = get_or_404(User, user_id)
    form = RoleForm(role=user.role, department_id=user.department_id or 0)
    form.department_id.choices = _department_choices("— Keep current —")
    if form.validate_on_submit():
        if attempt(lambda: accounts.change_role(current_user, user, form.role.data, form.department_id.data or None),
                   "Role updated."):
            return redirect(url_for("superadmin.users"))
    return render_template("shared/form_page.html", form=form, title=f"Change role — {user.full_name}",
                           back_url=url_for("superadmin.users"),
                           intro=f"Current role: {user.role_label}. Only staff roles can be changed; "
                                 "a lecturer profile is needed for the Lecturer role.")


# --------------------------------------------------------------------------- #
#  Roles & permissions, audit trail
# --------------------------------------------------------------------------- #
@bp.route("/roles")
def roles():
    return render_template("superadmin/roles.html", roles=list(Role), matrix=ROLE_PERMISSIONS,
                           descriptions=PERMISSION_DESCRIPTIONS)


def _parse_day(text: str | None) -> datetime | None:
    """'2026-11-10' -> datetime at midnight; anything invalid is ignored."""
    try:
        return datetime.strptime(text or "", "%Y-%m-%d")
    except ValueError:
        return None


@bp.route("/audit")
def audit():
    """
    The audit trail in plain English. Filters: kind of activity (category),
    person, role, date range and free-text search. Technical codes are still
    available (shown small) for anyone who needs them.
    """
    query = db.select(AuditLog).order_by(AuditLog.created_at.desc())
    if category := request.args.get("category", ""):
        query = query.where(AuditLog.action.in_(audit_text.codes_in(category)))
    if action := request.args.get("action", "").strip():   # technical code prefix, e.g. "result"
        query = query.where(AuditLog.action.ilike(f"{action}%"))
    if role := request.args.get("role", ""):
        query = query.where(AuditLog.actor_role == role)
    if who := request.args.get("who", "").strip():
        like = f"%{who}%"
        query = query.outerjoin(AuditLog.actor).where(or_(AuditLog.actor_name.ilike(like), User.email.ilike(like),
                                                          User.first_name.ilike(like), User.last_name.ilike(like)))
    if search := request.args.get("q", "").strip():
        query = query.where(AuditLog.description.ilike(f"%{search}%"))
    if start := _parse_day(request.args.get("from")):
        query = query.where(AuditLog.created_at >= start)
    if end := _parse_day(request.args.get("to")):
        query = query.where(AuditLog.created_at < end + timedelta(days=1))
    page = db.paginate(query, per_page=30)
    return render_template("superadmin/audit.html", page=page, categories=audit_text.CATEGORIES,
                           roles=list(Role), describe=audit_text.describe)
