"""Brief §2B — LECTURER: abilities and restrictions."""

import csv
import io

from uemp.extensions import db
from uemp.models import CourseAllocation, ResultSheet, Semester

from .conftest import allocation_for, fill_scores, sheet_for, user


def _csc201(client):
    allocation = allocation_for("CSC 201")
    client.get(f"/lecturer/courses/{allocation.id}")  # creates the sheet rows
    return allocation, sheet_for("CSC 201")


def test_log_in_to_lecturer_dashboard(as_lecturer):
    page = as_lecturer.get("/lecturer/").get_data(as_text=True)
    assert "Dr. Adaeze Okafor" in page and "CSC 201" in page


def test_view_and_manage_assigned_courses_only(as_lecturer):
    page = as_lecturer.get("/lecturer/courses").get_data(as_text=True)
    assert "CSC 201" in page and "CSC 101" in page   # this semester + last session
    assert "CSC 203" not in page                      # taught by Prof. Bakare


def test_view_students_registered_for_assigned_course(as_lecturer):
    page = as_lecturer.get(f"/lecturer/courses/{allocation_for('CSC 201').id}?tab=class-list").get_data(as_text=True)
    for n in range(2, 13):
        assert f"CSC/2025/{n:03d}" in page
    assert "CSC/2025/001" not in page  # the demo student has not registered CSC 201


def test_access_class_list_csv_and_print(as_lecturer):
    allocation = allocation_for("CSC 201")
    response = as_lecturer.get(f"/lecturer/courses/{allocation.id}/class-list.csv")
    assert response.mimetype == "text/csv"
    rows = list(csv.reader(io.StringIO(response.get_data(as_text=True))))
    assert rows[0][:3] == ["Matric No", "Name", "Level"] and len(rows) == 12  # header + 11 students
    printed = as_lecturer.get(f"/lecturer/courses/{allocation.id}/print").get_data(as_text=True)
    assert "Class List & Score Sheet" in printed and "CSC/2025/002" in printed


def test_enter_ca_and_exam_scores_and_save_as_draft(as_lecturer):
    allocation, sheet = _csc201(as_lecturer)
    response = as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, "25", "40"),
                                follow_redirects=True)
    assert b"Draft saved" in response.data
    db.session.refresh(sheet)
    assert sheet.status == "draft" and all((e.total, e.grade) == (65, "B") for e in sheet.entries)


def test_partial_draft_is_allowed(as_lecturer):
    allocation, sheet = _csc201(as_lecturer)
    first = sheet.entries[0]
    as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores",
                     data={"action": "save", f"ca_{first.id}": "20", f"exam_{first.id}": ""})
    db.session.refresh(first)
    assert first.ca_score == 20 and first.total is None and first.grade is None


def test_non_numeric_and_negative_scores_rejected(as_lecturer):
    allocation, sheet = _csc201(as_lecturer)
    for bad, message in [("abc", b"must be a number"), ("-1", b"must be between 0 and 40")]:
        response = as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores",
                                    data=fill_scores(sheet, ca=bad), follow_redirects=True)
        assert message in response.data


def test_decimal_scores_are_accepted(as_lecturer):
    allocation, sheet = _csc201(as_lecturer)
    as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, "29.5", "40"))
    db.session.refresh(sheet)
    assert sheet.entries[0].total == 69.5 and sheet.entries[0].grade == "B"


def test_submit_completed_results_for_departmental_review(as_lecturer):
    allocation, sheet = _csc201(as_lecturer)
    response = as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores",
                                data=fill_scores(sheet, action="submit"), follow_redirects=True)
    assert b"submitted for departmental review" in response.data
    db.session.refresh(sheet)
    assert sheet.status == "submitted" and sheet.submitted_at is not None


def test_view_submission_status_and_feedback(client_as):
    lecturer = client_as("lecturer@uemp.edu.ng")
    allocation, sheet = _csc201(lecturer)
    lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, action="submit"))
    assert "Awaiting review" in lecturer.get("/lecturer/courses").get_data(as_text=True)

    admin = client_as("csc.admin@uemp.edu.ng")
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reject", "comment": "Recheck CA for 007"})

    dashboard = lecturer.get("/lecturer/").get_data(as_text=True)
    detail = lecturer.get(f"/lecturer/courses/{allocation.id}").get_data(as_text=True)
    assert "Recheck CA for 007" in dashboard and "Recheck CA for 007" in detail
    assert "Returned" in detail


