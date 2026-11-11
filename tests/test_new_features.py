"""
Tests for the second round of features:

- Lecturer course tabs and the "request a correction" flow.
- Super Admin: unsuspend/unlock, deletes, session and semester control
  (complete / reopen / edit / add / delete, activity pages), registration edits.
- Department report, academic report, readable audit trail, registration filter.
- Database schema auto-upgrade for older databases.
"""

from datetime import date

import sqlalchemy as sa

from uemp.extensions import db
from uemp.models import (
    AcademicSession,
    AuditLog,
    CourseRegistration,
    Department,
    Faculty,
    Program,
    ResultSheet,
    Semester,
)
from uemp.services import reports
from uemp.services.grading import academic_report

from .conftest import allocation_for, course, current_semester, fill_scores, sheet_for, user


def _session(name) -> AcademicSession:
    db.session.expire_all()
    return db.session.scalar(db.select(AcademicSession).filter_by(name=name))


def _submit_csc201(lecturer_client):
    allocation = allocation_for("CSC 201")
    lecturer_client.get(f"/lecturer/courses/{allocation.id}")
    sheet = sheet_for("CSC 201")
    lecturer_client.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, "30", "45", "submit"))
    assert sheet_for("CSC 201").status == "submitted"
    return allocation, sheet_for("CSC 201")


# --------------------------------------------------------------------------- #
#  Lecturer tabs and correction requests
# --------------------------------------------------------------------------- #
def test_lecturer_course_page_has_every_tab(as_lecturer):
    allocation = allocation_for("CSC 201")
    for tab, text in [("overview", "Overview"), ("class-list", "CSC/2025/002"), ("scores", 'name="ca_'),
                      ("submit", "Submit"), ("performance", "Performance"), ("correction", "orrection")]:
        response = as_lecturer.get(f"/lecturer/courses/{allocation.id}?tab={tab}")
        assert response.status_code == 200 and text in response.get_data(as_text=True), tab


def test_correction_request_granted_then_lecturer_can_edit(client_as):
    lecturer, admin = client_as("lecturer@uemp.edu.ng"), client_as("csc.admin@uemp.edu.ng")
    allocation, sheet = _submit_csc201(lecturer)

    # Submitted results are locked: saving again changes nothing.
    first = sheet.entries[0]
    lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data={"action": "save", f"ca_{first.id}": "1"})
    assert sheet_for("CSC 201").entries[0].ca_score == 30

    lecturer.post(f"/lecturer/courses/{allocation.id}/correction", data={"reason": "Wrong exam score for one student"})
    sheet = sheet_for("CSC 201")
    assert sheet.correction_pending and "Wrong exam score" in sheet.correction_reason

    # The request shows in the department's results queue, and approval waits for a decision.
    assert "correction" in admin.get("/admin/results?status=correction").get_data(as_text=True).lower()
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    assert sheet_for("CSC 201").status == "submitted"

    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "grant", "comment": "Go ahead"})
    sheet = sheet_for("CSC 201")
    assert sheet.status == "returned" and not sheet.correction_pending
    lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data={"action": "save", f"ca_{first.id}": "20",
                                                                      f"exam_{first.id}": "45"})
    assert sheet_for("CSC 201").entries[0].ca_score == 20


def test_correction_request_declined_needs_a_reason(client_as):
    lecturer, admin = client_as("lecturer@uemp.edu.ng"), client_as("csc.admin@uemp.edu.ng")
    allocation, sheet = _submit_csc201(lecturer)
    lecturer.post(f"/lecturer/courses/{allocation.id}/correction", data={"reason": "Please recheck the exam scores"})
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "decline", "comment": ""})
    assert sheet_for("CSC 201").correction_pending          # no reason given -> nothing happens
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "decline", "comment": "Scores are correct"})
    sheet = sheet_for("CSC 201")
    assert not sheet.correction_pending and sheet.status == "submitted"


def test_correction_request_needs_submitted_results(as_lecturer):
    allocation = allocation_for("CSC 201")
    as_lecturer.get(f"/lecturer/courses/{allocation.id}")
    as_lecturer.post(f"/lecturer/courses/{allocation.id}/correction", data={"reason": "x"})
    assert not sheet_for("CSC 201").correction_pending


# --------------------------------------------------------------------------- #
#  Account status: Super Admin only; unsuspend and unlock
# --------------------------------------------------------------------------- #
def test_super_admin_suspends_and_unsuspends(as_super, app):
    student = user("csc26002@uemp.edu.ng")
    as_super.post(f"/admin/users/{student.id}/status", data={"status": "suspended"})
    assert user("csc26002@uemp.edu.ng").status == "suspended"
    response = as_super.post(f"/admin/users/{student.id}/status", data={"status": "active"}, follow_redirects=True)
    assert b"unsuspended" in response.data and user("csc26002@uemp.edu.ng").status == "active"


