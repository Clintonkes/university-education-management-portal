"""
lecturer blueprint — the Lecturer portal (/lecturer/...).

Every page requires the lecturer permission. On top of that, each course page
checks that the course is allocated to THIS lecturer (Business rule 3).
"""

from flask import Blueprint

from ...security import Perm, protect_blueprint

bp = Blueprint("lecturer", __name__)
protect_blueprint(bp, Perm.LECTURER_PORTAL)

from . import routes  # noqa: E402,F401
