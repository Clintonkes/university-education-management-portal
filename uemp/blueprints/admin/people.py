"""
People management — students and lecturers (/admin/students, /admin/lecturers).

Department Admins: "Register and manage students within their department",
"Create and manage lecturer profiles".
Super Admin: the same, for every department.

Every page that opens ONE person calls `_load_person()`, which returns 403
if the person belongs to a department the admin may not manage.
"""

from flask import abort, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_

from ...extensions import db
from ...models import (
    AccountStatus, CourseRegistration, LecturerProfile, Role, Semester, StudentProfile, User,
)
from ...security import Perm, ensure_department_access, permission_required
from ...services import accounts, grading
from ...web import attempt, get_or_404
from . import bp
from .forms import LecturerForm, PasswordResetForm, StudentForm
from .helpers import department_choices, department_filter, level_choices, limit_to, program_choices


def _load_person(user_id: int, role: Role) -> User:
    user = get_or_404(User, user_id)
    if user.role != role:
        abort(404)
    ensure_department_access(user.department_id)
    return user


def _require_password(form) -> bool:
    if not form.password.data:
        form.password.errors = list(form.password.errors) + ["An initial password is required."]
        return False
    return True


# --------------------------------------------------------------------------- #
#  Students
# --------------------------------------------------------------------------- #
@bp.route("/students")
@permission_required(Perm.STUDENTS_MANAGE)
def students():
    search = request.args.get("q", "").strip()
    program_id = request.args.get("program_id", type=int)
    level = request.args.get("level", type=int)
    status = request.args.get("status", "")

    query = (db.select(User).join(User.student_profile).where(User.role == Role.STUDENT)
             .order_by(StudentProfile.matric_number))
    query = limit_to(query, User.department_id, department_filter())
    if search:
        like = f"%{search}%"
        query = query.where(or_(User.first_name.ilike(like), User.last_name.ilike(like),
                                User.email.ilike(like), StudentProfile.matric_number.ilike(like)))
    if program_id:
        query = query.where(StudentProfile.program_id == program_id)
    if level:
        query = query.where(StudentProfile.level == level)
    if status:
        query = query.where(User.status == status)

    page = db.paginate(query, per_page=20)
    return render_template("admin/students.html", page=page, programs=program_choices(),
                           levels=level_choices(), statuses=list(AccountStatus))


@bp.route("/students/new", methods=["GET", "POST"])
@permission_required(Perm.STUDENTS_MANAGE)
def students_new():
    form = StudentForm()
    form.program_id.choices = program_choices()
    form.level.choices = level_choices()

    if form.validate_on_submit() and _require_password(form):
        holder = {}

        def create():
            holder["user"] = accounts.create_student(
                current_user, email=form.email.data, password=form.password.data,
                first_name=form.first_name.data, last_name=form.last_name.data,
                matric_number=form.matric_number.data, program_id=form.program_id.data,
                level=form.level.data, entry_year=form.entry_year.data,
                phone=form.phone.data or None, gender=form.gender.data or None)

        if attempt(create, "Student created."):
            return redirect(url_for("admin.students_view", user_id=holder["user"].id))
    return render_template("shared/form_page.html", form=form, title="Register a student",
                           back_url=url_for("admin.students"))


@bp.route("/students/<int:user_id>")
@permission_required(Perm.STUDENTS_MANAGE)
def students_view(user_id: int):
    student = _load_person(user_id, Role.STUDENT)
    registrations = list(db.session.scalars(
        db.select(CourseRegistration).where(CourseRegistration.student_id == student.id)
        .join(CourseRegistration.semester).order_by(Semester.id.desc())))
    return render_template("admin/student_view.html", student=student, registrations=registrations,
                           history=grading.academic_history(student.id), reset_form=PasswordResetForm())


