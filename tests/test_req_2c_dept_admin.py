"""Brief §2C — DEPARTMENT ADMIN: abilities and restrictions (own department only)."""

import csv
import io

from uemp.extensions import db
from uemp.models import Course, CourseAllocation, Department, Program, Semester

from .conftest import course, login, sheet_for, user


def dept(code) -> Department:
    db.session.expire_all()
    return db.session.scalar(db.select(Department).filter_by(code=code))


def program(code) -> Program:
    db.session.expire_all()
    return db.session.scalar(db.select(Program).filter_by(code=code))


def new_student(**overrides):
    data = {"first_name": "Ada", "last_name": "Obi", "email": "ada.obi@uemp.edu.ng", "password": "Strong1234",
            "matric_number": "CSC/2026/050", "program_id": program("BSC-CSC").id, "level": 100, "entry_year": 2026}
    data.update(overrides)
    return data


def new_course(**overrides):
    data = {"code": "CSC 207", "title": "Web Technologies", "units": 2, "level": 200, "semester_term": "first",
            "department_id": dept("CSC").id, "program_ids": [program("BSC-CSC").id], "is_active": "y"}
    data.update(overrides)
    return data


# --------------------------------------------------------------------------- #
#  Department administrators should be able to …
# --------------------------------------------------------------------------- #
def test_access_departmental_dashboard(as_csc_admin):
    page = as_csc_admin.get("/admin/").get_data(as_text=True)
    assert "Computer Science Department" in page
    assert "Results awaiting review" in page and "CSC 203" in page


def test_register_student_within_department(as_csc_admin):
    response = as_csc_admin.post("/admin/students/new", data=new_student(), follow_redirects=True)
    assert b"Student created" in response.data
    created = user("ada.obi@uemp.edu.ng")
    assert created.role == "student" and created.department_id == dept("CSC").id
    # The new student can log in immediately with the initial password.
    fresh = as_csc_admin.application.test_client()
    assert login(fresh, "ada.obi@uemp.edu.ng", "Strong1234").status_code == 302


def test_manage_student_record_edit_level_and_details(as_csc_admin):
    student = user("csc26001@uemp.edu.ng")
    data = new_student(email=student.email, matric_number=student.student_profile.matric_number,
                       first_name="Renamed", level=200, entry_year=2026)
    data.pop("password")
    as_csc_admin.post(f"/admin/students/{student.id}/edit", data=data)
    student = user("csc26001@uemp.edu.ng")
    assert student.first_name == "Renamed" and student.student_profile.level == 200


def test_student_level_must_fit_programme_duration(as_csc_admin):
    response = as_csc_admin.post("/admin/students/new", data=new_student(level=500), follow_redirects=True)
    assert b"runs from 100 to 400 Level" in response.data


def test_weak_password_and_duplicate_email_rejected(as_csc_admin):
    assert b"letters and numbers" in as_csc_admin.post("/admin/students/new",
                                                       data=new_student(password="abcdefgh")).data
    dup = as_csc_admin.post("/admin/students/new", data=new_student(email="student@uemp.edu.ng"),
                            follow_redirects=True)
    assert b"already in use" in dup.data


def test_deactivate_reactivate_and_reset_password_of_own_student(as_csc_admin, app):
    student = user("csc26002@uemp.edu.ng")
    as_csc_admin.post(f"/admin/users/{student.id}/status", data={"status": "inactive"})
    assert user("csc26002@uemp.edu.ng").status == "inactive"
    as_csc_admin.post(f"/admin/users/{student.id}/status", data={"status": "active"})
    as_csc_admin.post(f"/admin/users/{student.id}/password", data={"new_password": "NewPass2026"})
    assert login(app.test_client(), "csc26002@uemp.edu.ng", "NewPass2026").status_code == 302


def test_create_and_manage_lecturer_profiles(as_csc_admin):
    as_csc_admin.post("/admin/lecturers/new", data={
        "first_name": "Kemi", "last_name": "Ade", "email": "kemi.ade@uemp.edu.ng", "password": "Strong1234",
        "title": "Dr.", "staff_id": "STF/CSC/010", "department_id": dept("CSC").id, "rank": "Lecturer I"})
    lecturer = user("kemi.ade@uemp.edu.ng")
    assert lecturer.role == "lecturer" and lecturer.lecturer_profile.staff_id == "STF/CSC/010"

    as_csc_admin.post(f"/admin/lecturers/{lecturer.id}/edit", data={
        "first_name": "Kemi", "last_name": "Ade", "email": "kemi.ade@uemp.edu.ng", "title": "Dr.",
        "staff_id": "STF/CSC/010", "department_id": dept("CSC").id, "rank": "Senior Lecturer"})
    assert user("kemi.ade@uemp.edu.ng").lecturer_profile.rank == "Senior Lecturer"


