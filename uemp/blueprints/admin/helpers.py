"""
helpers.py — Shared bits for the admin pages.

    department_filter()   which departments to show on this page
    *_choices()           options for drop-down menus, limited to the admin's scope
"""

from flask import abort, current_app, request

from ...extensions import db
from ...models import AccountStatus, Course, Program, Role, User
from ...security import allowed_department_ids, can_access_department, manageable_departments, scoped


def department_filter() -> list[int] | None:
    """
    Departments shown on the current page.
        Dept Admin  -> always [their department]
        Super Admin -> all (None), or one if they picked ?department_id=3
    """
    allowed = allowed_department_ids()
    chosen = request.args.get("department_id", type=int)
    if chosen:
        if not can_access_department(chosen):
            abort(403)
        return [chosen]
    return allowed


def department_choices(include_blank: bool = False) -> list[tuple[int, str]]:
    choices = [(d.id, f"{d.name} ({d.code})") for d in manageable_departments()]
    return ([(0, "— Select department —")] if include_blank else []) + choices


def _filter_ids() -> list[int] | None:
    """Departments chosen in the page's filter (used to narrow other drop-downs)."""
    try:
        return department_filter()
    except Exception:  # outside a request, or not allowed: fall back to the admin's scope
        return allowed_department_ids()


def program_choices() -> list[tuple[int, str]]:
    """Programmes the admin may use. If a department is picked in the filter, only its programmes."""
    query = limit_to(scoped(db.select(Program), Program.department_id), Program.department_id, _filter_ids())
    return [(p.id, f"{p.degree} {p.name} ({p.code})") for p in db.session.scalars(query.order_by(Program.name))]


def level_choices() -> list[tuple[int, str]]:
    return [(lvl, f"{lvl} Level") for lvl in current_app.config["ACADEMIC_LEVELS"]]


def lecturer_choices() -> list[tuple[int, str]]:
    query = limit_to(scoped(
        db.select(User).where(User.role == Role.LECTURER, User.status == AccountStatus.ACTIVE),
        User.department_id,
    ), User.department_id, _filter_ids()).order_by(User.last_name)
    return [(u.id, f"{u.display_name} — {u.department.code if u.department else ''}") for u in db.session.scalars(query)]


def course_choices(term: str | None = None) -> list[tuple[int, str]]:
    query = limit_to(scoped(db.select(Course).where(Course.is_active.is_(True)), Course.department_id),
                     Course.department_id, _filter_ids()).order_by(Course.code)
    if term:
        query = query.where(Course.semester_term == term)
    return [(c.id, f"{c.code} — {c.title} ({c.units}u, {c.level}L)") for c in db.session.scalars(query)]


def limit_to(query, department_column, department_ids: list[int] | None):
    """Apply the result of department_filter() to a query (None = no limit)."""
    return query if department_ids is None else query.where(department_column.in_(department_ids))


def register_context(bp) -> None:
    """Give admin templates the department list for the Super Admin's filter box."""
    from ...models import Department
    from ...security import is_university_wide

    @bp.context_processor
    def _inject():
        if not is_university_wide():
            return {"filter_departments": []}
        return {"filter_departments": list(db.session.scalars(db.select(Department).order_by(Department.name)))}
