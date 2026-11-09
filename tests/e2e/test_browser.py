"""
Browser end-to-end tests — a real Chromium browser clicks through the portal.

What this adds on top of the other tests:
    * real CSRF tokens, real cookies, real JavaScript (live grade preview,
      unit counter, confirmation dialogs, mobile menu);
    * the four workflows done by clicking, as an evaluator would;
    * responsive check: no sideways scrolling on a phone-sized screen;
    * no JavaScript errors in the browser console on any page.

These tests are OPT-IN because they need a browser:
    pip install playwright && playwright install --with-deps chromium
    RUN_E2E=1 pytest tests/e2e -v
Set E2E_SCREENSHOTS=/some/folder to save a screenshot of every step.
"""

import os
import re
import threading

import pytest

if os.environ.get("RUN_E2E") != "1":
    pytest.skip("browser tests are opt-in: set RUN_E2E=1", allow_module_level=True)
sync_api = pytest.importorskip("playwright.sync_api")

from werkzeug.serving import make_server  # noqa: E402

from uemp import create_app  # noqa: E402
from uemp.extensions import db  # noqa: E402
from uemp.seed import seed_demo_data  # noqa: E402

SHOTS = os.environ.get("E2E_SCREENSHOTS")


# --------------------------------------------------------------------------- #
#  Fixtures: a real server on a temporary database, and a browser
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def server(tmp_path_factory):
    db_file = tmp_path_factory.mktemp("e2e") / "e2e.db"
    app = create_app("development", {
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_file}",
        "DEBUG": False,
        "SECRET_KEY": "e2e-test-secret-key",
        "WTF_CSRF_ENABLED": True,          # real CSRF protection, like production
    })
    with app.app_context():
        db.create_all()
        seed_demo_data()
    http = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{http.server_port}"
    http.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


class Session:
    """A browser tab signed in as one user, collecting console errors."""

    def __init__(self, browser, base, width=1366, height=900):
        self.base = base
        self.context = browser.new_context(viewport={"width": width, "height": height})
        self.page = self.context.new_page()
        self.errors = []
        self.page.on("console", lambda m: m.type == "error" and self.errors.append(m.text))
        self.page.on("pageerror", lambda e: self.errors.append(str(e)))
        self.page.on("dialog", lambda d: d.accept())   # click "OK" on confirmation prompts

    def go(self, path):
        self.page.goto(self.base + path)
        self.page.wait_for_load_state("networkidle")
        return self.page

    def login(self, email, password):
        self.go("/login")
        self.page.fill("#email", email)
        self.page.fill("#password", password)
        self.page.click("button:has-text('Sign in')")
        self.page.wait_for_load_state("networkidle")
        return self

    def flash(self):
        return self.page.locator(".alert").first.inner_text()

    def shot(self, name):
        if SHOTS:
            os.makedirs(SHOTS, exist_ok=True)
            self.page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)

    def close(self):
        assert not self.errors, f"JavaScript console errors: {self.errors}"
        self.context.close()


# --------------------------------------------------------------------------- #
#  Tests (run in order — later steps build on earlier ones)
# --------------------------------------------------------------------------- #
def test_01_login_page_demo_chip_and_wrong_password(server, browser):
    s = Session(browser, server)
    s.go("/login")
    s.page.click("[data-demo-email='student@uemp.edu.ng']")
    assert s.page.input_value("#email") == "student@uemp.edu.ng"
    s.page.fill("#password", "wrong-password1")
    s.page.click("button:has-text('Sign in')")
    assert "Incorrect email or password" in s.flash()
    s.shot("01_login_error")
    s.close()


