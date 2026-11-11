"""
lecturer routes — Workflow 2: Lecturer Result Submission.

    /lecturer/                               dashboard (this semester's courses)
    /lecturer/courses                        every course ever allocated to me
    /lecturer/courses/<id>?tab=...           one course, in tabs:
            overview     status, feedback from the department, key numbers
            class-list   the students registered (table, CSV, print)
            scores       enter / modify CA and exam scores (save as draft)
            submit       final check, then submit for approval
            performance  course and student performance summary
            correction   ask permission to edit results after submitting
    /lecturer/courses/<id>/scores   (POST)   save draft OR submit for approval
    /lecturer/courses/<id>/correction (POST) request authorisation to edit
    /lecturer/courses/<id>/class-list.csv    download class list
    /lecturer/courses/<id>/print             printable class list / score sheet

`<id>` is a CourseAllocation ID. `_my_allocation()` refuses (403) any
allocation that belongs to another lecturer.
"""

from flask import abort, current_app, redirect, render_template, request, url_for
from flask_login import current_user

from ...extensions import db
from ...models import AuditLog, ResultStatus, Semester
from ...services import results as result_service
from ...services.errors import ServiceError
from ...web import attempt, csv_response
from . import bp


def _my_allocation(allocation_id: int):
    """Return the allocation if it is mine; otherwise stop with 403 Forbidden."""
    try:
        return result_service.get_allocation(current_user, allocation_id)
    except ServiceError:
        abort(403)


def _sheet_for(allocation):
    """Load (or create) the result sheet and save any newly added student rows."""
    sheet = result_service.open_sheet(allocation)
    db.session.commit()
    return sheet


@bp.route("/")
def dashboard():
    semester = Semester.current()
    allocations = result_service.allocations_for_lecturer(current_user, semester) if semester else []
    rows = []
    for allocation in allocations:
        sheet = result_service.find_sheet(allocation.course_id, allocation.semester_id)
        students = len(result_service.registrations_for_course(allocation.course_id, allocation.semester_id))
        rows.append({"allocation": allocation, "sheet": sheet, "students": students})

    returned = [r for r in rows if r["sheet"] and r["sheet"].status == ResultStatus.RETURNED]
    return render_template(
        "lecturer/dashboard.html", semester=semester, rows=rows, returned=returned,
        total_students=sum(r["students"] for r in rows),
        submitted=sum(1 for r in rows if r["sheet"] and r["sheet"].status in (ResultStatus.SUBMITTED, ResultStatus.APPROVED)),
    )


@bp.route("/courses")
def courses():
    rows = []
    for allocation in result_service.allocations_for_lecturer(current_user):
        sheet = result_service.find_sheet(allocation.course_id, allocation.semester_id)
        rows.append({"allocation": allocation, "sheet": sheet})
    return render_template("lecturer/courses.html", rows=rows)


TABS = ("overview", "class-list", "scores", "submit", "performance", "correction")


@bp.route("/courses/<int:allocation_id>")
def courses_detail(allocation_id: int):
    allocation = _my_allocation(allocation_id)
    sheet = _sheet_for(allocation)
    tab = request.args.get("tab", "overview")
    if tab not in TABS:
        abort(404)
    entries = sorted(sheet.entries, key=lambda e: e.registration.student.student_profile.matric_number)
    trail = list(db.session.scalars(
        db.select(AuditLog).where(AuditLog.entity_type == "ResultSheet", AuditLog.entity_id == sheet.id)
        .order_by(AuditLog.created_at.desc()).limit(15)))
    return render_template(
        "lecturer/course_detail.html", allocation=allocation, sheet=sheet, entries=entries, tab=tab,
        summary=result_service.sheet_summary(sheet), trail=trail,
        max_ca=current_app.config["MAX_CA_SCORE"], max_exam=current_app.config["MAX_EXAM_SCORE"],
    )


@bp.route("/courses/<int:allocation_id>/correction", methods=["POST"])
def courses_correction(allocation_id: int):
    """Ask the department for permission to edit submitted or approved results."""
    allocation = _my_allocation(allocation_id)
    sheet = _sheet_for(allocation)
    attempt(lambda: result_service.request_correction(sheet, current_user, request.form.get("reason", "")),
            "Request sent. Your department will allow or refuse it; you will see the answer here.")
    return redirect(url_for("lecturer.courses_detail", allocation_id=allocation.id, tab="correction"))


@bp.route("/courses/<int:allocation_id>/scores", methods=["POST"])
def courses_scores(allocation_id: int):
    allocation = _my_allocation(allocation_id)
    sheet = _sheet_for(allocation)
    submit = request.form.get("action") == "submit"

    # Read the score boxes. Each row has inputs named ca_<entryId> and exam_<entryId>.
    # Only rows whose boxes were actually sent are updated. (The Submit tab
    # sends no boxes at all: it submits the scores already saved.)
    scores = {
        entry.id: (request.form.get(f"ca_{entry.id}"), request.form.get(f"exam_{entry.id}"))
        for entry in sheet.entries
        if f"ca_{entry.id}" in request.form or f"exam_{entry.id}" in request.form
    }

    if submit:
        ok = attempt(lambda: result_service.save_scores(sheet, scores, current_user, submit=True),
                     "Results submitted for departmental review. They are now locked.")
        if not ok:
            # Submission failed (e.g. a missing score). Keep the lecturer's typing
            # by saving it as a draft instead, if the numbers themselves are valid.
            attempt(lambda: result_service.save_scores(sheet, scores, current_user, submit=False),
                    "Your scores were kept as a draft.")
        tab = "overview" if ok else "scores"
    else:
        attempt(lambda: result_service.save_scores(sheet, scores, current_user, submit=False),
                "Draft saved.")
        tab = request.form.get("next_tab", "scores")
    return redirect(url_for("lecturer.courses_detail", allocation_id=allocation.id,
                            tab=tab if tab in TABS else "scores"))


@bp.route("/courses/<int:allocation_id>/class-list.csv")
def courses_csv(allocation_id: int):
    allocation = _my_allocation(allocation_id)
    sheet = _sheet_for(allocation)
    rows = []
    for entry in sorted(sheet.entries, key=lambda e: e.registration.student.student_profile.matric_number):
        student = entry.registration.student
        rows.append([student.student_profile.matric_number, student.full_name,
                     student.student_profile.level, entry.ca_score, entry.exam_score, entry.total, entry.grade])
    filename = f"{allocation.course.code.replace(' ', '')}_class_list.csv"
    return csv_response(filename, ["Matric No", "Name", "Level", "CA", "Exam", "Total", "Grade"], rows)


@bp.route("/courses/<int:allocation_id>/print")
def courses_print(allocation_id: int):
    allocation = _my_allocation(allocation_id)
    sheet = _sheet_for(allocation)
    entries = sorted(sheet.entries, key=lambda e: e.registration.student.student_profile.matric_number)
    return render_template("lecturer/print_sheet.html", allocation=allocation, sheet=sheet, entries=entries,
                           summary=result_service.sheet_summary(sheet))
