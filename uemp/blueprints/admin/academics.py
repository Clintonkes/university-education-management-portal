"""
Academic set-up — programmes, courses, lecturer allocation, registrations.

    /admin/programs          list + create + edit programmes
    /admin/courses           course catalogue (code, title, units, level, semester)
    /admin/allocations       assign lecturers to this semester's courses
    /admin/registrations     see which students registered which courses (+ CSV)
    /admin/registrations/<id>   one registration; the Super Admin can edit or remove it
"""

from flask import abort, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import or_
from sqlalchemy.orm import contains_eager, joinedload

from ...extensions import db
from ...models import (
    Course,
    CourseAllocation,
    CourseRegistration,
    Program,
    Semester,
    SemesterTerm,
    StudentProfile,
    User,
)
from ...security import Perm, ensure_department_access, permission_required
from ...services import catalogue
from ...services import registration as registration_service
from ...web import all_semesters, attempt, csv_response, get_or_404, selected_semester
from . import bp
from .forms import AllocationForm, CourseForm, ProgramForm, RegistrationEditForm
from .helpers import (
    course_choices,
    department_choices,
    department_filter,
    lecturer_choices,
    level_choices,
    limit_to,
    program_choices,
)


# --------------------------------------------------------------------------- #
#  Programmes
# --------------------------------------------------------------------------- #
@bp.route("/programs")
@permission_required(Perm.PROGRAMS_MANAGE)
def programs():
    query = limit_to(db.select(Program), Program.department_id, department_filter()).order_by(Program.name)
    rows = []
    for program in db.session.scalars(query):
        students = db.session.scalar(db.select(db.func.count(StudentProfile.id)).filter_by(program_id=program.id))
        rows.append((program, students))
    return render_template("admin/programs.html", rows=rows)


def _program_form_page(program: Program | None):
    form = ProgramForm(obj=program)
    form.department_id.choices = department_choices()
    if form.validate_on_submit():
        if attempt(lambda: catalogue.save_program(
                current_user, program, name=form.name.data, code=form.code.data, degree=form.degree.data,
                duration_years=form.duration_years.data, department_id=form.department_id.data),
                "Programme saved."):
            return redirect(url_for("admin.programs"))
    title = f"Edit {program.name}" if program else "New programme"
    return render_template("shared/form_page.html", form=form, title=title, back_url=url_for("admin.programs"))


@bp.route("/programs/new", methods=["GET", "POST"])
@permission_required(Perm.PROGRAMS_MANAGE)
def programs_new():
    return _program_form_page(None)


