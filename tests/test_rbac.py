"""Role-based access control and department scoping."""

import pytest

from .conftest import course, sheet_for, user


@pytest.mark.parametrize("url", ["/student/", "/lecturer/", "/admin/", "/super/"])
def test_anonymous_users_are_sent_to_login(client, url):
    response = client.get(url)
    assert response.status_code == 302 and "/login" in response.headers["Location"]


@pytest.mark.parametrize("url", ["/lecturer/", "/admin/", "/admin/students", "/super/", "/super/users"])
def test_student_cannot_open_staff_pages(as_student, url):
    assert as_student.get(url).status_code == 403


@pytest.mark.parametrize("url", ["/student/", "/admin/", "/admin/results", "/super/"])
def test_lecturer_cannot_open_other_areas(as_lecturer, url):
    assert as_lecturer.get(url).status_code == 403


@pytest.mark.parametrize("url", ["/super/", "/super/users", "/super/sessions", "/super/audit", "/student/", "/lecturer/"])
def test_department_admin_cannot_open_super_admin_or_personal_portals(as_csc_admin, url):
    assert as_csc_admin.get(url).status_code == 403


def test_super_admin_can_open_department_tools(as_super):
    for url in ["/admin/", "/admin/students", "/admin/results", "/admin/reports"]:
        assert as_super.get(url).status_code == 200


def test_department_admin_cannot_view_another_departments_student(as_eco_admin):
    csc_student = user("csc25002@uemp.edu.ng")
    assert as_eco_admin.get(f"/admin/students/{csc_student.id}").status_code == 403
    assert as_eco_admin.get(f"/admin/students/{csc_student.id}/edit").status_code == 403


def test_department_admin_list_only_shows_own_department(as_eco_admin):
    page = as_eco_admin.get("/admin/students").get_data(as_text=True)
    assert "ECO/2026/001" in page
    assert "CSC/2025/001" not in page


def test_department_admin_cannot_edit_another_departments_course(as_eco_admin):
    assert as_eco_admin.get(f"/admin/courses/{course('CSC 201').id}/edit").status_code == 403


def test_department_admin_cannot_review_another_departments_results(as_eco_admin):
    sheet = sheet_for("CSC 203")
    assert as_eco_admin.get(f"/admin/results/{sheet.id}").status_code == 403
    assert as_eco_admin.post(f"/admin/results/{sheet.id}/decision", data={"decision": "approve"}).status_code == 403


def test_department_admin_cannot_filter_into_another_department(as_eco_admin):
    csc_id = user("csc.admin@uemp.edu.ng").department_id
    assert as_eco_admin.get(f"/admin/students?department_id={csc_id}").status_code == 403
