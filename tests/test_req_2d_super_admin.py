"""Brief §2D — SUPER ADMIN: overall control of the platform."""

from uemp.extensions import db
from uemp.models import AuditLog, Course, CourseAllocation, Department, Program, Semester

from .conftest import course, login, sheet_for, user


def dept(code):
    return db.session.scalar(db.select(Department).filter_by(code=code))


def test_view_university_wide_dashboard(as_super):
    page = as_super.get("/super/").get_data(as_text=True)
    for text in ["University overview", "Faculties", "Departments", "Students per department", "System activity"]:
        assert text in page
    assert ">24<" in page.replace(" ", "")  # 24 active students university-wide


def test_create_and_manage_faculties_and_departments(as_super):
    as_super.post("/super/faculties/new", data={"name": "Faculty of Law", "code": "LAW"})
    from uemp.models import Faculty
    law = db.session.scalar(db.select(Faculty).filter_by(code="LAW"))
    as_super.post(f"/super/faculties/{law.id}/edit", data={"name": "Faculty of Law & Justice", "code": "LAW"})
    as_super.post("/super/faculties/departments/new", data={"name": "Public Law", "code": "PUL", "faculty_id": law.id})
    page = as_super.get("/super/faculties").get_data(as_text=True)
    assert "Faculty of Law &amp; Justice" in page and "Public Law" in page


def test_create_and_manage_programmes_in_any_department(as_super):
    as_super.post("/admin/programs/new", data={"name": "Power Systems", "code": "BENG-PWR", "degree": "B.Eng.",
                                               "duration_years": 5, "department_id": dept("EEE").id})
    created = db.session.scalar(db.select(Program).filter_by(code="BENG-PWR"))
    assert created.department_id == dept("EEE").id


def test_manage_student_and_lecturer_accounts_in_any_department(as_super):
    eco_program = db.session.scalar(db.select(Program).filter_by(code="BSC-ECO"))
    as_super.post("/admin/students/new", data={
        "first_name": "Musa", "last_name": "Bala", "email": "musa.bala@uemp.edu.ng", "password": "Strong1234",
        "matric_number": "ECO/2026/090", "program_id": eco_program.id, "level": 100, "entry_year": 2026})
    as_super.post("/admin/lecturers/new", data={
        "first_name": "Tola", "last_name": "Ojo", "email": "tola.ojo@uemp.edu.ng", "password": "Strong1234",
        "staff_id": "STF/EEE/001", "department_id": dept("EEE").id})
    assert user("musa.bala@uemp.edu.ng").department_id == dept("ECO").id
    assert user("tola.ojo@uemp.edu.ng").department_id == dept("EEE").id


def test_create_and_manage_sessions_and_semesters(as_super):
    as_super.post("/super/sessions", data={"name": "2027/2028", "start_date": "2027-10-01", "end_date": "2028-08-31"})
    page = as_super.get("/super/sessions").get_data(as_text=True)
    assert "2027/2028" in page
    current = Semester.current()
    as_super.post(f"/super/sessions/semester/{current.id}", data={"action": "close"})
    db.session.expire_all()
    assert Semester.current().registration_open is False


def test_registration_can_only_be_opened_for_current_semester(as_super):
    not_current = db.session.scalar(db.select(Semester).filter_by(is_current=False))
    response = as_super.post(f"/super/sessions/semester/{not_current.id}", data={"action": "open"},
                             follow_redirects=True)
    assert b"only be opened for the current semester" in response.data


def test_duplicate_session_rejected(as_super):
    response = as_super.post("/super/sessions", data={"name": "2026/2027"}, follow_redirects=True)
    assert b"already exists" in response.data


def test_manage_courses_and_allocations_in_any_department(as_super):
    eco_program = db.session.scalar(db.select(Program).filter_by(code="BSC-ECO"))
    as_super.post("/admin/courses/new", data={
        "code": "ECO 203", "title": "Statistics for Economists", "units": 3, "level": 200,
        "semester_term": "first", "department_id": dept("ECO").id, "program_ids": [eco_program.id], "is_active": "y"})
    as_super.post("/admin/allocations", data={"course_id": course("ECO 203").id,
                                              "lecturer_id": user("adeyemi@uemp.edu.ng").id})
    allocation = db.session.scalar(db.select(CourseAllocation).filter_by(course_id=course("ECO 203").id))
    assert allocation.lecturer_id == user("adeyemi@uemp.edu.ng").id


