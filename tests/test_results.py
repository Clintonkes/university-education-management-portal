"""Workflows 2 & 3 — Lecturer result submission and departmental approval."""

from uemp.extensions import db
from uemp.models import AuditLog

from .conftest import allocation_for, login, sheet_for, user


def _fill_all(sheet, ca="30", exam="45"):
    data = {}
    for entry in sheet.entries:
        data[f"ca_{entry.id}"] = ca
        data[f"exam_{entry.id}"] = exam
    return data


def _open_csc201(client):
    allocation = allocation_for("CSC 201")
    assert client.get(f"/lecturer/courses/{allocation.id}").status_code == 200
    return allocation, sheet_for("CSC 201")


# --------------------------------------------------------------------------- #
#  Lecturer (Workflow 2)
# --------------------------------------------------------------------------- #
def test_lecturer_sees_registered_students(as_lecturer):
    allocation = allocation_for("CSC 201")
    page = as_lecturer.get(f"/lecturer/courses/{allocation.id}").get_data(as_text=True)
    assert "CSC/2025/002" in page


def test_lecturer_cannot_open_course_assigned_to_someone_else(as_lecturer):
    assert as_lecturer.get(f"/lecturer/courses/{allocation_for('CSC 203').id}").status_code == 403


def test_save_draft_computes_total_and_grade(as_lecturer):
    allocation, sheet = _open_csc201(as_lecturer)
    as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data={**_fill_all(sheet), "action": "save"})
    db.session.refresh(sheet)
    entry = sheet.entries[0]
    assert (entry.total, entry.grade, entry.grade_point) == (75, "A", 5.0)
    assert sheet.status == "draft"


def test_out_of_range_score_is_rejected(as_lecturer, app):
    allocation, sheet = _open_csc201(as_lecturer)
    data = _fill_all(sheet, ca=str(app.config["MAX_CA_SCORE"] + 1))
    response = as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data={**data, "action": "save"},
                                follow_redirects=True)
    assert b"must be between 0 and 40" in response.data
    db.session.refresh(sheet)
    assert sheet.entries[0].ca_score is None


def test_cannot_submit_with_missing_scores(as_lecturer):
    allocation, sheet = _open_csc201(as_lecturer)
    data = _fill_all(sheet)
    data[f"exam_{sheet.entries[0].id}"] = ""
    response = as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data={**data, "action": "submit"},
                                follow_redirects=True)
    assert b"Enter both CA and exam scores" in response.data
    db.session.refresh(sheet)
    assert sheet.status == "draft"
    assert sheet.entries[1].ca_score == 30  # the typed scores were kept as a draft


def test_submitted_results_are_locked(as_lecturer):
    allocation, sheet = _open_csc201(as_lecturer)
    as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data={**_fill_all(sheet), "action": "submit"})
    db.session.refresh(sheet)
    assert sheet.status == "submitted"
    response = as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores",
                                data={**_fill_all(sheet, ca="10"), "action": "save"}, follow_redirects=True)
    assert b"can no longer be edited" in response.data
    db.session.refresh(sheet)
    assert sheet.entries[0].ca_score == 30


# --------------------------------------------------------------------------- #
#  Department review (Workflow 3) + student visibility
# --------------------------------------------------------------------------- #
def test_students_cannot_see_unapproved_results(client):
    login(client, "csc25002@uemp.edu.ng", "Student@1234")
    page = client.get("/student/results").get_data(as_text=True)
    assert "Awaiting approval" in page and "CSC 203" in page   # listed as pending only
    history = client.get("/student/history").get_data(as_text=True)
    assert "First Semester 2026/2027</a>" not in history      # no row in the history table
    assert "Second Semester 2025/2026</a>" in history


def test_approval_publishes_results_to_students(client):
    sheet = sheet_for("CSC 203")
    login(client, "csc.admin@uemp.edu.ng", "Admin@1234")
    client.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    db.session.refresh(sheet)
    assert sheet.status == "approved"
    assert sheet.reviewed_by_id == user("csc.admin@uemp.edu.ng").id
    assert db.session.scalar(db.select(AuditLog).filter_by(action="result.approved", entity_id=sheet.id))

    client.post("/logout")
    login(client, "csc25002@uemp.edu.ng", "Student@1234")
    history = client.get("/student/history").get_data(as_text=True)
    assert "First Semester 2026/2027</a>" in history


def test_reject_requires_comment_and_returns_sheet(as_csc_admin):
    sheet = sheet_for("CSC 203")
    response = as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reject", "comment": ""},
                                 follow_redirects=True)
    assert b"explain what the lecturer needs to correct" in response.data
    as_csc_admin.post(f"/admin/results/{sheet.id}/decision",
                      data={"decision": "reject", "comment": "Check CA for CSC/2025/004"})
    db.session.refresh(sheet)
    assert sheet.status == "returned" and "CSC/2025/004" in sheet.review_comment


def test_full_cycle_submit_reject_correct_resubmit_approve(client):
    # Lecturer submits
    login(client, "lecturer@uemp.edu.ng", "Lecturer@1234")
    allocation, sheet = _open_csc201(client)
    client.post(f"/lecturer/courses/{allocation.id}/scores", data={**_fill_all(sheet), "action": "submit"})
    client.post("/logout")

    # Admin rejects with feedback
    login(client, "csc.admin@uemp.edu.ng", "Admin@1234")
    client.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reject", "comment": "Exam too high"})
    client.post("/logout")

    # Lecturer sees feedback, corrects and resubmits — the change is audited
    login(client, "lecturer@uemp.edu.ng", "Lecturer@1234")
    assert b"Exam too high" in client.get("/lecturer/").data
    client.post(f"/lecturer/courses/{allocation.id}/scores", data={**_fill_all(sheet, exam="40"), "action": "submit"})
    modified = db.session.scalar(db.select(AuditLog).filter_by(action="result.modified", entity_id=sheet.id))
    assert modified and "Exam 45→40" in modified.description
    client.post("/logout")

    # Admin approves
    login(client, "csc.admin@uemp.edu.ng", "Admin@1234")
    client.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    db.session.refresh(sheet)
    assert sheet.status == "approved"
    assert sheet.entries[0].total == 70


def test_reopen_approved_results(as_csc_admin):
    sheet = sheet_for("CSC 203")
    as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reopen", "comment": "Typo in CA"})
    db.session.refresh(sheet)
    assert sheet.status == "returned"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="result.reopened"))


def test_draft_results_cannot_be_approved(as_csc_admin, as_lecturer):
    sheet = sheet_for("CSC 201")
    response = as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"},
                                 follow_redirects=True)
    assert b"Only submitted results can be approved" in response.data
