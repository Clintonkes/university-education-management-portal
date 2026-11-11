"""Brief §5 — Technical Requirements (security, data integrity, audit, errors, UI basics)."""

import time

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from uemp import create_app
from uemp.extensions import db
from uemp.models import (
    AuditLog,
    CourseAllocation,
    CourseRegistration,
    ResultEntry,
    StudentProfile,
    User,
)
from uemp.security.permissions import ROLE_PERMISSIONS, Perm

from .conftest import allocation_for, course, current_semester, fill_scores, login, sheet_for, user


# ---- Role-based access control -------------------------------------------------
def test_rbac_table_gives_each_role_only_its_permissions():
    assert ROLE_PERMISSIONS["student"] == {Perm.STUDENT_PORTAL}
    assert ROLE_PERMISSIONS["lecturer"] == {Perm.LECTURER_PORTAL, Perm.RESULTS_ENTER}
    assert Perm.RESULTS_REVIEW in ROLE_PERMISSIONS["dept_admin"]
    assert Perm.AUDIT_VIEW not in ROLE_PERMISSIONS["dept_admin"]
    assert ROLE_PERMISSIONS["dept_admin"] < ROLE_PERMISSIONS["super_admin"]


# ---- Secure authentication and session management ------------------------------
def test_passwords_are_hashed_with_scrypt_outside_tests(app):
    dev = create_app("development", {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with dev.app_context():
        u = User(email="x@y.z", first_name="X", last_name="Y", role="student")
        u.set_password("Secret1234")
        assert u.password_hash.startswith("scrypt:") and "Secret1234" not in u.password_hash
        assert u.check_password("Secret1234") and not u.check_password("secret1234")


def test_no_plain_text_password_stored_or_logged(as_super):
    as_super.post("/super/users/new-admin", data={"role": "super_admin", "first_name": "A", "last_name": "B",
                                                  "email": "ab@uemp.edu.ng", "password": "VerySecret99"})
    assert "VerySecret99" not in user("ab@uemp.edu.ng").password_hash
    descriptions = " ".join(db.session.scalars(db.select(AuditLog.description)))
    assert "VerySecret99" not in descriptions


def test_production_cookie_and_session_settings():
    from config import ProductionConfig
    assert ProductionConfig.SESSION_COOKIE_SECURE and ProductionConfig.SESSION_COOKIE_HTTPONLY
    assert ProductionConfig.SESSION_COOKIE_SAMESITE == "Lax"
    assert ProductionConfig.PERMANENT_SESSION_LIFETIME.total_seconds() == 30 * 60


def test_non_testing_app_initializes_schema_without_demo_users(tmp_path):
    database_path = tmp_path / "startup.db"
    app = create_app("development", {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        "AUTO_SEED": False,
    })

    with app.app_context():
        assert set(db.metadata.tables) <= set(inspect(db.engine).get_table_names())
        assert db.session.scalar(db.select(User).limit(1)) is None


def test_idle_session_expires(app, client):
    app.config["PERMANENT_SESSION_LIFETIME"] = 1  # one second, for the test
    login(client, "student@uemp.edu.ng", "Student@1234")
    assert client.get("/student/").status_code == 200
    time.sleep(2.1)
    response = client.get("/student/")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_csrf_token_required_on_forms():
    app = create_app("testing", {"WTF_CSRF_ENABLED": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        response = app.test_client().post("/login", data={"email": "a@b.c", "password": "x"})
        assert response.status_code == 400 and b"form was incomplete or has expired" in response.data


def test_production_refuses_default_secret_key(monkeypatch):
    from config import ProductionConfig
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "dev-only-change-me")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        create_app("production", {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})


# ---- Database relationships ----------------------------------------------------
def test_relationships_link_students_lecturers_courses_departments_and_results(app):
    sheet = sheet_for("CSC 203")
    entry = sheet.entries[0]
    reg = entry.registration
    assert reg.course is sheet.course and reg.semester is sheet.semester
    assert reg.student.student_profile.program.department.faculty.code == "SCI"
    assert sheet.lecturer.lecturer_profile.staff_id == "STF/CSC/002"
    assert sheet.course.department.code == "CSC"
    assert {p.code for p in course("MTH 201").programs} == {"BSC-CSC", "BSC-MTH"}
    assert reg.result is entry


# ---- Data validation and duplicate prevention (database level) ----------------
@pytest.mark.parametrize("make_duplicate", [
    lambda: CourseRegistration(student_id=user("csc25002@uemp.edu.ng").id, course_id=course("CSC 201").id,
                               semester_id=current_semester().id),
    lambda: CourseAllocation(course_id=course("CSC 201").id, semester_id=current_semester().id,
                             lecturer_id=user("musa@uemp.edu.ng").id),
    lambda: ResultEntry(sheet_id=sheet_for("CSC 203").id, registration_id=sheet_for("CSC 203").entries[0].registration_id),
    lambda: User(email="student@uemp.edu.ng", first_name="D", last_name="U", role="student", password_hash="x"),
    lambda: StudentProfile(user_id=user("admin@uemp.edu.ng").id, matric_number="CSC/2025/001",
                           program_id=1, level=100, entry_year=2026),
], ids=["registration", "allocation", "result-entry", "email", "matric-number"])
def test_database_rejects_duplicates_even_if_code_checks_were_bypassed(app, make_duplicate):
    db.session.add(make_duplicate())
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ---- Audit trails ----------------------------------------------------------------
def test_audit_trail_records_who_what_when_and_where(client_as):
    lecturer = client_as("lecturer@uemp.edu.ng")
    allocation = allocation_for("CSC 201")
    lecturer.get(f"/lecturer/courses/{allocation.id}")
    sheet = sheet_for("CSC 201")
    lecturer.post(f"/lecturer/courses/{allocation.id}/scores", data=fill_scores(sheet, action="submit"),
                  environ_base={"REMOTE_ADDR": "10.1.2.3"})
    entry = db.session.scalar(db.select(AuditLog).filter_by(action="result.submitted", entity_id=sheet.id))
    assert entry.actor.email == "lecturer@uemp.edu.ng"
    assert entry.entity_type == "ResultSheet" and entry.created_at is not None
    assert entry.ip_address == "10.1.2.3"


# ---- Error handling and user feedback --------------------------------------------
def test_missing_record_shows_friendly_404(as_csc_admin):
    response = as_csc_admin.get("/admin/students/999999")
    assert response.status_code == 404 and b"Page not found" in response.data and b"Go to my dashboard" in response.data


def test_unknown_page_shows_friendly_404(as_student):
    assert b"Page not found" in as_student.get("/does-not-exist").data


def test_forbidden_shows_friendly_403(as_student):
    response = as_student.get("/super/")
    assert response.status_code == 403 and b"Access denied" in response.data


def test_unexpected_error_shows_friendly_500_without_details():
    app = create_app("testing", {"SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:", "PROPAGATE_EXCEPTIONS": False})

    @app.route("/boom")
    def boom():
        raise RuntimeError("secret internal detail")

    response = app.test_client().get("/boom")
    assert response.status_code == 500 and b"Something went wrong" in response.data
    assert b"secret internal detail" not in response.data


def test_user_input_is_html_escaped(as_student):
    as_student.post("/student/profile", data={"address": "<script>alert('x')</script>"})
    page = as_student.get("/student/profile").get_data(as_text=True)
    assert "<script>alert('x')</script>" not in page and "&lt;script&gt;" in page


# ---- Responsive UI basics (full browser check is in tests/e2e) -----------------
@pytest.mark.parametrize("url", ["/student/", "/student/courses", "/student/results"])
def test_pages_have_mobile_viewport_and_security_headers(as_student, url):
    response = as_student.get(url)
    assert b'name="viewport" content="width=device-width, initial-scale=1"' in response.data
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Cache-Control"] == "no-store"


def test_static_files_are_versioned_and_cached_in_production():
    from uemp import create_app
    app = create_app("production", {"SECRET_KEY": "x" * 40, "SQLALCHEMY_DATABASE_URI": "sqlite://", "AUTO_SEED": False})
    with app.test_request_context():
        from flask import url_for
        url = url_for("static", filename="js/app.js")
    assert "?v=" in url
    response = app.test_client().get(url)
    assert response.status_code == 200 and "max-age=31536000" in response.headers["Cache-Control"]
