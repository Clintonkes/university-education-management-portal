"""
superadmin blueprint — university-wide administration (/super/...).

Only the Super Admin role has the UNIVERSITY_DASHBOARD permission, so every
page here is closed to everyone else. Department-level tools (students,
courses, results...) are shared with department admins in the `admin`
blueprint, where the Super Admin simply sees all departments.

    routes.py   dashboard, faculties/departments, sessions, users, roles, audit
    forms.py    the forms used on these pages
"""

from flask import Blueprint

from ...security import Perm, protect_blueprint

bp = Blueprint("superadmin", __name__)
protect_blueprint(bp, Perm.UNIVERSITY_DASHBOARD)

from . import routes  # noqa: E402,F401
