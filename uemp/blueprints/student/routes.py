"""
student routes — everything a student can do.

    /student/                     dashboard
    /student/profile              view & edit permitted profile details
    /student/courses              Workflow 1: see available courses, register, drop
    /student/courses/slip         printable course registration form
    /student/results              approved results for one semester + GPA
    /student/history              all semesters + CGPA
    /student/statement            printable statement of result

SAFETY RULE
    Every query uses `current_user` — the logged-in student. A student ID is
    never taken from the URL or form, so one student cannot view or register
    on behalf of another.
"""

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from ...extensions import db
from ...models import CourseRegistration, Semester
from ...services import audit, grading
from ...services import registration as registration_service
from ...services.errors import ServiceError
from ...web import attempt, selected_semester
from . import bp
from .forms import StudentProfileForm


def _semesters_with_registrations() -> list[Semester]:
    """Semesters in which this student registered at least one course."""
    query = (db.select(Semester).join(CourseRegistration, CourseRegistration.semester_id == Semester.id)
             .where(CourseRegistration.student_id == current_user.id).distinct())
    semesters = list(db.session.scalars(query))
    return sorted(semesters, key=lambda s: (s.session.name, s.term), reverse=True)


@bp.route("/")
def dashboard():
    semester = Semester.current()
    registered = registration_service.registrations_for(current_user, semester) if semester else []
    history = grading.academic_history(current_user.id)
    latest = history.semesters[-1] if history.semesters else None
    return render_template(
        "student/dashboard.html",
        profile=current_user.student_profile,
        semester=semester,
        registered=registered,
        total_units=sum(r.course.units for r in registered),
        history=history,
        latest=latest,
    )


@bp.route("/profile", methods=["GET", "POST"])
def profile():
    profile = current_user.student_profile
    form = StudentProfileForm(obj=profile)
    if request.method == "GET":
        form.phone.data = current_user.phone

    if form.validate_on_submit():
        # Copy ONLY the permitted fields — official fields are untouched.
        current_user.phone = form.phone.data or None
        profile.address = form.address.data or None
        profile.date_of_birth = form.date_of_birth.data
        profile.gender = form.gender.data or None
        profile.next_of_kin = form.next_of_kin.data or None
        profile.next_of_kin_phone = form.next_of_kin_phone.data or None
        audit.record(current_user, "profile.updated", f"{profile.matric_number} updated personal details", current_user)
        db.session.commit()
        flash("Your profile has been updated.", "success")
        return redirect(url_for("student.profile"))
    return render_template("student/profile.html", form=form, profile=profile)


@bp.route("/courses", methods=["GET", "POST"])
def registration():
    semester = Semester.current()

    if request.method == "POST":
        course_ids = request.form.getlist("course_ids", type=int)
        attempt(lambda: registration_service.register_courses(current_user, course_ids, semester),
                "Courses registered successfully.")
        return redirect(url_for("student.registration"))

    available, registered, error = [], [], None
    if semester:
        try:
            available = registration_service.eligible_courses(current_user, semester)
        except ServiceError as exc:
            error = str(exc)
        registered = registration_service.registrations_for(current_user, semester)

    registered_ids = {r.course_id for r in registered}
    return render_template(
        "student/registration.html",
        semester=semester,
        available=available,
        registered=registered,
        registered_ids=registered_ids,
        total_units=sum(r.course.units for r in registered),
        error=error,
    )


@bp.route("/courses/<int:registration_id>/drop", methods=["POST"])
def registration_drop(registration_id: int):
    attempt(lambda: registration_service.drop_course(current_user, registration_id), "Course dropped.")
    return redirect(url_for("student.registration"))


@bp.route("/courses/slip")
def registration_slip():
    """Printable course registration form for a semester."""
    semester = selected_semester()
    if semester is None:
        flash("There is no semester to print.", "warning")
        return redirect(url_for("student.registration"))
    registered = registration_service.registrations_for(current_user, semester)
    return render_template(
        "student/print_slip.html", semester=semester, registered=registered,
        total_units=sum(r.course.units for r in registered), profile=current_user.student_profile,
    )


@bp.route("/results")
def results():
    """
    Results for one semester. Only APPROVED results are shown (Business rule 6);
    registered courses still waiting for approval are listed separately.
    """
    semesters = _semesters_with_registrations()            # newest first
    semester_id = request.args.get("semester_id", type=int)
    chosen = next((s for s in semesters if s.id == semester_id), semesters[0] if semesters else None)

    history = grading.academic_history(current_user.id)
    record = next((r for r in history.semesters if chosen and r.semester.id == chosen.id), None)

    pending = []
    if chosen:
        approved_ids = {e.registration_id for e in (record.entries if record else [])}
        pending = [r for r in registration_service.registrations_for(current_user, chosen) if r.id not in approved_ids]

    return render_template("student/results.html", semesters=semesters, chosen=chosen, history=history,
                           record=record, pending=pending)


@bp.route("/history")
def history():
    return render_template("student/history.html", history=grading.academic_history(current_user.id),
                           profile=current_user.student_profile)


@bp.route("/statement")
def statement():
    """Printable statement of result (all approved semesters)."""
    return render_template("student/print_statement.html", history=grading.academic_history(current_user.id),
                           profile=current_user.student_profile)