def test_super_admin_unlocks_a_locked_account(as_super, app):
    from datetime import timedelta

    from uemp.extensions import db as _db
    from uemp.models.mixins import utcnow
    student = user("csc26002@uemp.edu.ng")
    student.locked_until, student.failed_logins = utcnow() + timedelta(minutes=10), 5
    _db.session.commit()
    assert "Locked" in as_super.get("/super/users?locked=1").get_data(as_text=True)
    as_super.post(f"/admin/users/{student.id}/unlock")
    assert user("csc26002@uemp.edu.ng").locked_until is None


# --------------------------------------------------------------------------- #
#  Deletes
# --------------------------------------------------------------------------- #
def test_delete_student_removes_their_registrations_and_keeps_audit_names(as_super):
    student = user("csc26002@uemp.edu.ng")
    sid, name = student.id, student.full_name
    as_super.post(f"/admin/users/{sid}/delete")
    assert user("csc26002@uemp.edu.ng") is None
    assert not db.session.scalar(db.select(sa.func.count()).select_from(CourseRegistration).filter_by(student_id=sid))
    entry = db.session.scalar(db.select(AuditLog).where(AuditLog.action == "user.deleted"))
    assert entry is not None and name in (entry.description or "")


def test_lecturer_with_allocations_cannot_be_deleted(as_super):
    lecturer = user("lecturer@uemp.edu.ng")
    response = as_super.post(f"/admin/users/{lecturer.id}/delete", follow_redirects=True)
    assert user("lecturer@uemp.edu.ng") is not None and b"cannot" in response.data.lower()


def test_dept_admin_cannot_delete(as_csc_admin):
    assert as_csc_admin.post(f"/admin/users/{user('csc26002@uemp.edu.ng').id}/delete").status_code == 403


def test_delete_unused_faculty_department_programme(as_super):
    from uemp.services import academic, catalogue
    admin = user("admin@uemp.edu.ng")
    faculty = academic.save_faculty(admin, None, name="Faculty of Arts", code="ART")
    dept = academic.save_department(admin, None, name="History", code="HIS", faculty_id=faculty.id)
    program = catalogue.save_program(admin, None, name="History", code="BA-HIS", degree="B.A.", duration_years=4,
                                     department_id=dept.id)
    db.session.commit()   # the requests below use their own database connection
    fid, did, pid = faculty.id, dept.id, program.id

    as_super.post(f"/super/faculties/{fid}/delete")                    # still has a department
    assert db.session.get(Faculty, fid) is not None
    as_super.post(f"/admin/programs/{pid}/delete")
    as_super.post(f"/super/faculties/departments/{did}/delete")
    as_super.post(f"/super/faculties/{fid}/delete")
    db.session.expire_all()
    assert db.session.get(Program, pid) is None and db.session.get(Department, did) is None
    assert db.session.get(Faculty, fid) is None


def test_department_with_students_cannot_be_deleted(as_super):
    csc = db.session.scalar(db.select(Department).filter_by(code="CSC"))
    as_super.post(f"/super/faculties/departments/{csc.id}/delete")
    assert db.session.get(Department, csc.id) is not None


# --------------------------------------------------------------------------- #
#  Sessions and semesters
# --------------------------------------------------------------------------- #
def test_create_edit_add_and_delete_empty_session(as_super):
    as_super.post("/super/sessions", data={"name": "2030/2031"})
    s = _session("2030/2031")
    assert len(s.semesters) == 2
    as_super.post(f"/super/sessions/{s.id}/edit", data={"name": "2030/2031", "start_date": "2030-10-01",
                                                       "end_date": "2031-08-31"})
    assert _session("2030/2031").start_date == date(2030, 10, 1)

    second = next(sem for sem in s.semesters if sem.term == "second")
    as_super.post(f"/super/semesters/{second.id}/delete")
    assert len(_session("2030/2031").semesters) == 1
    as_super.post(f"/super/sessions/{s.id}/action", data={"action": "add_semester", "term": "second"})
    assert len(_session("2030/2031").semesters) == 2

    as_super.post(f"/super/sessions/{s.id}/action", data={"action": "delete"})
    assert _session("2030/2031") is None


def test_session_with_records_cannot_be_deleted(as_super):
    s = _session("2026/2027")
    as_super.post(f"/super/sessions/{s.id}/action", data={"action": "delete"})
    assert _session("2026/2027") is not None


