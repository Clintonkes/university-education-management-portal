"""
admin blueprint — department-level administration (/admin/...).

WHO USES IT
    * Department Admins  -> see and manage ONLY their own department.
    * Super Admin        -> sees every department, and can filter by one.

The same pages serve both roles. The difference is decided in one place,
security/scope.py, so there is no duplicated code for "dept" vs "super" views.

FILES
    helpers.py        shared choices and department filter
    dashboard.py      department dashboard
    people.py         students and lecturers
    academics.py      programmes, courses, allocations, registrations
    results.py        Workflow 3 – result review & approval
    reports.py        reports and CSV exports
"""

from flask import Blueprint

from ...security import Perm, protect_blueprint

bp = Blueprint("admin", __name__)
protect_blueprint(bp, Perm.ADMIN_PORTAL)

from .helpers import register_context  # noqa: E402

register_context(bp)

from . import academics, dashboard, people, reports, results  # noqa: E402,F401
