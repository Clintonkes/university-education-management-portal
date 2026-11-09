"""
web.py — Small helpers shared by all route files.

    attempt(...)       run a service call safely (commit, or roll back + show error)
    csv_response(...)  send a table as a downloadable CSV file
    get_or_404(...)    fetch a record by ID or show "Not found"
    selected_semester  read ?semester_id= from the URL, default to current
"""

import csv
import io

from flask import Response, abort, flash, request
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import AcademicSession, Semester
from .services.errors import ServiceError


def attempt(action, success_message: str | None = None) -> bool:
    """
    Run `action()` (a service call). If it works, save everything to the
    database and show a green message. If a rule is broken, undo every change
    made during this request and show the reason in a red message.
    Returns True on success so the route can decide where to go next.
    """
    try:
        action()
        db.session.commit()
    except ServiceError as error:
        db.session.rollback()
        flash(str(error), "danger")
        return False
    except IntegrityError:
        # Safety net: the database itself refused a duplicate record.
        db.session.rollback()
        flash("That record already exists or conflicts with another record.", "danger")
        return False
    if success_message:
        flash(success_message, "success")
    return True


def get_or_404(model, record_id):
    record = db.session.get(model, record_id)
    if record is None:
        abort(404)
    return record


def csv_response(filename: str, header: list[str], rows: list[list]) -> Response:
    """Build a CSV download (opens in Excel / Google Sheets)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return Response(
        buffer.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def all_semesters() -> list[Semester]:
    """Every semester, newest first — used for semester pickers."""
    query = (db.select(Semester).join(Semester.session)
             .order_by(AcademicSession.name.desc(), Semester.term.desc()))
    return list(db.session.scalars(query))


def selected_semester() -> Semester | None:
    """The semester chosen in the URL (?semester_id=5), otherwise the current one."""
    semester_id = request.args.get("semester_id", type=int)
    if semester_id:
        return db.session.get(Semester, semester_id) or abort(404)
    return Semester.current()