def test_complete_and_reopen_semester_and_session(as_super):
    s = _session("2025/2026")
    for sem in s.semesters:
        response = as_super.post(f"/super/sessions/semester/{sem.id}", data={"action": "complete"}, follow_redirects=True)
        assert response.status_code == 200
    s = _session("2025/2026")
    assert all(sem.is_completed and not sem.registration_open for sem in s.semesters)
    as_super.post(f"/super/sessions/{s.id}/action", data={"action": "complete"})
    assert _session("2025/2026").is_completed and _session("2025/2026").status_label == "Completed"

    # A completed semester cannot become current or reopen registration.
    sem = _session("2025/2026").semesters[0]
    as_super.post(f"/super/sessions/semester/{sem.id}", data={"action": "make_current"})
    db.session.expire_all()
    assert not db.session.get(Semester, sem.id).is_current
    as_super.post(f"/super/sessions/{s.id}/action", data={"action": "reopen"})
    as_super.post(f"/super/sessions/semester/{sem.id}", data={"action": "reopen"})
    db.session.expire_all()
    assert not db.session.get(Semester, sem.id).is_completed


def test_session_cannot_complete_before_its_semesters(as_super):
    s = _session("2026/2027")
    as_super.post(f"/super/sessions/{s.id}/action", data={"action": "complete"})
    assert not _session("2026/2027").is_completed


def test_semester_and_session_activity_pages(as_super):
    sem = current_semester()
    page = as_super.get(f"/super/semesters/{sem.id}").get_data(as_text=True)
    assert "Students registered" in page and "What happened" in page
    page = as_super.get(f"/super/sessions/{sem.session_id}").get_data(as_text=True)
    assert "First Semester" in page and "Second Semester" in page
    assert as_super.get(f"/super/semesters/{sem.id}?category=Registrations").status_code == 200


def test_semester_dates_must_fit_the_session(as_super):
    sem = current_semester()
    response = as_super.post(f"/super/semesters/{sem.id}/edit", data={"start_date": "2020-01-01",
                                                                      "end_date": "2020-02-01"},
                             follow_redirects=True)
    assert db.session.get(Semester, sem.id).start_date is None
    assert response.status_code == 200


# --------------------------------------------------------------------------- #
#  Course registrations: filter (dept admin) and edits (super admin)
# --------------------------------------------------------------------------- #
def test_registration_filter_by_course_and_programme(as_csc_admin):
    sem = current_semester()
    page = as_csc_admin.get(f"/admin/registrations?semester_id={sem.id}&course_id={course('CSC 201').id}")
    text = page.get_data(as_text=True)
    assert "CSC/2025/002" in text and "CSC 203" not in text.split("<tbody")[-1]
    # A course id left over from another semester is ignored instead of emptying the list.
    text = as_csc_admin.get(f"/admin/registrations?semester_id={sem.id}&course_id=999999").get_data(as_text=True)
    assert "CSC/2025/002" in text
    text = as_csc_admin.get(f"/admin/registrations?semester_id={sem.id}&q=Data Structures").get_data(as_text=True)
    assert "CSC 201" in text


def test_super_admin_edits_registration_type_and_remarks(as_super, client_as):
    reg = db.session.scalar(db.select(CourseRegistration).filter_by(
        student_id=user("csc25002@uemp.edu.ng").id, course_id=course("CSC 203").id))
    page = as_super.get(f"/admin/registrations/{reg.id}").get_data(as_text=True)
    assert "registration_type" in page
    as_super.post(f"/admin/registrations/{reg.id}", data={"course_id": reg.course_id, "registration_type": "carryover",
                                                          "remarks": "Resit approved by senate"})
    db.session.expire_all()
    reg = db.session.get(CourseRegistration, reg.id)
    assert reg.registration_type == "carryover" and reg.remarks == "Resit approved by senate"
    # Department admins can look but not change.
    dept_admin = client_as("csc.admin@uemp.edu.ng")
    assert dept_admin.get(f"/admin/registrations/{reg.id}").status_code == 200
    assert dept_admin.post(f"/admin/registrations/{reg.id}", data={"registration_type": "regular"}).status_code == 403


def test_registration_with_scores_cannot_be_changed(as_super, client_as):
    lecturer = client_as("lecturer@uemp.edu.ng")
    _submit_csc201(lecturer)
    reg = db.session.scalar(db.select(CourseRegistration).filter_by(
        student_id=user("csc25002@uemp.edu.ng").id, course_id=course("CSC 201").id))
    as_super.post(f"/admin/registrations/{reg.id}/delete")
    assert db.session.get(CourseRegistration, reg.id) is not None