@bp.route("/students/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.STUDENTS_MANAGE)
def students_edit(user_id: int):
    student = _load_person(user_id, Role.STUDENT)
    profile = student.student_profile
    form = StudentForm(obj=student)
    form.program_id.choices = program_choices()
    form.level.choices = level_choices()
    del form.password  # passwords are reset separately
    if request.method == "GET":
        form.matric_number.data, form.program_id.data = profile.matric_number, profile.program_id
        form.level.data, form.entry_year.data, form.gender.data = profile.level, profile.entry_year, profile.gender or ""

    if form.validate_on_submit():
        if attempt(lambda: accounts.update_student(
                current_user, student, email=form.email.data, first_name=form.first_name.data,
                last_name=form.last_name.data, matric_number=form.matric_number.data,
                program_id=form.program_id.data, level=form.level.data, entry_year=form.entry_year.data,
                phone=form.phone.data or None, gender=form.gender.data or None), "Student updated."):
            return redirect(url_for("admin.students_view", user_id=student.id))
    return render_template("shared/form_page.html", form=form, title=f"Edit {student.full_name}",
                           back_url=url_for("admin.students_view", user_id=student.id))


# --------------------------------------------------------------------------- #
#  Lecturers
# --------------------------------------------------------------------------- #
@bp.route("/lecturers")
@permission_required(Perm.LECTURERS_MANAGE)
def lecturers():
    search = request.args.get("q", "").strip()
    query = (db.select(User).join(User.lecturer_profile).where(User.role == Role.LECTURER)
             .order_by(User.last_name))
    query = limit_to(query, User.department_id, department_filter())
    if search:
        like = f"%{search}%"
        query = query.where(or_(User.first_name.ilike(like), User.last_name.ilike(like),
                                User.email.ilike(like), LecturerProfile.staff_id.ilike(like)))
    page = db.paginate(query, per_page=20)
    return render_template("admin/lecturers.html", page=page)


@bp.route("/lecturers/new", methods=["GET", "POST"])
@permission_required(Perm.LECTURERS_MANAGE)
def lecturers_new():
    form = LecturerForm()
    form.department_id.choices = department_choices()
    if form.validate_on_submit() and _require_password(form):
        if attempt(lambda: accounts.create_lecturer(
                current_user, email=form.email.data, password=form.password.data,
                first_name=form.first_name.data, last_name=form.last_name.data,
                staff_id=form.staff_id.data, department_id=form.department_id.data,
                title=form.title.data or None, rank=form.rank.data or None,
                specialization=form.specialization.data or None, phone=form.phone.data or None),
                "Lecturer created."):
            return redirect(url_for("admin.lecturers"))
    return render_template("shared/form_page.html", form=form, title="Add a lecturer",
                           back_url=url_for("admin.lecturers"))


@bp.route("/lecturers/<int:user_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.LECTURERS_MANAGE)
def lecturers_edit(user_id: int):
    lecturer = _load_person(user_id, Role.LECTURER)
    profile = lecturer.lecturer_profile
    form = LecturerForm(obj=lecturer)
    form.department_id.choices = department_choices()
    del form.password
    if request.method == "GET":
        form.staff_id.data, form.title.data = profile.staff_id, profile.title or ""
        form.rank.data, form.specialization.data = profile.rank, profile.specialization

    if form.validate_on_submit():
        if attempt(lambda: accounts.update_lecturer(
                current_user, lecturer, email=form.email.data, first_name=form.first_name.data,
                last_name=form.last_name.data, staff_id=form.staff_id.data,
                department_id=form.department_id.data, title=form.title.data or None,
                rank=form.rank.data or None, specialization=form.specialization.data or None,
                phone=form.phone.data or None), "Lecturer updated."):
            return redirect(url_for("admin.lecturers"))
    return render_template("shared/form_page.html", form=form, title=f"Edit {lecturer.display_name}",
                           back_url=url_for("admin.lecturers"), reset_user=lecturer,
                           reset_form=PasswordResetForm())


# --------------------------------------------------------------------------- #
#  Account actions shared by students and lecturers
# --------------------------------------------------------------------------- #
def _back_to(user: User) -> str:
    if user.role == Role.STUDENT:
        return url_for("admin.students_view", user_id=user.id)
    if user.role == Role.LECTURER:
        return url_for("admin.lecturers_edit", user_id=user.id)
    return url_for("superadmin.users")


@bp.route("/users/<int:user_id>/status", methods=["POST"])
@permission_required(Perm.STUDENTS_MANAGE)
def users_status(user_id: int):
    user = get_or_404(User, user_id)
    status = request.form.get("status", "")
    # The service checks the admin may change this account (department + role rules).
    attempt(lambda: accounts.set_status(current_user, user, status), f"Account is now {status}.")
    return redirect(_back_to(user))


@bp.route("/users/<int:user_id>/password", methods=["POST"])
@permission_required(Perm.STUDENTS_MANAGE)
def users_password(user_id: int):
    user = get_or_404(User, user_id)
    form = PasswordResetForm()
    if form.validate_on_submit():
        attempt(lambda: accounts.reset_password(current_user, user, form.new_password.data),
                "Password reset. Share the new password with the user securely.")
    else:
        flash("Password must be at least 8 characters.", "danger")
    return redirect(_back_to(user))

