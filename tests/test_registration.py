"""Workflow 1 — Student course registration and its business rules."""

from uemp.extensions import db
from uemp.models import AuditLog, CourseRegistration

from .conftest import course, current_semester, user


def _my_registrations():
    student = user("student@uemp.edu.ng")
    return {r.course.code for r in db.session.scalars(
        db.select(CourseRegistration).filter_by(student_id=student.id, semester_id=current_semester().id))}


def test_student_sees_only_courses_for_their_programme_level_and_semester(as_student):
    page = as_student.get("/student/courses").get_data(as_text=True)
    assert "CSC 201" in page and "MTH 201" in page          # 200L first semester, offered to CSC
    assert "CSC 202" not in page                             # second semester
    assert "CSC 101" not in page                             # wrong level
    assert "ECO 201" not in page                             # other programme


def test_student_can_register_courses(as_student):
    ids = [course("CSC 201").id, course("CSC 203").id]
    response = as_student.post("/student/courses", data={"course_ids": ids}, follow_redirects=True)
    assert b"Courses registered successfully" in response.data
    assert _my_registrations() == {"CSC 201", "CSC 203"}
    # Audit trail records the registration.
    assert db.session.scalar(db.select(AuditLog).filter_by(action="registration.created"))


def test_duplicate_registration_is_prevented(as_student):
    as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id]})
    response = as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id]}, follow_redirects=True)
    assert b"already registered" in response.data
    assert len(_my_registrations()) == 1


def test_ineligible_course_is_rejected_even_if_form_is_tampered(as_student):
    response = as_student.post("/student/courses", data={"course_ids": [course("ECO 201").id]}, follow_redirects=True)
    assert b"not available to you" in response.data
    assert _my_registrations() == set()


def test_unit_limit_is_enforced(as_student, app):
    app.config["MAX_UNITS_PER_SEMESTER"] = 5
    ids = [course("CSC 201").id, course("CSC 203").id]  # 6 units
    response = as_student.post("/student/courses", data={"course_ids": ids}, follow_redirects=True)
    assert b"maximum is 5 units" in response.data
    assert _my_registrations() == set()


def test_registration_closed_blocks_registration(as_student):
    current_semester().registration_open = False
    db.session.commit()
    response = as_student.post("/student/courses", data={"course_ids": [course("CSC 201").id]}, follow_redirects=True)
    assert b"closed" in response.data
    assert _my_registrations() == set()


def test_student_can_drop_own_course_but_not_others(as_student):
    as_student.post("/student/courses", data={"course_ids": [course("CSC 205").id]})
    mine = db.session.scalar(db.select(CourseRegistration).filter_by(student_id=user("student@uemp.edu.ng").id,
                                                                    semester_id=current_semester().id))
    other = db.session.scalar(db.select(CourseRegistration).filter_by(student_id=user("csc25002@uemp.edu.ng").id,
                                                                     semester_id=current_semester().id))
    response = as_student.post(f"/student/courses/{other.id}/drop", follow_redirects=True)
    assert b"Registration not found" in response.data
    as_student.post(f"/student/courses/{mine.id}/drop")
    assert _my_registrations() == set()


def test_department_admin_sees_registrations(as_csc_admin):
    page = as_csc_admin.get("/admin/registrations").get_data(as_text=True)
    assert "CSC/2025/002" in page and "CSC 201" in page
