"""
permissions.py — The single source of truth for "who can do what".

HOW RBAC WORKS IN THIS APP (Role-Based Access Control)
    1. Every action is given a permission name, e.g. "results.approve".
    2. Each role is given a set of permissions in ROLE_PERMISSIONS below.
    3. Routes are protected with @permission_required("results.approve").
       If the logged-in user's role does not have it, they get "403 Forbidden".

    Checking a *permission* (not a role name) inside routes means that adding a
    new role later — e.g. "Exams Officer" — is just one new entry in this file.

PERMISSIONS ARE ONLY HALF OF THE CHECK
    A department admin has "students.manage", but only for THEIR department.
    That second check ("which records?") lives in security/scope.py.
"""

from ..models.enums import Role


class Perm:
    """All permission names used in the app, in one list."""

    # Student self-service
    STUDENT_PORTAL = "student.portal"

    # Lecturer work
    LECTURER_PORTAL = "lecturer.portal"
    RESULTS_ENTER = "results.enter"

    # Department-level management (scoped to a department)
    ADMIN_PORTAL = "admin.portal"
    STUDENTS_MANAGE = "students.manage"
    LECTURERS_MANAGE = "lecturers.manage"
    COURSES_MANAGE = "courses.manage"
    ALLOCATIONS_MANAGE = "allocations.manage"
    PROGRAMS_MANAGE = "programs.manage"
    REGISTRATIONS_VIEW = "registrations.view"
    RESULTS_REVIEW = "results.review"
    REPORTS_VIEW = "reports.view"

    # University-wide administration (Super Admin only)
    UNIVERSITY_DASHBOARD = "university.dashboard"
    FACULTIES_MANAGE = "faculties.manage"
    DEPARTMENTS_MANAGE = "departments.manage"
    SESSIONS_MANAGE = "sessions.manage"
    USERS_MANAGE_ALL = "users.manage_all"
    ROLES_MANAGE = "roles.manage"
    AUDIT_VIEW = "audit.view"


# Short description of each permission, shown on the Roles & Permissions page.
PERMISSION_DESCRIPTIONS = {
    Perm.STUDENT_PORTAL: "Use the student portal (own profile, courses, results)",
    Perm.LECTURER_PORTAL: "Use the lecturer portal (assigned courses, class lists)",
    Perm.RESULTS_ENTER: "Enter, save and submit scores for assigned courses",
    Perm.ADMIN_PORTAL: "Open the administration area",
    Perm.STUDENTS_MANAGE: "Register and update student records",
    Perm.LECTURERS_MANAGE: "Create and update lecturer profiles",
    Perm.COURSES_MANAGE: "Create and update courses",
    Perm.ALLOCATIONS_MANAGE: "Assign lecturers to courses",
    Perm.PROGRAMS_MANAGE: "Create and update academic programmes",
    Perm.REGISTRATIONS_VIEW: "View student course registrations",
    Perm.RESULTS_REVIEW: "Approve, reject or reopen submitted results",
    Perm.REPORTS_VIEW: "View student, registration and performance reports",
    Perm.UNIVERSITY_DASHBOARD: "View the university-wide dashboard",
    Perm.FACULTIES_MANAGE: "Create and update faculties",
    Perm.DEPARTMENTS_MANAGE: "Create and update departments",
    Perm.SESSIONS_MANAGE: "Create sessions/semesters and control registration",
    Perm.USERS_MANAGE_ALL: "Manage every account and its status",
    Perm.ROLES_MANAGE: "Change a staff member's role",
    Perm.AUDIT_VIEW: "Read the system audit trail",
}

# Department admins and super admins share the management permissions.
_MANAGEMENT = {
    Perm.ADMIN_PORTAL, Perm.STUDENTS_MANAGE, Perm.LECTURERS_MANAGE, Perm.COURSES_MANAGE,
    Perm.ALLOCATIONS_MANAGE, Perm.PROGRAMS_MANAGE, Perm.REGISTRATIONS_VIEW,
    Perm.RESULTS_REVIEW, Perm.REPORTS_VIEW,
}

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.STUDENT: frozenset({Perm.STUDENT_PORTAL}),
    Role.LECTURER: frozenset({Perm.LECTURER_PORTAL, Perm.RESULTS_ENTER}),
    Role.DEPT_ADMIN: frozenset(_MANAGEMENT),
    Role.SUPER_ADMIN: frozenset(
        _MANAGEMENT | {
            Perm.UNIVERSITY_DASHBOARD, Perm.FACULTIES_MANAGE, Perm.DEPARTMENTS_MANAGE,
            Perm.SESSIONS_MANAGE, Perm.USERS_MANAGE_ALL, Perm.ROLES_MANAGE, Perm.AUDIT_VIEW,
        }
    ),
}


def role_has_permission(role: str, permission: str) -> bool:
    """True if the given role is allowed to perform the given permission."""
    try:
        return permission in ROLE_PERMISSIONS[Role(role)]
    except ValueError:  # unknown role text in the database -> deny
        return False


def user_can(user, permission: str) -> bool:
    """True if a logged-in, active user has the permission."""
    return bool(user and user.is_authenticated and user.is_active and role_has_permission(user.role, permission))
