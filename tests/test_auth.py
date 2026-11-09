"""Authentication: login, role redirect, lockout, suspended accounts, logout."""

import pytest

from uemp.extensions import db

from .conftest import login, user


@pytest.mark.parametrize("email, password, home", [
    ("student@uemp.edu.ng", "Student@1234", "/student/"),
    ("lecturer@uemp.edu.ng", "Lecturer@1234", "/lecturer/"),
    ("csc.admin@uemp.edu.ng", "Admin@1234", "/admin/"),
    ("admin@uemp.edu.ng", "Admin@1234", "/super/"),
])
def test_each_role_is_redirected_to_its_dashboard(client, email, password, home):
    login(client, email, password)
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(home)
    assert client.get(home).status_code == 200


def test_wrong_password_is_rejected(client):
    response = login(client, "student@uemp.edu.ng", "wrong-password1")
    assert response.status_code == 200
    assert b"Incorrect email or password" in response.data


def test_unknown_email_gives_same_message(client):
    response = login(client, "nobody@uemp.edu.ng", "whatever123")
    assert b"Incorrect email or password" in response.data


def test_account_locks_after_too_many_failures(client, app):
    for _ in range(app.config["MAX_FAILED_LOGINS"]):
        login(client, "student@uemp.edu.ng", "wrong-password1")
    # Even the correct password is now refused.
    response = login(client, "student@uemp.edu.ng", "Student@1234")
    assert b"Too many failed attempts" in response.data


def test_suspended_user_cannot_log_in(client):
    user("student@uemp.edu.ng").status = "suspended"
    db.session.commit()
    response = login(client, "student@uemp.edu.ng", "Student@1234")
    assert b"suspended" in response.data


def test_suspending_logs_out_an_active_session(as_student):
    assert as_student.get("/student/").status_code == 200
    user("student@uemp.edu.ng").status = "suspended"
    db.session.commit()
    response = as_student.get("/student/")
    assert response.status_code == 302 and "/login" in response.headers["Location"]


def test_logout_requires_post(as_student):
    assert as_student.get("/logout").status_code == 405
    assert as_student.post("/logout").status_code == 302
    assert as_student.get("/student/").status_code == 302  # back to login


def test_external_next_redirect_is_ignored(client):
    response = client.post("/login?next=https://evil.example.com",
                           data={"email": "student@uemp.edu.ng", "password": "Student@1234"})
    assert "evil.example.com" not in response.headers["Location"]


def test_security_headers_present(client):
    response = client.get("/login")
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
