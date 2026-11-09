"""Brief §6 — Important Business Rules 1–8, plus the GPA requirement."""

import pytest

from uemp.extensions import db
from uemp.models import AuditLog, Semester
from uemp.services import grading

from .conftest import allocation_for, course, fill_scores, sheet_for, user


def _register(client, *codes):
    return client.post("/student/courses", data={"course_ids": [course(c).id for c in codes]}, follow_redirects=True)


# Rule 1 — only courses for the student's department, programme, level AND semester.
@pytest.mark.parametrize("code, reason", [
    ("CSC 101", "wrong level (100L course for a 200L student)"),
    ("CSC 202", "wrong semester (second-semester course)"),
    ("ECO 201", "wrong programme / department"),
])
def test_rule_1_only_eligible_courses_can_be_registered(as_student, code, reason):
    response = _register(as_student, code)
    assert b"not available to you" in response.data, reason


def test_rule_1_100_level_student_cannot_take_200_level_course(client_as):
    response = _register(client_as("csc26001@uemp.edu.ng"), "CSC 201")
    assert b"not available to you" in response.data


# Rule 2 — no course twice in the same semester (but a new semester is fine, e.g. a resit).
def test_rule_2_no_duplicate_in_same_semester_but_allowed_next_session(as_student, client_as):
    _register(as_student, "CSC 201")
    assert b"already registered" in _register(as_student, "CSC 201").data

    sa = client_as("admin@uemp.edu.ng")
    sa.post("/super/sessions", data={"name": "2027/2028"})
    db.session.expire_all()
    new_first = db.session.scalar(db.select(Semester).where(Semester.is_current.is_(False), Semester.term == "first")
                                  .order_by(Semester.id.desc()))
    sa.post(f"/super/sessions/semester/{new_first.id}", data={"action": "make_current"})
    sa.post(f"/super/sessions/semester/{new_first.id}", data={"action": "open"})
    assert b"Courses registered successfully" in _register(as_student, "CSC 201").data


# Rule 3 — lecturers only enter results for courses assigned to them.
def test_rule_3_lecturer_limited_to_assigned_courses(client_as):
    bakare = client_as("bakare@uemp.edu.ng")
    assert bakare.get(f"/lecturer/courses/{allocation_for('CSC 201').id}").status_code == 403
    assert bakare.post(f"/lecturer/courses/{allocation_for('CSC 201').id}/scores",
                       data=fill_scores(sheet_for("CSC 201"))).status_code == 403


# Rule 4 — results must be submitted before departmental approval.
def test_rule_4_draft_cannot_be_approved(as_csc_admin):
    sheet = sheet_for("CSC 201")
    response = as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"},
                                 follow_redirects=True)
    assert b"Only submitted results can be approved" in response.data
    assert sheet_for("CSC 201").status == "draft"


# Rule 5 — only that department's administrators approve its results.
def test_rule_5_other_department_admin_cannot_approve(as_eco_admin):
    sheet = sheet_for("CSC 203")
    assert as_eco_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"}).status_code == 403
    assert sheet_for("CSC 203").status == "submitted"


def test_rule_5_service_rejects_out_of_department_reviewer(app):
    from uemp.services import results
    from uemp.services.errors import ServiceError
    with pytest.raises(ServiceError, match="your own department"):
        results.approve(sheet_for("CSC 203"), user("eco.admin@uemp.edu.ng"))


# Rule 6 — students only see approved results (and lose sight of them if reopened).
def test_rule_6_only_approved_results_visible(client_as):
    student = client_as("csc25003@uemp.edu.ng")
    admin = client_as("csc.admin@uemp.edu.ng")
    sheet = sheet_for("CSC 203")

    def visible():
        history = grading.academic_history(user("csc25003@uemp.edu.ng").id)
        return any(e.sheet_id == sheet.id for e in history.all_entries)

    assert not visible()                                               # submitted
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    assert visible()                                                   # approved
    assert "Discrete Structures" in student.get("/student/results").get_data(as_text=True)
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reopen", "comment": "Correction"})
    assert not visible()                                               # reopened → hidden again


# Rule 7 — Super Admin has university-wide administrative access (also see endpoint matrix).
def test_rule_7_super_admin_reaches_every_department(as_super):
    for code in ["CSC", "ECO", "EEE", "MTH"]:
        from uemp.models import Department
        dept = db.session.scalar(db.select(Department).filter_by(code=code))
        assert as_super.get(f"/admin/students?department_id={dept.id}").status_code == 200


# Rule 8 — every important result action is traceable.
def test_rule_8_every_result_action_is_audited(client_as):
    lecturer = client_as("lecturer@uemp.edu.ng")
    admin = client_as("csc.admin@uemp.edu.ng")
    allocation = allocation_for("CSC 201")
    lecturer.get(f"/lecturer/courses/{allocation.id}")
    sheet = sheet_for("CSC 201")
    url = f"/lecturer/courses/{allocation.id}/scores"
    lecturer.post(url, data=fill_scores(sheet, "30", "40"))                       # draft
    lecturer.post(url, data=fill_scores(sheet, "30", "41"))                       # modification
    lecturer.post(url, data=fill_scores(sheet, "30", "41", action="submit"))      # submission
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reject", "comment": "x"})   # rejection
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})                 # (refused: not submitted)
    lecturer.post(url, data=fill_scores(sheet, "30", "41", action="submit"))
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})                 # approval
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reopen", "comment": "y"})  # reopening

    actions = set(db.session.scalars(db.select(AuditLog.action).filter_by(entity_type="ResultSheet", entity_id=sheet.id)))
    assert {"result.draft_saved", "result.modified", "result.submitted", "result.rejected",
            "result.approved", "result.reopened"} <= actions
    modified = db.session.scalar(db.select(AuditLog).filter_by(action="result.modified", entity_id=sheet.id))
    assert "Exam 40→41" in modified.description


# GPA — documented scale, credit-unit weighted, and configurable.
def test_gpa_uses_credit_units(app):
    assert grading.calculate_gpa([(3, 5), (3, 5), (2, 0)]) == 3.75   # (15+15+0)/8


def test_grading_scale_is_configurable(app):
    app.config["GRADING_SCALE"] = [(75, "A", 4.0), (50, "B", 3.0), (0, "F", 0.0)]   # e.g. a 4-point scale
    assert grading.grade_for(74) == ("B", 3.0) and grading.grade_for(75) == ("A", 4.0)
