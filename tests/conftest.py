"""
conftest.py — Shared test setup (pytest "fixtures").

Every test gets a FRESH in-memory database filled with the demo data, so
tests never affect each other. Helper fixtures log in as each role.
"""

import pytest
from flask.testing import FlaskClient

from uemp import create_app
from uemp.extensions import db
from uemp.models import Course, CourseAllocation, ResultSheet, Semester, User
from uemp.seed import seed_demo_data


class IsolatedClient(FlaskClient):
    """
    Runs every request in its OWN application context, exactly like a real
    server. Without this, Flask reuses the test's context, so cached data
    (such as the logged-in user) could leak from one client to another.
    """

    def open(self, *args, **kwargs):
        with self.application.app_context():
            return super().open(*args, **kwargs)


@pytest.fixture()
def app():
    app = create_app("testing")
    app.test_client_class = IsolatedClient
    with app.app_context():
        db.create_all()
        seed_demo_data()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, email, password):
    """Sign in and return the response (302 redirect on success)."""
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture()
def as_student(client):
    login(client, "student@uemp.edu.ng", "Student@1234")
    return client


@pytest.fixture()
def as_lecturer(client):
    login(client, "lecturer@uemp.edu.ng", "Lecturer@1234")
    return client


@pytest.fixture()
def as_csc_admin(client):
    login(client, "csc.admin@uemp.edu.ng", "Admin@1234")
    return client


@pytest.fixture()
def as_eco_admin(client):
    login(client, "eco.admin@uemp.edu.ng", "Admin@1234")
    return client


@pytest.fixture()
def as_super(client):
    login(client, "admin@uemp.edu.ng", "Admin@1234")
    return client


# ---- Small lookup helpers used by many tests ---------------------------------
# Each request runs in its own database session, so before looking something up
# we "expire" the test's cached objects to read the latest saved values.
def user(email) -> User:
    db.session.expire_all()
    return db.session.scalar(db.select(User).filter_by(email=email))


def course(code) -> Course:
    db.session.expire_all()
    return db.session.scalar(db.select(Course).filter_by(code=code))


def current_semester() -> Semester:
    return Semester.current()


def allocation_for(code) -> CourseAllocation:
    return db.session.scalar(db.select(CourseAllocation).filter_by(course_id=course(code).id,
                                                                   semester_id=current_semester().id))


def sheet_for(code) -> ResultSheet:
    db.session.expire_all()
    return db.session.scalar(db.select(ResultSheet).filter_by(course_id=course(code).id,
                                                              semester_id=current_semester().id))


# ---- Logging in as anyone --------------------------------------------------------
DEMO_PASSWORDS = {
    "admin@uemp.edu.ng": "Admin@1234", "csc.admin@uemp.edu.ng": "Admin@1234", "eco.admin@uemp.edu.ng": "Admin@1234",
}


DEMO_LECTURERS = {"lecturer@uemp.edu.ng", "bakare@uemp.edu.ng", "musa@uemp.edu.ng", "eze@uemp.edu.ng",
                  "adeyemi@uemp.edu.ng"}


def password_for(email: str) -> str:
    """Demo passwords: admins Admin@1234, lecturers Lecturer@1234, students Student@1234."""
    if email in DEMO_PASSWORDS:
        return DEMO_PASSWORDS[email]
    return "Lecturer@1234" if email in DEMO_LECTURERS else "Student@1234"


@pytest.fixture()
def client_as(app):
    """Factory: client_as("someone@uemp.edu.ng") returns a NEW client signed in as that user."""
    def make(email):
        c = app.test_client()
        response = login(c, email, password_for(email))
        assert response.status_code == 302, f"login failed for {email}"
        return c
    return make


def fill_scores(sheet, ca="30", exam="45", action="save"):
    """Form data that gives every student on a sheet the same CA and exam score."""
    data = {"action": action}
    for entry in sheet.entries:
        data[f"ca_{entry.id}"], data[f"exam_{entry.id}"] = ca, exam
    return data
