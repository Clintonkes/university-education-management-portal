"""
UEMP — University Education Management Portal
==============================================

This file builds the Flask application ("app factory" pattern).

WHAT HAPPENS WHEN THE APP STARTS (create_app)
    1. Load settings from config.py (development / testing / production).
    2. Connect the extensions: database, login manager, CSRF protection.
    3. Register the blueprints — each blueprint is one area of the site:
           auth        /login, /logout, change password
           main        "/" sends each user to their own dashboard
           student     /student/...     (Students only)
           lecturer    /lecturer/...    (Lecturers only)
           admin       /admin/...       (Department Admins + Super Admin, scoped)
           superadmin  /super/...       (Super Admin only)
    4. Add error pages, security headers and template helpers.
    5. Add command-line tools:  `flask init-db`  and  `flask seed`.

WHY AN APP FACTORY
    Tests can create a fresh app with a test database, and production can run
    several worker processes, each creating its own app the same way.
"""

import os
from datetime import datetime

from flask import Flask, render_template, session

from config import engine_options, get_config
from .extensions import csrf, db, login_manager


def create_app(config_name: str | None = None, overrides: dict | None = None) -> Flask:
    """Build the app. `overrides` lets tests change settings (e.g. use a temporary database)."""
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.config.update(overrides or {})
    # Build a FRESH options dict for this app's database. (Flask-SQLAlchemy edits
    # this dict in place, so it must never be shared between app instances.)
    app.config.setdefault("SQLALCHEMY_ENGINE_OPTIONS", engine_options(app.config["SQLALCHEMY_DATABASE_URI"]))
    os.makedirs(app.instance_path, exist_ok=True)

    if not app.config.get("TESTING") and not app.debug and app.config["SECRET_KEY"] == "dev-only-change-me":
        raise RuntimeError("Set the SECRET_KEY environment variable before running in production.")

    # --- Extensions ----------------------------------------------------------
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        """Called on every request to turn the session's user ID into a User."""
        user = db.session.get(User, int(user_id))
        # A suspended/deactivated user is logged out on their very next click.
        return user if user and user.is_active else None

    # --- Blueprints ----------------------------------------------------------
    from .blueprints.admin import bp as admin_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.lecturer import bp as lecturer_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.student import bp as student_bp
    from .blueprints.superadmin import bp as superadmin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp, url_prefix="/student")
    app.register_blueprint(lecturer_bp, url_prefix="/lecturer")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(superadmin_bp, url_prefix="/super")

    _register_request_hooks(app)
    _register_error_pages(app)
    _register_template_helpers(app)

    from .cli import register_cli
    register_cli(app)

    if app.config.get("AUTO_SEED"):
        _auto_seed(app)
    return app


def _auto_seed(app: Flask) -> None:
    """
    Create tables and demo data on first start (only if there are no users yet).

    Run gunicorn with --preload so this happens ONCE, before worker processes
    are started. If two processes still race, the loser's insert fails on the
    unique email column; we roll back and carry on, because the data exists.
    """
    from sqlalchemy.exc import IntegrityError

    from .seed import seed_demo_data

    with app.app_context():
        try:
            db.create_all()
            seed_demo_data()
        except IntegrityError:
            db.session.rollback()
            app.logger.info("Demo data was already created by another process.")
        finally:
            db.session.remove()
            # Close pooled connections so forked workers open their own
            # (sharing a database connection between processes corrupts it).
            db.engine.dispose()


def _register_request_hooks(app: Flask) -> None:
    @app.before_request
    def _refresh_session_timeout():
        # Marking the session "permanent" makes PERMANENT_SESSION_LIFETIME apply,
        # and Flask refreshes the expiry on every request (idle timeout).
        session.permanent = True

    @app.after_request
    def _security_headers(response):
        """Extra browser protections added to every page."""
        response.headers.setdefault("X-Content-Type-Options", "nosniff")     # no MIME guessing
        response.headers.setdefault("X-Frame-Options", "DENY")               # no click-jacking via iframes
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Pages with private data must not be cached by shared computers/proxies.
        response.headers.setdefault("Cache-Control", "no-store")
        return response


def _register_error_pages(app: Flask) -> None:
    """Friendly pages instead of raw server errors."""

    def render(code: int, title: str, message: str):
        return render_template("errors/error.html", code=code, title=title, message=message), code

    app.register_error_handler(400, lambda e: render(400, "Bad request", "The form was incomplete or has expired. Please try again."))
    app.register_error_handler(403, lambda e: render(403, "Access denied", "Your account does not have permission to view this page."))
    app.register_error_handler(404, lambda e: render(404, "Page not found", "The page or record you requested does not exist."))

    @app.errorhandler(500)
    def _server_error(error):
        db.session.rollback()  # leave the database clean after a crash
        return render(500, "Something went wrong", "An unexpected error occurred. Please try again shortly.")


def _register_template_helpers(app: Flask) -> None:
    from flask_login import current_user

    from .models import ResultStatus, Role, Semester
    from .navigation import build_navigation
    from .security import Perm, user_can

    @app.context_processor
    def inject_globals():
        """Values available in every HTML template."""
        current_semester = Semester.current() if current_user.is_authenticated else None
        return {
            "current_semester": current_semester,
            "navigation": build_navigation(current_user) if current_user.is_authenticated else [],
            "can": lambda perm: user_can(current_user, perm),
            "Perm": Perm,
            "Role": Role,
            "ResultStatus": ResultStatus,
            "app_name": "UEMP",
            "now": datetime.now(),
        }

    @app.template_filter("dt")
    def format_datetime(value, fmt="%d %b %Y, %H:%M"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("d")
    def format_date(value, fmt="%d %b %Y"):
        return value.strftime(fmt) if value else "—"

    @app.template_filter("score")
    def format_score(value):
        """Show 12.0 as '12' and 12.5 as '12.5' (blank when there is no score)."""
        return "" if value is None else f"{value:g}"

    @app.template_filter("num")
    def format_number(value, places=2):
        return "—" if value is None else f"{value:.{places}f}"
