"""
Brief §2A — STUDENT: every "should be able to" item and every restriction.

Each test name says which line of the brief it proves.
"""

from uemp.extensions import db
from uemp.models import AuditLog, CourseRegistration, ResultSheet
from uemp.services.grading import calculate_gpa

from .conftest import course, current_semester, fill_scores, sheet_for, user


# --------------------------------------------------------------------------- #
#  Students should be able to …
# --------------------------------------------------------------------------- #
def test_log_in_securely_to_student_dashboard(as_student):
    page = as_student.get("/student/").get_data(as_text=True)
    assert "Welcome, Chinedu" in page and "Student portal" in page


def test_view_and_update_permitted_profile_information(as_student):
    response = as_student.post("/student/profile", data={
        "phone": "+234 803 000 1111", "address": "12 Unity Road, Abuja", "gender": "Male",
        "next_of_kin": "Mrs Okeke", "next_of_kin_phone": "08030002222", "date_of_birth": "2005-03-14",
    }, follow_redirects=True)
    assert b"Your profile has been updated" in response.data
    me = user("student@uemp.edu.ng")
    assert me.phone == "+234 803 000 1111"
    assert me.student_profile.address == "12 Unity Road, Abuja"
    assert str(me.student_profile.date_of_birth) == "2005-03-14"
    assert db.session.scalar(db.select(AuditLog).filter_by(action="profile.updated"))


def test_official_profile_fields_cannot_be_changed_by_student(as_student):
    """Matric no., names, level and programme are NOT permitted fields — tampering is ignored."""
    as_student.post("/student/profile", data={
        "phone": "08011112222", "matric_number": "HACK/001", "first_name": "Hacker", "level": "500",
        "program_id": "999", "email": "hacker@evil.com", "status": "active",
    })
    me = user("student@uemp.edu.ng")
    assert me.student_profile.matric_number == "CSC/2025/001"
    assert me.first_name == "Chinedu" and me.email == "student@uemp.edu.ng"
    assert me.student_profile.level == 200


def test_invalid_profile_input_is_rejected_with_message(as_student):
    response = as_student.post("/student/profile", data={"phone": "not-a-phone!!"})
    assert b"Enter a valid phone number" in response.data


def test_view_department_faculty_program_and_matric_number(as_student):
    page = as_student.get("/student/profile").get_data(as_text=True)
    for text in ["CSC/2025/001", "Computer Science", "Faculty of Science", "B.Sc. Computer Science", "200 Level"]:
        assert text in page


def test_view_available_courses_for_program_and_level(as_student):
    page = as_student.get("/student/courses").get_data(as_text=True)
    assert all(code in page for code in ["CSC 201", "CSC 203", "CSC 205", "MTH 201"])


def test_register_courses_for_current_semester(as_student):
    as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id, course("MTH 201").id]})
    regs = db.session.scalars(db.select(CourseRegistration).filter_by(
        student_id=user("student@uemp.edu.ng").id, semester_id=current_semester().id)).all()
    assert {r.course.code for r in regs} == {"CSC 201", "MTH 201"}


def test_view_registered_courses_and_course_units(as_student):
    as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id, course("CSC 205").id]})
    dashboard = as_student.get("/student/").get_data(as_text=True)
    assert "CSC 201" in dashboard and "CSC 205" in dashboard
    assert "Total units" in dashboard and ">5<" in dashboard.replace(" ", "")  # 3 + 2 units


def test_view_academic_results_and_semester_grades(client_as):
    c = client_as("csc25002@uemp.edu.ng")
    page = c.get("/student/results").get_data(as_text=True)
    # Default = newest semester; previous semester has approved grades.
    prev = c.get("/student/results?semester_id=2").get_data(as_text=True)
    assert "Semester GPA" in prev and "CSC 102" in prev and 'class="grade grade-' in prev
    assert "Awaiting approval" in page


def test_view_academic_history_and_correct_cgpa(client_as):
    student = user("csc25002@uemp.edu.ng")
    # Work out the expected CGPA independently, straight from the database.
    rows = []
    for sheet in db.session.scalars(db.select(ResultSheet).filter_by(status="approved")):
        for e in sheet.entries:
            if e.registration.student_id == student.id:
                rows.append((sheet.course.units, e.grade_point))
    expected = f"{calculate_gpa(rows):.2f}"
    page = client_as("csc25002@uemp.edu.ng").get("/student/history").get_data(as_text=True)
    assert expected in page and "CGPA" in page


def test_download_or_print_registration_summary(as_student):
    as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id]})
    slip = as_student.get("/student/courses/slip").get_data(as_text=True)
    assert "Course Registration Form" in slip and "CSC 201" in slip and "CSC/2025/001" in slip
    assert "window.print()" in slip


def test_download_or_print_result_statement(as_student):
    statement = as_student.get("/student/statement").get_data(as_text=True)
    assert "Statement of Result" in statement and "CGPA" in statement and "CSC 101" in statement


# --------------------------------------------------------------------------- #
#  Restrictions
# --------------------------------------------------------------------------- #
def test_students_cannot_register_other_students(as_student):
    """There is no student-ID field; any sent is ignored and only the caller is registered."""
    other = user("csc26001@uemp.edu.ng")
    as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id], "student_id": other.id})
    assert not db.session.scalar(db.select(CourseRegistration).filter_by(student_id=other.id))
    assert db.session.scalar(db.select(CourseRegistration).filter_by(
        student_id=user("student@uemp.edu.ng").id, course_id=course("CSC 201").id))


def test_students_cannot_upload_or_modify_examination_results(client_as, app):
    c = client_as("csc25002@uemp.edu.ng")
    from .conftest import allocation_for
    sheet = sheet_for("CSC 201")
    assert c.post(f"/lecturer/courses/{allocation_for('CSC 201').id}/scores",
                  data=fill_scores(sheet, ca="40", exam="60")).status_code == 403
    assert c.post(f"/admin/results/{sheet_for('CSC 203').id}/decision", data={"decision": "approve"}).status_code == 403
    db.session.refresh(sheet)
    assert all(e.ca_score is None for e in sheet.entries)


def test_students_cannot_access_lecturer_or_admin_dashboards(as_student):
    for url in ["/lecturer/", "/lecturer/courses", "/admin/", "/admin/results", "/super/"]:
        assert as_student.get(url).status_code == 403


def test_students_cannot_modify_their_records_or_grades(as_student):
    me = user("student@uemp.edu.ng")
    assert as_student.post(f"/admin/students/{me.id}/edit", data={"level": 500}).status_code == 403
    assert as_student.post(f"/admin/users/{me.id}/status", data={"status": "active"}).status_code == 403
    assert user("student@uemp.edu.ng").student_profile.level == 200