# --------------------------------------------------------------------------- #
#  Reports
# --------------------------------------------------------------------------- #
def test_department_report_numbers_and_formulas(as_csc_admin):
    csc = db.session.scalar(db.select(Department).filter_by(code="CSC"))
    r = reports.department_report([csc.id], current_semester())
    assert r["students"] > 0 and r["offered"] > 0 and 0 <= r["coverage"] <= 100
    assert len(r["formulas"]) >= 8
    page = as_csc_admin.get("/admin/reports").get_data(as_text=True)
    assert "Department report" in page and "How these numbers are calculated" in page
    assert "Department report" in as_csc_admin.get("/admin/").get_data(as_text=True)


def test_super_admin_dashboard_compares_and_opens_departments(as_super):
    page = as_super.get("/admin/").get_data(as_text=True)
    assert "Computer Science" in page and "Economics" in page
    csc = db.session.scalar(db.select(Department).filter_by(code="CSC"))
    page = as_super.get(f"/admin/?department_id={csc.id}").get_data(as_text=True)
    assert "Department report" in page and "Computer Science" in page


def test_academic_report_has_cumulative_figures(as_student):
    student = user("student@uemp.edu.ng")
    report = academic_report(student.id)
    assert report.rows and report.rows[-1].ctcr >= report.rows[0].tcr
    page = as_student.get("/student/statement").get_data(as_text=True)
    for text in ("CGPA", "CTCR", "Grading scale", "Outstanding courses", "Standing"):
        assert text in page


def test_admin_can_print_a_students_academic_report(as_csc_admin):
    page = as_csc_admin.get(f"/admin/students/{user('student@uemp.edu.ng').id}/academic-report")
    assert page.status_code == 200 and b"Academic Report" in page.data


# --------------------------------------------------------------------------- #
#  Readable audit trail
# --------------------------------------------------------------------------- #
def test_audit_trail_reads_in_plain_english(as_super, client_as):
    _submit_csc201(client_as("lecturer@uemp.edu.ng"))
    page = as_super.get("/super/audit").get_data(as_text=True)
    assert "Results submitted" in page or "submitted" in page.lower()
    page = as_super.get("/super/audit?category=Results").get_data(as_text=True)
    assert "Lecturer" in page
    assert as_super.get("/super/audit?role=lecturer&from=2000-01-01&to=bad-date").status_code == 200
    entry = db.session.scalar(db.select(AuditLog).order_by(AuditLog.id.desc()))
    assert entry.actor_name and entry.actor_role


# --------------------------------------------------------------------------- #
#  Schema upgrade for databases created by an older version
# --------------------------------------------------------------------------- #
def test_schema_upgrade_adds_missing_columns(tmp_path):
    from uemp.schema import missing_columns, upgrade_schema
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("ALTER TABLE course_registrations DROP COLUMN remarks"))
        conn.execute(sa.text("ALTER TABLE result_sheets DROP COLUMN correction_reason"))
    assert missing_columns(engine, db.metadata)
    upgrade_schema(engine, db.metadata)
    assert not missing_columns(engine, db.metadata)
    assert ResultSheet.__tablename__ == "result_sheets"


def test_correction_requests_from_older_semesters_are_listed(client_as):
    lecturer, admin = client_as("lecturer@uemp.edu.ng"), client_as("csc.admin@uemp.edu.ng")
    allocation, sheet = _submit_csc201(lecturer)
    lecturer.post(f"/lecturer/courses/{allocation.id}/correction", data={"reason": "One exam score is wrong"})
    old_semester = current_semester()
    other = next(s for s in old_semester.session.semesters if s.id != old_semester.id)
    client_as("admin@uemp.edu.ng").post(f"/super/sessions/semester/{other.id}", data={"action": "make_current"})
    assert current_semester().id == other.id
    page = admin.get("/admin/results?status=correction").get_data(as_text=True)
    assert "CSC 201" in page and old_semester.name in page


def test_department_comparison_matches_each_department_report(client_as):
    # Give the comparison some approved results to work with.
    lecturer, admin = client_as("lecturer@uemp.edu.ng"), client_as("csc.admin@uemp.edu.ng")
    _, sheet = _submit_csc201(lecturer)
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    keys = ("students", "lecturers", "registration_rate", "completion", "pass_rate", "average_gpa")
    db.session.expire_all()   # read what the requests above saved, not this session's cached copies
    for semester in (current_semester(), None):
        for row in reports.department_comparison(semester):
            full = reports.department_report([row["department"].id], semester)
            for key in keys:
                assert row[key] == full[key], (row["department"].code, semester, key)
            assert row["at_risk"] == len(full["at_risk"])
