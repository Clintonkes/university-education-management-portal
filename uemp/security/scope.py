"""
scope.py — "Which records may this person touch?"

Permissions (permissions.py) answer "may this role do X at all?". This file
answers the second question: "on which department's data?"

    Super Admin       -> every department (no limit)
    Department Admin  -> only their own department
    Everyone else     -> nothing in the admin area

Every admin query is passed through `scoped(...)`, and every admin action on a
single record calls `ensure_department_access(...)`. So a department admin who
edits a URL to point at another department's student gets "403 Forbidden".
"""

from flask import abort
from flask_login import current_user

from ..models import Department, Role
from ..extensions import db


def is_university_wide(user=None) -> bool:
    """True for users whose admin powers cover the whole university."""
    user = user or current_user
    return user.is_authenticated and user.role == Role.SUPER_ADMIN


def allowed_department_ids(user=None) -> list[int] | None:
    """
    The department IDs this admin may manage.
    Returns None to mean "all departments" (super admin).
    """
    user = user or current_user
    if is_university_wide(user):
        return None
    if user.role == Role.DEPT_ADMIN and user.department_id:
        return [user.department_id]
    return []  # no admin rights over any department


def can_access_department(department_id: int | None, user=None) -> bool:
    allowed = allowed_department_ids(user)
    return allowed is None or (department_id is not None and department_id in allowed)


def ensure_department_access(department_id: int | None) -> None:
    """Stop the request with 403 if the record belongs to another department."""
    if not can_access_department(department_id):
        abort(403)


def scoped(query, department_column):
    """
    Limit a SELECT query to the departments the current admin may see.

        q = scoped(db.select(Course), Course.department_id)
    """
    allowed = allowed_department_ids()
    if allowed is None:
        return query
    return query.where(department_column.in_(allowed))


def manageable_departments() -> list[Department]:
    """Departments to show in drop-down menus for the current admin."""
    query = scoped(db.select(Department), Department.id).order_by(Department.name)
    return list(db.session.scalars(query))