def test_view_course_and_student_performance_summary(as_lecturer):
    allocation, sheet = _csc201(as_lecturer)
    data = fill_scores(sheet, "30", "45")                       # 75 = A
    first = sheet.entries[0]
    data[f"ca_{first.id}"], data[f"exam_{first.id}"] = "10", "20"  # 30 = F
    as_lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=data)
    page = as_lecturer.get(f"/lecturer/courses/{allocation.id}?tab=performance").get_data(as_text=True)
    expected_average = round((75 * 10 + 30) / 11, 1)
    assert f">{expected_average}<" in page.replace(" ", "")
    assert "91%" in page  # 10 of 11 passed


# --------------------------------------------------------------------------- #
#  Restrictions
# --------------------------------------------------------------------------- #
def test_lecturers_can_only_manage_courses_assigned_to_them(as_lecturer):
    other = allocation_for("CSC 203")  # Prof. Bakare's course
    sheet = sheet_for("CSC 203")
    for url in [f"/lecturer/courses/{other.id}", f"/lecturer/courses/{other.id}/class-list.csv",
                f"/lecturer/courses/{other.id}/print"]:
        assert as_lecturer.get(url).status_code == 403
    assert as_lecturer.post(f"/lecturer/courses/{other.id}/scores", data=fill_scores(sheet, "0", "0")).status_code == 403
    db.session.refresh(sheet)
    assert sheet.entries[0].ca_score != 0


def test_lecturers_cannot_modify_courses_or_students_outside_their_role(as_lecturer):
    student = user("csc25002@uemp.edu.ng")
    assert as_lecturer.post("/admin/courses/new", data={"code": "CSC 999"}).status_code == 403
    assert as_lecturer.post(f"/admin/students/{student.id}/edit", data={}).status_code == 403
    assert as_lecturer.post("/admin/allocations", data={}).status_code == 403


def test_submitted_results_cannot_be_edited_without_reopening(client_as):
    lecturer = client_as("lecturer@uemp.edu.ng")
    allocation, sheet = _csc201(lecturer)
    lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, action="submit"))
    blocked = lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, "1", "1"),
                            follow_redirects=True)
    assert b"can no longer be edited" in blocked.data

    admin = client_as("csc.admin@uemp.edu.ng")
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reopen", "comment": "Authorised fix"})
    lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, "31", "45"))
    db.session.refresh(sheet)
    assert sheet.status == "returned" and sheet.entries[0].ca_score == 31


def test_lecturers_cannot_approve_results(as_lecturer):
    assert as_lecturer.post(f"/admin/results/{sheet_for('CSC 203').id}/decision",
                            data={"decision": "approve"}).status_code == 403


def test_nobody_can_approve_results_they_submitted(app):
    """Even if a lecturer is later promoted to department admin, they cannot approve their own sheet."""
    from uemp.services import results
    from uemp.services.errors import ServiceError
    import pytest

    sheet = sheet_for("CSC 203")
    bakare = user("bakare@uemp.edu.ng")
    bakare.role = "dept_admin"
    db.session.commit()
    with pytest.raises(ServiceError, match="submitted yourself"):
        results.approve(sheet, bakare)


def test_reallocated_course_moves_to_new_lecturer(client_as):
    admin = client_as("csc.admin@uemp.edu.ng")
    alloc = allocation_for("CSC 201")
    admin.post("/admin/allocations", data={"course_id": alloc.course_id, "lecturer_id": user("musa@uemp.edu.ng").id})
    assert client_as("lecturer@uemp.edu.ng").get(f"/lecturer/courses/{alloc.id}").status_code == 403
    assert client_as("musa@uemp.edu.ng").get(f"/lecturer/courses/{alloc.id}").status_code == 200
    db.session.expire_all()
    assert db.session.get(ResultSheet, sheet_for("CSC 201").id).lecturer_id == user("musa@uemp.edu.ng").id
    assert db.session.scalar(db.select(db.func.count(CourseAllocation.id)).filter_by(
        course_id=alloc.course_id, semester_id=Semester.current().id)) == 1
