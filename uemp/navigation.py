"""
navigation.py — Builds the left-hand sidebar menu for the logged-in user.

Each menu item lists the permission it needs. A user only SEES links they are
allowed to open. (The routes still check permissions themselves — hiding a
link is a convenience, not the security.)

To add a new page to the menu, add one line to MENU below.
"""

from dataclasses import dataclass

from flask import request, url_for

from .security.permissions import Perm, user_can


@dataclass
class NavItem:
    label: str
    endpoint: str
    icon: str              # Bootstrap Icons name, see https://icons.getbootstrap.com
    permission: str
    section: str = ""      # group heading in the sidebar

    @property
    def url(self) -> str:
        return url_for(self.endpoint)

    @property
    def active(self) -> bool:
        """
        Highlight the item for its own page and its sub-pages.
        Sub-pages follow a naming convention: "admin.students" owns
        "admin.students_new", "admin.students_edit", and so on.
        """
        current = request.endpoint or ""
        return current == self.endpoint or current.startswith(self.endpoint + "_")


MENU: list[NavItem] = [
    # ---- Student --------------------------------------------------------
    NavItem("Dashboard", "student.dashboard", "speedometer2", Perm.STUDENT_PORTAL),
    NavItem("My Profile", "student.profile", "person-vcard", Perm.STUDENT_PORTAL),
    NavItem("Course Registration", "student.registration", "journal-plus", Perm.STUDENT_PORTAL, "Academics"),
    NavItem("Semester Results", "student.results", "clipboard-data", Perm.STUDENT_PORTAL, "Academics"),
    NavItem("Academic History", "student.history", "mortarboard", Perm.STUDENT_PORTAL, "Academics"),

    # ---- Lecturer -------------------------------------------------------
    NavItem("Dashboard", "lecturer.dashboard", "speedometer2", Perm.LECTURER_PORTAL),
    NavItem("My Courses", "lecturer.courses", "journal-bookmark", Perm.LECTURER_PORTAL, "Teaching"),

    # ---- Super Admin overview -------------------------------------------
    NavItem("University Dashboard", "superadmin.dashboard", "globe2", Perm.UNIVERSITY_DASHBOARD),

    # ---- Department / shared administration ----------------------------
    NavItem("Department Dashboard", "admin.dashboard", "speedometer2", Perm.ADMIN_PORTAL),
    NavItem("Students", "admin.students", "people", Perm.STUDENTS_MANAGE, "Records"),
    NavItem("Lecturers", "admin.lecturers", "person-workspace", Perm.LECTURERS_MANAGE, "Records"),
    NavItem("Programmes", "admin.programs", "diagram-3", Perm.PROGRAMS_MANAGE, "Academics"),
    NavItem("Courses", "admin.courses", "book", Perm.COURSES_MANAGE, "Academics"),
    NavItem("Course Allocation", "admin.allocations", "person-check", Perm.ALLOCATIONS_MANAGE, "Academics"),
    NavItem("Registrations", "admin.registrations", "card-checklist", Perm.REGISTRATIONS_VIEW, "Academics"),
    NavItem("Result Approval", "admin.results", "patch-check", Perm.RESULTS_REVIEW, "Results"),
    NavItem("Reports", "admin.reports", "bar-chart-line", Perm.REPORTS_VIEW, "Results"),

    # ---- Super Admin only -----------------------------------------------
    NavItem("Faculties & Departments", "superadmin.faculties", "building", Perm.FACULTIES_MANAGE, "University"),
    NavItem("Sessions & Semesters", "superadmin.sessions", "calendar3", Perm.SESSIONS_MANAGE, "University"),
    NavItem("User Accounts", "superadmin.users", "person-gear", Perm.USERS_MANAGE_ALL, "University"),
    NavItem("Roles & Permissions", "superadmin.roles", "shield-lock", Perm.ROLES_MANAGE, "University"),
    NavItem("Audit Trail", "superadmin.audit", "clock-history", Perm.AUDIT_VIEW, "University"),
]


def build_navigation(user) -> list[tuple[str, list[NavItem]]]:
    """Return the visible menu grouped by section: [(section, [items...]), ...]."""
    groups: dict[str, list[NavItem]] = {}
    for item in MENU:
        if user_can(user, item.permission):
            groups.setdefault(item.section, []).append(item)
    return list(groups.items())


def active_endpoint(groups) -> str:
    """Endpoint of the highlighted menu item (sent with each page so the
    sidebar can update its highlight without being reloaded)."""
    for _section, items in groups:
        for item in items:
            if item.active:
                return item.endpoint
    return ""
