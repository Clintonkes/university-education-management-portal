"""
extensions.py — Shared Flask extensions.

WHAT THIS FILE DOES
    Creates the extension objects (database, login manager, CSRF protection)
    once, without attaching them to an app yet. The app factory in
    uemp/__init__.py attaches them later with `.init_app(app)`.

WHY
    Creating them here avoids "circular imports": models and routes can import
    `db` from this file without importing the whole application.
"""

from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

# The database handle used by every model and query.
db = SQLAlchemy()

# Handles "who is logged in" using a signed session cookie.
login_manager = LoginManager()
login_manager.login_view = "auth.login"            # where to send logged-out users
login_manager.login_message = "Please sign in to continue."
login_manager.login_message_category = "warning"
# "strong" = if the session looks stolen (IP/browser changed), log the user out.
login_manager.session_protection = "strong"

# Adds a hidden secret token to every form so other websites cannot submit
# forms on a user's behalf (Cross-Site Request Forgery protection).
csrf = CSRFProtect()