def test_02_workflow1_student_registers_with_live_unit_counter(server, browser):
    s = Session(browser, server).login("student@uemp.edu.ng", "Student@1234")
    assert s.page.url.endswith("/student/")
    s.page.click("text=Course Registration")
    submit = s.page.locator("[data-register-submit]")
    assert submit.is_disabled()                              # nothing ticked yet
    s.page.click("label.course-option:has-text('CSC 201')")
    s.page.click("label.course-option:has-text('MTH 201')")
    assert s.page.inner_text("[data-unit-total]") == "6"      # live counter: 3 + 3
    assert submit.is_enabled()
    s.shot("02_registration_selected")
    submit.click()
    s.page.wait_for_load_state("networkidle")
    assert "Courses registered successfully" in s.flash()

    # Drop a course (confirmation dialog is accepted automatically).
    s.page.locator("tr:has-text('MTH 201') button[title='Drop course']").click()
    s.page.wait_for_load_state("networkidle")
    assert "Course dropped" in s.flash()
    assert s.page.locator("label.course-option:has-text('CSC 201') input").is_checked()

    # Printable slip
    s.go("/student/")
    s.page.click("text=Print registration slip")
    s.page.wait_for_load_state("networkidle")
    assert "Course Registration Form" in s.page.content() and "CSC 201" in s.page.content()
    s.shot("02_registration_slip")
    s.close()


def test_03_workflow2_lecturer_live_grades_draft_and_submit(server, browser):
    s = Session(browser, server).login("lecturer@uemp.edu.ng", "Lecturer@1234")
    s.page.click("tr:has-text('CSC 201') >> text=Enter scores")
    s.page.wait_for_load_state("networkidle")
    rows = s.page.locator("tr[data-entry]")
    count = rows.count()
    assert count == 12                                        # 11 seeded + the student from step 02

    # Live preview: 35 + 40 = 75 -> A ; out-of-range CA is highlighted.
    first = rows.nth(0)
    first.locator("[data-ca]").fill("45")
    assert "is-invalid" in first.locator("[data-ca]").get_attribute("class")
    first.locator("[data-ca]").fill("35")
    first.locator("[data-exam]").fill("40")
    assert first.locator("[data-total]").inner_text() == "75"
    assert first.locator("[data-grade]").inner_text() == "A"

    for i in range(1, count):
        rows.nth(i).locator("[data-ca]").fill(str(20 + i))
        rows.nth(i).locator("[data-exam]").fill(str(30 + i))
    s.page.click("button:has-text('Save draft')")
    s.page.wait_for_load_state("networkidle")
    assert "Draft saved" in s.flash()
    s.shot("03_score_sheet_draft")

    s.page.click("button:has-text('Submit for approval')")
    s.page.wait_for_load_state("networkidle")
    assert "submitted for departmental review" in s.flash()
    assert s.page.locator("[data-ca]").count() == 0           # inputs are gone: sheet is locked
    s.close()


def test_04_workflow3_dept_admin_returns_then_approves(server, browser):
    admin = Session(browser, server).login("csc.admin@uemp.edu.ng", "Admin@1234")
    admin.page.click("text=Result Approval")
    admin.page.click("tr:has-text('CSC 201') a.btn:has-text('Review')")
    admin.page.wait_for_load_state("networkidle")
    admin.page.fill("textarea[name=comment]", "Please recheck CA for the first student")
    admin.page.click("button:has-text('Return for correction')")
    admin.page.wait_for_load_state("networkidle")
    assert "returned to the lecturer" in admin.flash()

    lecturer = Session(browser, server).login("lecturer@uemp.edu.ng", "Lecturer@1234")
    assert "Please recheck CA for the first student" in lecturer.page.content()
    lecturer.page.click("text=Fix now")
    lecturer.page.wait_for_load_state("networkidle")
    lecturer.page.locator("tr[data-entry]").nth(0).locator("[data-ca]").fill("33")
    lecturer.page.click("button:has-text('Submit for approval')")
    lecturer.page.wait_for_load_state("networkidle")
    assert "submitted for departmental review" in lecturer.flash()
    lecturer.close()

    admin.go("/admin/results")
    admin.page.click("tr:has-text('CSC 201') a.btn:has-text('Review')")
    admin.page.wait_for_load_state("networkidle")
    assert "Exam" in admin.page.inner_text(".timeline") or "modified" in admin.page.inner_text(".timeline").lower()
    admin.page.click("button:has-text('Approve & publish')")
    admin.page.wait_for_load_state("networkidle")
    assert "approved and published" in admin.flash()
    admin.shot("04_review_approved")
    admin.close()