def test_duplicate_staff_id_rejected(as_csc_admin):
    response = as_csc_admin.post("/admin/lecturers/new", data={
        "first_name": "X", "last_name": "Y", "email": "xy@uemp.edu.ng", "password": "Strong1234",
        "staff_id": "stf/csc/001", "department_id": dept("CSC").id}, follow_redirects=True)
    assert b"Staff ID STF/CSC/001 is already in use" in response.data


def test_create_and_manage_departmental_courses(as_csc_admin):
    response = as_csc_admin.post("/admin/courses/new", data=new_course(), follow_redirects=True)
    assert b"Course saved" in response.data
    created = course("CSC 207")
    assert created.units == 2 and created.level == 200 and created.semester_term == "first"

    as_csc_admin.post(f"/admin/courses/{created.id}/edit", data=new_course(title="Web Engineering", units=3))
    assert course("CSC 207").title == "Web Engineering" and course("CSC 207").units == 3


def test_course_code_duplicates_are_caught_even_with_odd_spacing(as_csc_admin):
    response = as_csc_admin.post("/admin/courses/new", data=new_course(code="csc  201"), follow_redirects=True)
    assert b"Course code CSC 201 is already in use" in response.data


def test_course_units_validated(as_csc_admin):
    response = as_csc_admin.post("/admin/courses/new", data=new_course(units=9))
    assert b"Number must be between 1 and 6" in response.data


def test_deactivated_course_is_no_longer_registrable(as_csc_admin, client_as):
    target = course("CSC 205")
    data = new_course(code="CSC 205", title=target.title, units=target.units)
    data.pop("is_active")  # unticked checkbox = inactive
    as_csc_admin.post(f"/admin/courses/{target.id}/edit", data=data)
    assert "CSC 205" not in client_as("student@uemp.edu.ng").get("/student/courses").get_data(as_text=True)


def test_assign_lecturer_to_course_and_remove_allocation(as_csc_admin):
    as_csc_admin.post("/admin/courses/new", data=new_course())
    musa = user("musa@uemp.edu.ng")
    as_csc_admin.post("/admin/allocations", data={"course_id": course("CSC 207").id, "lecturer_id": musa.id})
    allocation = db.session.scalar(db.select(CourseAllocation).filter_by(course_id=course("CSC 207").id))
    assert allocation.lecturer_id == musa.id
    allocation_id = allocation.id
    as_csc_admin.post(f"/admin/allocations/{allocation_id}/delete")
    db.session.expire_all()
    assert db.session.get(CourseAllocation, allocation_id) is None


def test_allocation_of_wrong_semester_course_is_refused(as_csc_admin):
    response = as_csc_admin.post("/admin/allocations", data={
        "course_id": course("CSC 202").id, "lecturer_id": user("musa@uemp.edu.ng").id}, follow_redirects=True)
    # CSC 202 is a second-semester course: not even offered in the drop-down.
    assert b"Not a valid choice" in response.data


def test_cannot_remove_allocation_once_scores_exist(as_csc_admin):
    allocation = db.session.scalar(db.select(CourseAllocation).filter_by(
        course_id=course("CSC 203").id, semester_id=Semester.current().id))
    response = as_csc_admin.post(f"/admin/allocations/{allocation.id}/delete", follow_redirects=True)
    assert b"Scores have already been entered" in response.data


def test_manage_academic_levels_and_programmes(as_csc_admin):
    as_csc_admin.post("/admin/programs/new", data={"name": "Cyber Security", "code": "BSC-CYB", "degree": "B.Sc.",
                                                   "duration_years": 4, "department_id": dept("CSC").id})
    cyb = program("BSC-CYB")
    assert cyb.department_id == dept("CSC").id and cyb.max_level == 400
    as_csc_admin.post(f"/admin/programs/{cyb.id}/edit", data={"name": "Cyber Security", "code": "BSC-CYB",
                                                              "degree": "B.Sc.", "duration_years": 5,
                                                              "department_id": dept("CSC").id})
    assert program("BSC-CYB").max_level == 500
    assert "Cyber Security" in as_csc_admin.get("/admin/programs").get_data(as_text=True)


def test_view_student_course_registrations_and_export(as_csc_admin):
    page = as_csc_admin.get(f"/admin/registrations?course_id={course('CSC 201').id}").get_data(as_text=True)
    assert "CSC/2025/002" in page
    rows = list(csv.reader(io.StringIO(as_csc_admin.get("/admin/registrations.csv").get_data(as_text=True))))
    assert rows[0][0] == "Matric No" and len(rows) == 1 + 11 * 3   # 11 students × CSC 201/203 + MTH 201


