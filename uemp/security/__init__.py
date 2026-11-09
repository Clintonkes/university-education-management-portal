"""
security package — access control for the whole portal.

    permissions.py  which ROLE may do which ACTION (RBAC table)
    decorators.py   guards that enforce permissions on routes
    scope.py        which DEPARTMENT's data an admin may touch
"""

from .decorators import permission_required, protect_blueprint
from .permissions import Perm, user_can
from .scope import (
    allowed_department_ids,
    can_access_department,
    ensure_department_access,
    is_university_wide,
    manageable_departments,
    scoped,
)

__all__ = [
    "Perm", "allowed_department_ids", "can_access_department", "ensure_department_access",
    "is_university_wide", "manageable_departments", "permission_required",
    "protect_blueprint", "scoped", "user_can",
]
