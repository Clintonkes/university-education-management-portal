"""
Brief §4 — Important System Workflows, each followed step by step.

The comments "# 1." "# 2." … match the numbered steps in the brief.
Every step is done through the web pages, the way a real user would.
"""

import re

from uemp.extensions import db
from uemp.models import AuditLog, Faculty, Department, AcademicSession

from .conftest import fill_scores, login, sheet_for, user


def test_workflow_1_student_course_registration(client_as):
    # 1. Student logs in.
    student = client_as("student@uemp.edu.ng")
    # 2. System identifies the student's department, program and academic level.
    dashboard = student.get("/student/").get_data(as_text=True)
    assert "B.Sc. Computer Science" in dashboard and "200 Level" in dashboard and "Computer Science" in dashboard
    # 3. Student views available courses for the current semester.
    page = student.get("/student/courses").get_data(as_text=True)
    assert "First Semester 2026/2027" in page
    offered = re.findall(r'name="course_ids" value="(\d+)"', page)
    assert len(offered) == 4
    # 4. Student selects courses and submits registration.
    response = student.post("/student/courses", data={"course_ids": offered}, follow_redirects=True)
    assert b"Courses registered successfully" in response.data
    # 5. System validates availability and prevents duplicate registration.
    again = student.post("/student/courses", data={"course_ids": offered[:1]}, follow_redirects=True)
    assert b"already registered" in again.data
    # 6. Registered courses appear on the student's dashboard.
    dashboard = student.get("/student/").get_data(as_text=True)
    assert all(code in dashboard for code in ["CSC 201", "CSC 203", "CSC 205", "MTH 201"])
    assert ">11<" in dashboard.replace(" ", "")  # 3 + 3 + 2 + 3 units
    # 7. Department administrators can view the registrations.
    admin = client_as("csc.admin@uemp.edu.ng")
    assert "CSC/2025/001" in admin.get("/admin/registrations?q=CSC/2025/001").get_data(as_text=True)


def test_workflow_2_lecturer_result_submission(client_as):
    # 1. Lecturer logs in.
    lecturer = client_as("lecturer@uemp.edu.ng")
    # 2. Lecturer views assigned courses.
    dashboard = lecturer.get("/lecturer/").get_data(as_text=True)
    allocation_id = re.search(r"/lecturer/courses/(\d+)", dashboard).group(1)
    assert "CSC 201" in dashboard
    # 3. Lecturer selects a course.  4. System displays the registered students.
    page = lecturer.get(f"/lecturer/courses/{allocation_id}?tab=scores").get_data(as_text=True)
    assert page.count('name="ca_') == 11
    # 5. Lecturer enters CA and examination scores.
    sheet = sheet_for("CSC 201")
    data = fill_scores(sheet, "32", "40", action="save")
    # 6. System calculates total scores and corresponding grades.
    lecturer.post(f"/lecturer/courses/{allocation_id}/scores", data=data)
    sheet = sheet_for("CSC 201")
    assert all((e.total, e.grade, e.grade_point) == (72, "A", 5.0) for e in sheet.entries)
    # 7. Lecturer saves results as drafts or submits them for approval.
    assert sheet.status == "draft"
    lecturer.post(f"/lecturer/courses/{allocation_id}/scores", data={**data, "action": "submit"})
    assert sheet_for("CSC 201").status == "submitted"
    # 8. Department administrator reviews the submitted results.
    admin = client_as("csc.admin@uemp.edu.ng")
    review = admin.get(f"/admin/results/{sheet.id}").get_data(as_text=True)
    assert "CSC/2025/002" in review and ">72<" in review.replace(" ", "")
    # 9. Department administrator approves or rejects the submission.
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    # 10. Approved results become visible to students.
    student = client_as("csc25002@uemp.edu.ng")
    results = student.get("/student/results").get_data(as_text=True)
    assert "CSC 201" in results and "Data Structures and Algorithms" in results


