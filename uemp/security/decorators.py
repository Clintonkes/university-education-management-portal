"""
decorators.py — Guards placed on top of route functions.

    @permission_required(Perm.RESULTS_REVIEW)
    def approve(...):
        ...

Before the route runs, the guard checks:
    1. Is anyone logged in?           no  -> send to the login page
    2. Does their role have the perm? no  -> 403 Forbidden page
These checks run on the SERVER, so hiding a button in the page is never the
only protection — typing the URL directly is still blocked.
"""

from functools import wraps

from flask import abort
from flask_login import current_user

from ..extensions import login_manager
from .permissions import user_can


def permission_required(*permissions: str):
    """Allow the route only if the user has ALL of the listed permissions."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                return login_manager.unauthorized()
            if not all(user_can(current_user, p) for p in permissions):
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator


def protect_blueprint(blueprint, permission: str) -> None:
    """
    Apply one permission check to EVERY route in a blueprint.

    Used for the student and lecturer areas: a student can never open any
    /lecturer/... page, even one added in the future, because the check runs
    automatically before each request to that blueprint.
    """

    @blueprint.before_request
    def _guard():
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if not user_can(current_user, permission):
            abort(403)
        return None