@bp.route("/programs/<int:program_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.PROGRAMS_MANAGE)
def programs_edit(program_id: int):
    program = get_or_404(Program, program_id)
    ensure_department_access(program.department_id)
    return _program_form_page(program)


@bp.route("/programs/<int:program_id>/delete", methods=["POST"])
@permission_required(Perm.PROGRAMS_MANAGE)
def programs_delete(program_id: int):
    program = get_or_404(Program, program_id)
    ensure_department_access(program.department_id)
    name = program.name
    attempt(lambda: catalogue.delete_program(current_user, program), f"Programme {name} deleted.")
    return redirect(url_for("admin.programs"))


# --------------------------------------------------------------------------- #
#  Courses
# --------------------------------------------------------------------------- #
@bp.route("/courses")
@permission_required(Perm.COURSES_MANAGE)
def courses():
    search = request.args.get("q", "").strip()
    level = request.args.get("level", type=int)
    term = request.args.get("term", "")

    query = limit_to(db.select(Course), Course.department_id, department_filter()).order_by(Course.level, Course.code)
    if search:
        query = query.where(or_(Course.code.ilike(f"%{search}%"), Course.title.ilike(f"%{search}%")))
    if level:
        query = query.where(Course.level == level)
    if term:
        query = query.where(Course.semester_term == term)
    if (active := request.args.get("active", "")) in ("0", "1"):
        query = query.where(Course.is_active.is_(active == "1"))
    page = db.paginate(query, per_page=25)
    return render_template("admin/courses.html", page=page, levels=level_choices(), terms=list(SemesterTerm))


def _course_form_page(course: Course | None):
    form = CourseForm(obj=course)
    form.level.choices = level_choices()
    form.department_id.choices = department_choices()
    # Any programme may take a course, so list them all (see services/catalogue.py).
    form.program_ids.choices = [(p.id, f"{p.degree} {p.name} ({p.code})")
                                for p in db.session.scalars(db.select(Program).order_by(Program.name))]
    if request.method == "GET" and course:
        form.program_ids.data = [p.id for p in course.programs]

    if form.validate_on_submit():
        if attempt(lambda: catalogue.save_course(
                current_user, course, code=form.code.data, title=form.title.data, units=form.units.data,
                level=form.level.data, semester_term=form.semester_term.data,
                department_id=form.department_id.data, program_ids=form.program_ids.data,
                description=form.description.data, is_active=form.is_active.data), "Course saved."):
            return redirect(url_for("admin.courses"))
    title = f"Edit {course.code}" if course else "New course"
    return render_template("shared/form_page.html", form=form, title=title, back_url=url_for("admin.courses"))


@bp.route("/courses/new", methods=["GET", "POST"])
@permission_required(Perm.COURSES_MANAGE)
def courses_new():
    return _course_form_page(None)


@bp.route("/courses/<int:course_id>/edit", methods=["GET", "POST"])
@permission_required(Perm.COURSES_MANAGE)
def courses_edit(course_id: int):
    course = get_or_404(Course, course_id)
    ensure_department_access(course.department_id)
    return _course_form_page(course)


# --------------------------------------------------------------------------- #
#  Course allocation
# --------------------------------------------------------------------------- #
@bp.route("/allocations", methods=["GET", "POST"])
@permission_required(Perm.ALLOCATIONS_MANAGE)
def allocations():
    semester = selected_semester()
    form = AllocationForm()
    form.course_id.choices = course_choices(semester.term if semester else None)
    form.lecturer_id.choices = lecturer_choices()

    if form.validate_on_submit():
        attempt(lambda: catalogue.allocate_course(current_user, course_id=form.course_id.data,
                                                  lecturer_id=form.lecturer_id.data, semester=semester),
                "Lecturer assigned.")
        return redirect(url_for("admin.allocations", semester_id=semester.id if semester else None))

    rows, unallocated = [], []
    if semester:
        query = (limit_to(db.select(CourseAllocation).join(CourseAllocation.course), Course.department_id,
                          department_filter())
                 .options(
                     contains_eager(CourseAllocation.course).joinedload(Course.department),
                     joinedload(CourseAllocation.lecturer).joinedload(User.lecturer_profile),
                 )
                 .where(CourseAllocation.semester_id == semester.id).order_by(Course.code))
        rows = list(db.session.scalars(query))
        allocated_ids = {a.course_id for a in rows}
        unallocated_q = limit_to(
            db.select(Course).where(Course.is_active.is_(True), Course.semester_term == semester.term),
            Course.department_id, department_filter()).order_by(Course.code)
        unallocated = [c for c in db.session.scalars(unallocated_q) if c.id not in allocated_ids]
    return render_template("admin/allocations.html", form=form, rows=rows, unallocated=unallocated,
                           semester=semester, semesters=all_semesters())


@bp.route("/allocations/<int:allocation_id>/delete", methods=["POST"])
@permission_required(Perm.ALLOCATIONS_MANAGE)
def allocations_delete(allocation_id: int):
    allocation = get_or_404(CourseAllocation, allocation_id)
    semester_id = allocation.semester_id
    attempt(lambda: catalogue.remove_allocation(current_user, allocation), "Allocation removed.")
    return redirect(url_for("admin.allocations", semester_id=semester_id))


# --------------------------------------------------------------------------- #
#  Registrations
# --------------------------------------------------------------------------- #
def _registration_base(semester):
    """Registrations in a semester for students the admin may see (by the STUDENT's department)."""
    query = (db.select(CourseRegistration)
             .join(CourseRegistration.course)
             .join(User, CourseRegistration.student_id == User.id)
             .join(StudentProfile, StudentProfile.user_id == User.id)
             .where(CourseRegistration.semester_id == semester.id))
    return limit_to(query, User.department_id, department_filter())


def _registered_courses(semester) -> list[Course]:
    """
    Courses that students in scope ACTUALLY registered this semester. This is
    what the course filter offers — including courses owned by other
    departments (e.g. MTH 201 taken by Computer Science students).
    """
    ids = db.select(CourseRegistration.course_id).where(
        CourseRegistration.id.in_(_registration_base(semester).with_only_columns(CourseRegistration.id)))
    return list(db.session.scalars(db.select(Course).where(Course.id.in_(ids)).order_by(Course.code)))


def _registration_query(semester, course_ids: set[int]):
    query = (_registration_base(semester).order_by(StudentProfile.matric_number, Course.code)
             # The rows show student, profile and course: load them with the registrations.
             .options(contains_eager(CourseRegistration.course),
                      contains_eager(CourseRegistration.student).contains_eager(User.student_profile)))
    course_id = request.args.get("course_id", type=int)
    # Ignore a course left over from another semester's filter instead of showing nothing.
    if course_id and course_id in course_ids:
        query = query.where(CourseRegistration.course_id == course_id)
    if level := request.args.get("level", type=int):
        query = query.where(StudentProfile.level == level)
    if program_id := request.args.get("program_id", type=int):
        query = query.where(StudentProfile.program_id == program_id)
    if reg_type := request.args.get("type", ""):
        query = query.where(CourseRegistration.registration_type == reg_type)
    if search := request.args.get("q", "").strip():
        like = f"%{search}%"
        query = query.where(or_(StudentProfile.matric_number.ilike(like), User.last_name.ilike(like),
                                User.first_name.ilike(like), Course.code.ilike(like), Course.title.ilike(like)))
    return query


@bp.route("/registrations")
@permission_required(Perm.REGISTRATIONS_VIEW)
def registrations():
    semester = selected_semester()
    page, courses, totals = None, [], {}
    if semester:
        courses = _registered_courses(semester)
        query = _registration_query(semester, {c.id for c in courses})
        page = db.paginate(query, per_page=30)
        # Totals for the WHOLE filtered list (not just this page).
        rows = list(db.session.execute(query.with_only_columns(CourseRegistration.student_id, Course.units)
                                       .order_by(None)))
        totals = {"registrations": len(rows), "students": len({sid for sid, _ in rows}),
                  "units": sum(units for _, units in rows)}
    return render_template("admin/registrations.html", page=page, semester=semester, semesters=all_semesters(),
                           courses=courses, levels=level_choices(), programs=program_choices(),
                           types=CourseRegistration.TYPES, totals=totals)


@bp.route("/registrations.csv")
@permission_required(Perm.REGISTRATIONS_VIEW)
def registrations_csv():
    semester = selected_semester() or abort(404)
    course_ids = {c.id for c in _registered_courses(semester)}
    rows = []
    for reg in db.session.scalars(_registration_query(semester, course_ids)):
        profile = reg.student.student_profile
        rows.append([profile.matric_number, reg.student.full_name, profile.program.name, profile.level,
                     reg.course.code, reg.course.title, reg.course.units, reg.type_label, reg.remarks or "",
                     reg.created_at.strftime("%Y-%m-%d")])
    return csv_response(f"registrations_{semester.session.name.replace('/', '-')}_{semester.term}.csv",
                        ["Matric No", "Name", "Programme", "Level", "Course", "Title", "Units", "Type", "Remarks",
                         "Registered"], rows)


def _load_registration(registration_id: int) -> CourseRegistration:
    registration = get_or_404(CourseRegistration, registration_id)
    ensure_department_access(registration.student.department_id)
    return registration


@bp.route("/registrations/<int:registration_id>", methods=["GET", "POST"])
@permission_required(Perm.REGISTRATIONS_VIEW)
def registrations_view(registration_id: int):
    """
    One registration in detail. The Super Admin can also correct it here:
    change the course (same semester), set the type (regular / carry-over /
    elective) or add a remark. Every change is recorded in the audit trail.
    """
    registration = _load_registration(registration_id)
    can_edit = current_user.role == "super_admin"
    form = RegistrationEditForm(obj=registration) if can_edit else None
    if form is not None:
        semester: Semester = registration.semester
        options = db.session.scalars(db.select(Course).where(
            Course.is_active.is_(True), Course.semester_term == semester.term).order_by(Course.code))
        form.course_id.choices = [(c.id, f"{c.code} — {c.title} ({c.units}u, {c.level}L)") for c in options]
        if registration.course_id not in dict(form.course_id.choices):
            form.course_id.choices.insert(0, (registration.course_id, f"{registration.course.code} (inactive)"))
        form.registration_type.choices = list(CourseRegistration.TYPES.items())
        if request.method == "POST":
            if not can_edit:
                abort(403)
            if form.validate_on_submit() and attempt(lambda: registration_service.admin_update(
                    current_user, registration, course_id=form.course_id.data,
                    registration_type=form.registration_type.data, remarks=form.remarks.data),
                    "Registration updated."):
                return redirect(url_for("admin.registrations_view", registration_id=registration.id))
    elif request.method == "POST":
        abort(403)
    return render_template("admin/registration_view.html", registration=registration, form=form)


@bp.route("/registrations/<int:registration_id>/delete", methods=["POST"])
@permission_required(Perm.REGISTRATIONS_EDIT)
def registrations_delete(registration_id: int):
    registration = _load_registration(registration_id)
    semester_id = registration.semester_id
    if attempt(lambda: registration_service.admin_delete(current_user, registration), "Registration removed."):
        return redirect(url_for("admin.registrations", semester_id=semester_id))
    return redirect(url_for("admin.registrations_view", registration_id=registration_id))