def test_workflow_3_departmental_result_approval_with_rejection(client_as):
    # 1. Department administrator logs in.
    admin = client_as("csc.admin@uemp.edu.ng")
    # 2. Administrator views pending result submissions.
    pending = admin.get("/admin/results").get_data(as_text=True)
    assert "CSC 203" in pending and "Prof. Tunde Bakare" in pending
    # 3. Administrator selects a course.  4. Reviews submitted results.
    sheet = sheet_for("CSC 203")
    assert "Pass rate" in admin.get(f"/admin/results/{sheet.id}").get_data(as_text=True)
    # 5. Administrator approves or rejects the results (reject first).
    admin.post(f"/admin/results/{sheet.id}/decision",
               data={"decision": "reject", "comment": "CSC/2025/004 exam score looks wrong"})
    # 6. If rejected, the lecturer receives feedback and can make corrections.
    lecturer = client_as("bakare@uemp.edu.ng")
    assert "CSC/2025/004 exam score looks wrong" in lecturer.get("/lecturer/").get_data(as_text=True)
    sheet = sheet_for("CSC 203")
    entry = next(e for e in sheet.entries if e.registration.student.student_profile.matric_number == "CSC/2025/004")
    data = {"action": "submit"}
    for e in sheet.entries:
        data[f"ca_{e.id}"] = e.ca_score
        data[f"exam_{e.id}"] = 50 if e.id == entry.id else e.exam_score
    allocation_id = re.search(r"/lecturer/courses/(\d+)", lecturer.get("/lecturer/").get_data(as_text=True)).group(1)
    lecturer.post(f"/lecturer/courses/{allocation_id}/scores", data=data)
    assert sheet_for("CSC 203").status == "submitted"
    # The correction is traceable.
    change = db.session.scalar(db.select(AuditLog).filter_by(action="result.modified"))
    assert "CSC/2025/004" in change.description and "→50" in change.description
    # 5 (again). Administrator approves.  7. Approved results become available to students.
    admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    student = client_as("csc25004@uemp.edu.ng")
    assert "CSC 203" in student.get("/student/results").get_data(as_text=True)


def test_workflow_4_super_admin_management(client_as):
    # 1. Super Admin logs in.  2. Accesses the university-wide dashboard.
    sa = client_as("admin@uemp.edu.ng")
    assert "University overview" in sa.get("/super/").get_data(as_text=True)
    # 3. Creates faculties and departments.
    sa.post("/super/faculties/new", data={"name": "Faculty of Arts", "code": "ART"})
    art = db.session.scalar(db.select(Faculty).filter_by(code="ART"))
    sa.post("/super/faculties/departments/new", data={"name": "History", "code": "HIS", "faculty_id": art.id})
    his = db.session.scalar(db.select(Department).filter_by(code="HIS"))
    # 4. Creates academic sessions and semesters.
    sa.post("/super/sessions", data={"name": "2027/2028"})
    assert len(db.session.scalar(db.select(AcademicSession).filter_by(name="2027/2028")).semesters) == 2
    # 5. Manages student and lecturer accounts.  6. Assigns users to departments.
    sa.post("/admin/programs/new", data={"name": "History", "code": "BA-HIS", "degree": "B.A.",
                                         "duration_years": 4, "department_id": his.id})
    from uemp.models import Program
    ba = db.session.scalar(db.select(Program).filter_by(code="BA-HIS"))
    sa.post("/admin/lecturers/new", data={"first_name": "Bola", "last_name": "Ige", "email": "bola@uemp.edu.ng",
                                          "password": "Strong1234", "staff_id": "STF/HIS/001", "department_id": his.id})
    sa.post("/admin/students/new", data={"first_name": "Uche", "last_name": "Eze", "email": "uche@uemp.edu.ng",
                                         "password": "Strong1234", "matric_number": "HIS/2026/001",
                                         "program_id": ba.id, "level": 100, "entry_year": 2026})
    sa.post("/super/users/new-admin", data={"role": "dept_admin", "first_name": "Head", "last_name": "History",
                                            "email": "his.admin@uemp.edu.ng", "department_id": his.id,
                                            "password": "Strong1234"})
    for email in ["bola@uemp.edu.ng", "uche@uemp.edu.ng", "his.admin@uemp.edu.ng"]:
        assert user(email).department_id == his.id
    # The new department admin manages ONLY History.
    c = sa.application.test_client()
    login(c, "his.admin@uemp.edu.ng", "Strong1234")
    page = c.get("/admin/students").get_data(as_text=True)
    assert "HIS/2026/001" in page and "CSC/2025/001" not in page
    # 7. Monitors academic activities across the university.
    audit = sa.get("/super/audit").get_data(as_text=True)
    assert "Faculty ART" in audit and "Created session 2027/2028" in audit and "his.admin@uemp.edu.ng" in audit
