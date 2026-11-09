"""
main blueprint — the home page.

Visiting "/" sends each person to the right dashboard for their role, so
nobody ever lands on a page meant for a different role.
"""

from flask import Blueprint, redirect, url_for
from flask_login import current_user

from ...models import Role

bp = Blueprint("main", __name__)

# Where each role starts after logging in.
HOME_FOR_ROLE = {
    Role.STUDENT: "student.dashboard",
    Role.LECTURER: "lecturer.dashboard",
    Role.DEPT_ADMIN: "admin.dashboard",
    Role.SUPER_ADMIN: "superadmin.dashboard",
}


@bp.route("/")
def home():
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))
    return redirect(url_for(HOME_FOR_ROLE.get(Role(current_user.role), "auth.login")))


@bp.route("/health")
def health():
    """Used by hosting platforms to check the app is running."""
    return {"status": "ok"}