def test_activate_deactivate_and_suspend_accounts(as_super, app):
    target = user("csc25005@uemp.edu.ng")
    for status in ["inactive", "suspended", "active"]:
        as_super.post(f"/admin/users/{target.id}/status", data={"status": status})
        assert user("csc25005@uemp.edu.ng").status == status
    assert login(app.test_client(), "csc25005@uemp.edu.ng", "Student@1234").status_code == 302


def test_cannot_change_own_status_or_role(as_super):
    me = user("admin@uemp.edu.ng")
    as_super.post(f"/admin/users/{me.id}/status", data={"status": "suspended"})
    as_super.post(f"/super/users/{me.id}/role", data={"role": "lecturer", "department_id": dept("CSC").id})
    me = user("admin@uemp.edu.ng")
    assert me.status == "active" and me.role == "super_admin"


def test_manage_user_roles_and_permissions(as_super, client_as):
    musa = user("musa@uemp.edu.ng")
    as_super.post(f"/super/users/{musa.id}/role", data={"role": "dept_admin", "department_id": dept("CSC").id})
    assert user("musa@uemp.edu.ng").role == "dept_admin"
    promoted = client_as("musa@uemp.edu.ng")
    assert promoted.get("/admin/").status_code == 200
    assert promoted.get("/lecturer/").status_code == 403      # permissions follow the new role
    roles_page = as_super.get("/super/roles").get_data(as_text=True)
    assert "results.review" in roles_page and "audit.view" in roles_page


def test_student_role_cannot_be_changed(as_super):
    student = user("csc25002@uemp.edu.ng")
    response = as_super.post(f"/super/users/{student.id}/role", data={"role": "super_admin", "department_id": 0},
                             follow_redirects=True)
    assert b"only be changed between staff roles" in response.data
    assert user("csc25002@uemp.edu.ng").role == "student"


def test_create_department_admin_requires_department(as_super):
    response = as_super.post("/super/users/new-admin", data={
        "role": "dept_admin", "first_name": "No", "last_name": "Dept", "email": "nodept@uemp.edu.ng",
        "department_id": 0, "password": "Strong1234"}, follow_redirects=True)
    assert b"choose a valid department" in response.data
    assert user("nodept@uemp.edu.ng") is None


def test_view_and_monitor_registrations_across_departments(as_super, client_as):
    eco_student = client_as("eco26001@uemp.edu.ng")
    eco_student.post("/student/courses", data={"course_ids": [course("ECO 101").id]})
    assert "CSC/2025/002" in as_super.get("/admin/registrations").get_data(as_text=True)
    assert "ECO/2026/001" in as_super.get("/admin/registrations?q=ECO").get_data(as_text=True)


def test_oversee_departmental_result_approvals(as_super):
    sheet = sheet_for("CSC 203")
    assert "CSC 203" in as_super.get("/admin/results").get_data(as_text=True)
    as_super.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})
    assert sheet_for("CSC 203").status == "approved"


def test_access_university_wide_reports(as_super):
    page = as_super.get("/admin/reports?tab=students").get_data(as_text=True)
    assert "ECO/2026/001" in page and "CSC/2025/001" in page
    narrowed = as_super.get(f"/admin/reports?tab=students&department_id={dept('ECO').id}").get_data(as_text=True)
    assert "ECO/2026/001" in narrowed and "CSC/2025/001" not in narrowed


def test_monitor_system_activities_and_administrative_actions(as_super, client_as):
    client_as("csc.admin@uemp.edu.ng").post(f"/admin/results/{sheet_for('CSC 203').id}/decision",
                                            data={"decision": "approve"})
    page = as_super.get("/super/audit?action=result").get_data(as_text=True)
    assert "result.approved" in page and "Samuel Ogbu" in page
    assert "auth.login" not in page   # filter works
    searched = as_super.get("/super/audit?q=CSC 203").get_data(as_text=True)
    assert "CSC 203" in searched
    assert db.session.scalar(db.select(db.func.count(AuditLog.id))) > 5
    assert db.session.scalar(db.select(db.func.count(Course.id))) == 13
