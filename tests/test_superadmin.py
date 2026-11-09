"""Workflow 4 — Super Admin management, plus department admin account rules."""

from uemp.extensions import db
from uemp.models import AcademicSession, Department, Faculty, Semester, User

from .conftest import login, user


def test_create_faculty_and_department(as_super):
    as_super.post("/super/faculties/new", data={"name": "Faculty of Arts", "code": "ART"})
    faculty = db.session.scalar(db.select(Faculty).filter_by(code="ART"))
    assert faculty
    as_super.post("/super/faculties/departments/new", data={"name": "History", "code": "HIS", "faculty_id": faculty.id})
    assert db.session.scalar(db.select(Department).filter_by(code="HIS")).faculty_id == faculty.id


def test_duplicate_faculty_code_is_rejected(as_super):
    response = as_super.post("/super/faculties/new", data={"name": "Another Science", "code": "SCI"},
                             follow_redirects=True)
    assert b"already exists" in response.data


def test_create_session_creates_two_semesters_and_set_current(as_super):
    as_super.post("/super/sessions", data={"name": "2027/2028"})
    session = db.session.scalar(db.select(AcademicSession).filter_by(name="2027/2028"))
    assert [s.term for s in session.semesters] == ["first", "second"]

    first = session.semesters[0]
    as_super.post(f"/super/sessions/semester/{first.id}", data={"action": "make_current"})
    as_super.post(f"/super/sessions/semester/{first.id}", data={"action": "open"})
    db.session.expire_all()
    assert Semester.current().id == first.id
    assert db.session.get(Semester, first.id).registration_open
    assert db.session.scalar(db.select(db.func.count(Semester.id)).filter_by(is_current=True)) == 1


def test_bad_session_name_is_rejected(as_super):
    response = as_super.post("/super/sessions", data={"name": "2027-2029"}, follow_redirects=True)
    assert b"two consecutive years" in response.data


def test_create_department_admin_and_change_role(as_super):
    csc = db.session.scalar(db.select(Department).filter_by(code="CSC"))
    as_super.post("/super/users/new-admin", data={
        "role": "dept_admin", "first_name": "New", "last_name": "Admin", "email": "new.admin@uemp.edu.ng",
        "department_id": csc.id, "password": "Strong1234"})
    created = user("new.admin@uemp.edu.ng")
    assert created.role == "dept_admin" and created.department_id == csc.id

    lecturer = user("musa@uemp.edu.ng")
    as_super.post(f"/super/users/{lecturer.id}/role", data={"role": "dept_admin", "department_id": 0})
    assert user("musa@uemp.edu.ng").role == "dept_admin"


def test_super_admin_can_suspend_account(as_super):
    target = user("csc25003@uemp.edu.ng")
    as_super.post(f"/admin/users/{target.id}/status", data={"status": "suspended"})
    assert user("csc25003@uemp.edu.ng").status == "suspended"


def test_department_admin_registers_student_in_own_department(as_csc_admin):
    from uemp.models import Program
    program = db.session.scalar(db.select(Program).filter_by(code="BSC-CSC"))
    as_csc_admin.post("/admin/students/new", data={
        "first_name": "Ada", "last_name": "Lovelace", "email": "ada@uemp.edu.ng", "password": "Strong1234",
        "matric_number": "CSC/2026/099", "program_id": program.id, "level": 100, "entry_year": 2026})
    created = user("ada@uemp.edu.ng")
    assert created and created.student_profile.matric_number == "CSC/2026/099"


def test_department_admin_cannot_register_student_into_other_department(as_csc_admin):
    from uemp.models import Program
    eco_program = db.session.scalar(db.select(Program).filter_by(code="BSC-ECO"))
    as_csc_admin.post("/admin/students/new", data={
        "first_name": "X", "last_name": "Y", "email": "xy@uemp.edu.ng", "password": "Strong1234",
        "matric_number": "ECO/2026/099", "program_id": eco_program.id, "level": 100, "entry_year": 2026})
    assert user("xy@uemp.edu.ng") is None


def test_duplicate_matric_number_is_rejected(as_csc_admin):
    from uemp.models import Program
    program = db.session.scalar(db.select(Program).filter_by(code="BSC-CSC"))
    response = as_csc_admin.post("/admin/students/new", data={
        "first_name": "Dup", "last_name": "Licate", "email": "dup@uemp.edu.ng", "password": "Strong1234",
        "matric_number": "CSC/2025/001", "program_id": program.id, "level": 100, "entry_year": 2026},
        follow_redirects=True)
    assert b"already in use" in response.data


def test_department_admin_cannot_suspend_super_admin(client):
    login(client, "csc.admin@uemp.edu.ng", "Admin@1234")
    target = user("admin@uemp.edu.ng")
    client.post(f"/admin/users/{target.id}/status", data={"status": "suspended"})
    assert user("admin@uemp.edu.ng").status == "active"


def test_allocate_lecturer_to_course(as_csc_admin):
    from uemp.models import Course, CourseAllocation
    csc_lecturer = user("musa@uemp.edu.ng")
    course = db.session.scalar(db.select(Course).filter_by(code="CSC 205"))
    as_csc_admin.post("/admin/allocations", data={"course_id": course.id, "lecturer_id": csc_lecturer.id})
    allocation = db.session.scalar(db.select(CourseAllocation).filter_by(course_id=course.id,
                                                                         semester_id=Semester.current().id))
    assert allocation.lecturer_id == csc_lecturer.id


def test_users_page_lists_everyone(as_super):
    page = as_super.get("/super/users?role=dept_admin").get_data(as_text=True)
    assert "csc.admin@uemp.edu.ng" in page and "eco.admin@uemp.edu.ng" in page
    assert db.session.scalar(db.select(db.func.count(User.id))) > 20
