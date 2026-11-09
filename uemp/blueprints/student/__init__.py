"""
student blueprint — the Student portal (/student/...).

`protect_blueprint` makes EVERY page here require the student permission, so
lecturers and admins can never open a student page and vice versa.
"""

from flask import Blueprint

from ...security import Perm, protect_blueprint

bp = Blueprint("student", __name__)
protect_blueprint(bp, Perm.STUDENT_PORTAL)

from . import routes  # noqa: E402,F401
