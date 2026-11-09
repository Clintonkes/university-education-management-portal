"""auth blueprint — signing in, signing out and changing your password."""

from flask import Blueprint

bp = Blueprint("auth", __name__)

from . import routes  # noqa: E402,F401  (registers the routes on `bp`)