def test_05_student_sees_approved_result_and_gpa(server, browser):
    s = Session(browser, server).login("student@uemp.edu.ng", "Student@1234")
    s.page.click("text=Semester Results")
    s.page.wait_for_load_state("networkidle")
    content = s.page.content()
    assert "CSC 201" in content and "Semester GPA" in content
    s.page.click("text=Academic History")
    s.page.wait_for_load_state("networkidle")
    assert "First Semester 2026/2027" in s.page.content()
    s.shot("05_student_history")
    s.close()


def test_06_workflow4_super_admin_session_and_registration_control(server, browser):
    s = Session(browser, server).login("admin@uemp.edu.ng", "Admin@1234")
    assert s.page.url.endswith("/super/")
    s.page.click("text=Sessions & Semesters")
    s.page.fill("input[name=name]", "2027/2028")
    s.page.click("button:has-text('Create session')")
    s.page.wait_for_load_state("networkidle")
    assert "Session created" in s.flash()
    card = s.page.locator(".card:has-text('2027/2028')")
    card.locator("tr:has-text('First Semester') button:has-text('Make current')").click()
    s.page.wait_for_load_state("networkidle")
    assert "is now current" in s.flash()
    s.page.locator(".card:has-text('2027/2028') tr:has-text('First Semester') button:has-text('Open registration')").click()
    s.page.wait_for_load_state("networkidle")
    assert "Registration opened" in s.flash()
    assert "First Semester 2027/2028" in s.page.inner_text(".semester-pill")

    s.page.click("text=Roles & Permissions")
    assert s.page.locator("i.perm-yes").count() > 20
    s.page.click("text=Audit Trail")
    assert "result.approved" in s.page.content() and "session.created" in s.page.content()
    s.shot("06_super_audit")
    s.close()


def test_07_access_denied_page_in_browser(server, browser):
    s = Session(browser, server).login("student@uemp.edu.ng", "Student@1234")
    response = s.page.goto(server + "/super/users")
    assert response.status == 403 and "Access denied" in s.page.content()
    s.errors.clear()  # the browser logs the 403 itself; that is expected
    s.close()


@pytest.mark.parametrize("email, password, paths", [
    ("student@uemp.edu.ng", "Student@1234", ["/student/", "/student/courses", "/student/results",
                                             "/student/history", "/student/profile"]),
    ("lecturer@uemp.edu.ng", "Lecturer@1234", ["/lecturer/", "/lecturer/courses"]),
    ("csc.admin@uemp.edu.ng", "Admin@1234", ["/admin/", "/admin/students", "/admin/courses", "/admin/allocations",
                                             "/admin/registrations", "/admin/results", "/admin/reports"]),
    ("admin@uemp.edu.ng", "Admin@1234", ["/super/", "/super/users", "/super/sessions", "/super/faculties",
                                         "/super/roles", "/super/audit"]),
], ids=["student", "lecturer", "dept_admin", "super_admin"])
def test_08_mobile_layout_has_no_sideways_scroll(server, browser, email, password, paths):
    s = Session(browser, server, width=390, height=844).login(email, password)
    for path in paths:
        s.go(path)
        overflow = s.page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
        assert overflow <= 1, f"{path} scrolls sideways by {overflow}px on a phone"
    # The menu is hidden on phones and opens with the ☰ button.
    assert not s.page.locator(".sidebar").evaluate("el => el.getBoundingClientRect().right > 0")
    s.page.click("[data-toggle-sidebar]")
    s.page.wait_for_timeout(300)
    assert s.page.locator(".sidebar").evaluate("el => el.getBoundingClientRect().left >= 0")
    s.shot(f"08_mobile_{re.sub(r'[^a-z]', '', email.split('@')[0])}")
    s.close()


def test_09_sign_out(server, browser):
    s = Session(browser, server).login("student@uemp.edu.ng", "Student@1234")
    s.page.click(".topbar .dropdown button")
    s.page.click("button:has-text('Sign out')")
    s.page.wait_for_load_state("networkidle")
    assert "/login" in s.page.url and "signed out" in s.flash()
    s.go("/student/")
    assert "/login" in s.page.url
    s.close()