def test_review_approve_reject_and_return_results(as_csc_admin):
    sheet = sheet_for("CSC 203")
    page = as_csc_admin.get(f"/admin/results/{sheet.id}").get_data(as_text=True)
    assert "Approve & publish" in page and "Return for correction" in page and "CSC/2025/002" in page
    as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "reject", "comment": "Fix row 3"})
    assert sheet_for("CSC 203").status == "returned"


def test_generate_departmental_reports(as_csc_admin):
    sheet = sheet_for("CSC 203")
    as_csc_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"})

    students = as_csc_admin.get("/admin/reports?tab=students").get_data(as_text=True)
    assert "CSC/2025/001" in students and "ECO/2026/001" not in students

    registrations = as_csc_admin.get("/admin/reports?tab=registrations").get_data(as_text=True)
    assert "CSC 201" in registrations and "Dr. Adaeze Okafor" in registrations

    sheet = sheet_for("CSC 203")
    totals = [e.total for e in sheet.entries]
    performance = as_csc_admin.get("/admin/reports?tab=performance").get_data(as_text=True)
    assert f"{round(sum(totals) / len(totals), 1)}" in performance

    perf_csv = list(csv.reader(io.StringIO(as_csc_admin.get("/admin/reports/performance.csv").get_data(as_text=True))))
    assert perf_csv[1][0] == "CSC 203"


# --------------------------------------------------------------------------- #
#  Restrictions
# --------------------------------------------------------------------------- #
def test_records_outside_own_department_are_blocked(as_eco_admin):
    csc_lecturer = user("lecturer@uemp.edu.ng")
    assert as_eco_admin.get(f"/admin/lecturers/{csc_lecturer.id}/edit").status_code == 403
    assert as_eco_admin.get(f"/admin/programs/{program('BSC-CSC').id}/edit").status_code == 403
    page = as_eco_admin.get("/admin/registrations").get_data(as_text=True)
    assert "CSC/2025/002" not in page


def test_cannot_create_records_in_another_department_by_tampering(as_eco_admin):
    # Department / programme drop-downs only offer Economics, so a tampered ID is refused.
    assert b"Not a valid choice" in as_eco_admin.post("/admin/courses/new", data=new_course(code="CSC 299")).data
    assert b"Not a valid choice" in as_eco_admin.post("/admin/students/new", data=new_student()).data
    assert course("CSC 299") is None and user("ada.obi@uemp.edu.ng") is None


def test_cannot_allocate_other_departments_lecturer_or_course(as_eco_admin):
    response = as_eco_admin.post("/admin/allocations", data={
        "course_id": course("CSC 201").id, "lecturer_id": user("lecturer@uemp.edu.ng").id})
    assert b"Not a valid choice" in response.data


def test_cannot_change_status_of_other_departments_users(as_eco_admin):
    target = user("csc25002@uemp.edu.ng")
    response = as_eco_admin.post(f"/admin/users/{target.id}/status", data={"status": "suspended"},
                                 follow_redirects=True)
    assert response.status_code in (200, 403)
    assert user("csc25002@uemp.edu.ng").status == "active"


def test_cannot_access_super_admin_functions(as_csc_admin):
    lecturer = user("lecturer@uemp.edu.ng")
    for url in ["/super/", "/super/users", "/super/roles", "/super/audit", "/super/faculties", "/super/sessions"]:
        assert as_csc_admin.get(url).status_code == 403
    assert as_csc_admin.post("/super/sessions", data={"name": "2030/2031"}).status_code == 403
    assert as_csc_admin.post(f"/super/users/{lecturer.id}/role", data={"role": "super_admin"}).status_code == 403
    assert user("lecturer@uemp.edu.ng").role == "lecturer"


def test_cannot_alter_system_wide_settings(as_csc_admin):
    semester = Semester.current()
    assert as_csc_admin.post(f"/super/sessions/semester/{semester.id}", data={"action": "close"}).status_code == 403
    db.session.expire_all()
    assert Semester.current().registration_open is True


def test_cannot_reset_super_admin_password(as_csc_admin, app):
    target = user("admin@uemp.edu.ng")
    as_csc_admin.post(f"/admin/users/{target.id}/password", data={"new_password": "Hijack2026"})
    assert login(app.test_client(), "admin@uemp.edu.ng", "Hijack2026").status_code == 200  # still old password


def test_course_list_is_scoped(as_eco_admin):
    page = as_eco_admin.get("/admin/courses").get_data(as_text=True)
    assert "ECO 101" in page and "CSC 201" not in page
    assert db.session.scalar(db.select(db.func.count(Course.id))) > 2
