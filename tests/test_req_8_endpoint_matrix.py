"""
Brief §8 acceptance criterion:
    "Unauthorized users cannot access restricted pages or backend endpoints."

This test does NOT use a hand-written list of URLs. It reads EVERY route the
application registers (app.url_map) and calls each one — with GET and POST —
as an anonymous visitor and as each of the four roles. So any route added in
the future is automatically checked too.

Expected access is decided by the URL area:
    /student/...   -> Student only
    /lecturer/...  -> Lecturer only
    /admin/...     -> Department Admin and Super Admin, except the actions in
                      SUPER_ONLY_ADMIN_ACTIONS (account status, deletes and
                      registration edits), which are Super Admin only
    /super/...     -> Super Admin only
    /account/..., /logout -> any signed-in user
Also: nothing may ever return a 500 (server error).
"""

import pytest

from uemp.extensions import db
from uemp.models import CourseRegistration, Department, Faculty, Program

from .conftest import allocation_for, course, current_semester, password_for, login, sheet_for, user

ROLES = {
    "student": "student@uemp.edu.ng",
    "lecturer": "lecturer@uemp.edu.ng",
    "dept_admin": "csc.admin@uemp.edu.ng",
    "super_admin": "admin@uemp.edu.ng",
}
AREA_ACCESS = {
    "/student": {"student"},
    "/lecturer": {"lecturer"},
    "/admin": {"dept_admin", "super_admin"},
    "/super": {"super_admin"},
    "/account": set(ROLES),
    "/logout": set(ROLES),
}
PUBLIC = {"static", "auth.login", "main.health"}
SUPER_ONLY_ADMIN_ACTIONS = {
    ("admin.users_status", "POST"), ("admin.users_unlock", "POST"), ("admin.users_delete", "POST"),
    ("admin.registrations_view", "POST"), ("admin.registrations_delete", "POST"),
}


def _url_values():
    """Real record IDs (from the CSC department) to fill <placeholders> in routes."""
    reg = db.session.scalar(db.select(CourseRegistration).filter_by(
        student_id=user("student@uemp.edu.ng").id))
    return {
        "allocation_id": allocation_for("CSC 201").id,
        "sheet_id": sheet_for("CSC 203").id,
        "program_id": db.session.scalar(db.select(Program.id).filter_by(code="BSC-CSC")),
        "course_id": course("CSC 201").id,
        "faculty_id": db.session.scalar(db.select(Faculty.id).filter_by(code="SCI")),
        "department_id": db.session.scalar(db.select(Department.id).filter_by(code="CSC")),
        "semester_id": current_semester().id,
        "session_id": current_semester().session_id,
        "registration_id": reg.id,
        "tab": "students",
    }


def _user_id_for(endpoint):
    if "lecturer" in endpoint:
        return user("lecturer@uemp.edu.ng").id
    return user("csc25002@uemp.edu.ng").id


def _all_routes(app):
    values = _url_values()
    routes = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint in PUBLIC:
            continue
        args = {a: values.get(a) for a in rule.arguments}
        if "user_id" in rule.arguments:
            args["user_id"] = _user_id_for(rule.endpoint)
        path = rule.rule
        for name, value in args.items():
            path = path.replace(f"<int:{name}>", str(value)).replace(f"<{name}>", str(value))
        for method in sorted(rule.methods & {"GET", "POST"}):
            routes.append((rule.endpoint, method, path))
    # Deletes run last, so the records they remove are not needed by later checks.
    return sorted(routes, key=lambda r: "delete" in r[0])


def _allowed_roles(endpoint, method, path):
    if (endpoint, method) in SUPER_ONLY_ADMIN_ACTIONS:
        return {"super_admin"}
    for prefix, roles in AREA_ACCESS.items():
        if path.startswith(prefix):
            return roles
    return set(ROLES)  # "/" — any signed-in user (redirects to their dashboard)


def test_route_inventory_is_complete(app):
    routes = _all_routes(app)
    assert len(routes) >= 60, "expected every page and action to be discovered"


def test_anonymous_visitor_is_sent_to_login_everywhere(app):
    for endpoint, method, path in _all_routes(app):
        client = app.test_client()
        response = client.open(path, method=method)
        assert response.status_code == 302 and "/login" in response.headers["Location"], (endpoint, method, path)


@pytest.mark.parametrize("role", list(ROLES))
def test_each_role_only_reaches_its_own_areas(app, role):
    client = app.test_client()
    assert login(client, ROLES[role], password_for(ROLES[role])).status_code == 302
    problems = []
    for endpoint, method, path in _all_routes(app):
        if endpoint == "auth.logout":
            continue  # would end the session for the remaining checks
        response = client.open(path, method=method)
        allowed = role in _allowed_roles(endpoint, method, path)
        if response.status_code >= 500:
            problems.append(f"500 on {method} {path}")
        elif not allowed and response.status_code != 403:
            problems.append(f"{role} NOT blocked: {method} {path} -> {response.status_code}")
        elif allowed and response.status_code == 403:
            problems.append(f"{role} wrongly blocked: {method} {path}")
        elif allowed and method == "GET" and response.status_code not in (200, 302):
            problems.append(f"{role} GET {path} -> {response.status_code}")
    assert not problems, "\n".join(problems)
