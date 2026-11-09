"""
Super Admin routes — Workflow 4: Super Admin Management.

    /super/                      university-wide dashboard
    /super/faculties             faculties and their departments
    /super/sessions              academic sessions, current semester, registration on/off
    /super/users                 every account: status, role, password
    /super/roles                 the role → permission matrix (RBAC)
    /super/audit                 audit trail of all important actions

Department-level tools (students, lecturers, courses, results, reports) are in
the shared `admin` blueprint, where the Super Admin sees all departments.
"""

from flask import redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ...extensions import db
from ...models import (
    AcademicSession, AccountStatus, AuditLog, Department, Faculty, Role, Semester, User,
)
from ...security.permissions import PERMISSION_DESCRIPTIONS, ROLE_PERMISSIONS
from ...services import academic, accounts, reports
from ...web import attempt, get_or_404
from . import bp
from .forms import AdminUserForm, DepartmentForm, FacultyForm, RoleForm, SessionForm


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
    all_sessions = list(db.session.scalars(db.select(AcademicSession).order_by(AcademicSession.name.desc())))
    return render_template("superadmin/sessions.html", form=form, sessions=all_sessions)


@bp.route("/sessions/semester/<int:semester_id>", methods=["POST"])
def sessions_semester(semester_id: int):
    """One endpoint for the semester buttons: make current / open / close registration."""
    semester = get_or_404(Semester, semester_id)
    action = request.form.get("action")
    if action == "make_current":
        attempt(lambda: academic.set_current_semester(current_user, semester), f"{semester.name} is now current.")
    elif action in ("open", "close"):
        attempt(lambda: academic.set_registration(current_user, semester, action == "open"),
                f"Registration {'opened' if action == 'open' else 'closed'} for {semester.name}.")
    return redirect(url_for("superadmin.sessions"))


# --------------------------------------------------------------------------- #
#  User accounts
# --------------------------------------------------------------------------- #
@bp.route("/users")
def users():
    query = db.select(User).order_by(User.role, User.last_name)
    if role := request.args.get("role"):
        query = query.where(User.role == role)
    if status := request.args.get("status"):
        query = query.where(User.status == status)
    if department_id := request.args.get("department_id", type=int):
        query = query.where(User.department_id == department_id)
    if search := request.args.get("q", "").strip():
        like = f"%{search}%"
        query = query.where(or_(User.first_name.ilike(like), User.last_name.ilike(like), User.email.ilike(like)))
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


@bp.route("/audit")
def audit():
    query = db.select(AuditLog).order_by(AuditLog.created_at.desc())
    if action := request.args.get("action", "").strip():
        query = query.where(AuditLog.action.ilike(f"{action}%"))
    if search := request.args.get("q", "").strip():
        query = query.where(AuditLog.description.ilike(f"%{search}%"))
    page = db.paginate(query, per_page=30)
    return render_template("superadmin/audit.html", page=page)
