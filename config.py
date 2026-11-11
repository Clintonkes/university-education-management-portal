"""
config.py — All application settings in one place.

WHAT THIS FILE DOES
    Holds every setting the app needs (database location, security options,
    grading scale, registration limits). Settings are grouped into classes so
    we can switch between "development", "testing" and "production" with one
    environment variable (UEMP_ENV) instead of editing code.

WHY IT MATTERS FOR SCALING
    Secrets and the database URL are read from environment variables. That
    means the same code runs on a laptop with SQLite and on a server with
    PostgreSQL — you only change the environment, never the source code.
"""

import os
from datetime import timedelta

from dotenv import load_dotenv

# Load values from a local ".env" file if one exists (handy in development).
load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def normalise_db_url(url: str) -> str:
    """
    Hosting platforms (Neon, Render, Heroku) give PostgreSQL URLs as
    "postgres://..." or "postgresql://...". We rewrite them to use the modern
    psycopg (v3) driver listed in requirements.txt. Other URLs are unchanged.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _database_url() -> str:
    """DATABASE_URL if set, otherwise a local SQLite file."""
    return normalise_db_url(
        os.environ.get("DATABASE_URL") or "sqlite:///" + os.path.join(BASE_DIR, "instance", "uemp.db")
    )


def engine_options(url: str) -> dict:
    """
    Connection-pool settings. For PostgreSQL (e.g. Neon):
      * pool_pre_ping  – test each connection before use. Neon suspends idle
                         databases and closes their connections; this reconnects
                         quietly instead of showing an error page.
      * pool_recycle   – replace connections older than 5 minutes.
      * prepare_threshold=None – turn off server-side prepared statements so the
                         app also works through Neon's pooled (PgBouncer) endpoint.
    """
    if url.startswith("postgresql"):
        return {"pool_pre_ping": True, "pool_recycle": 300, "connect_args": {"prepare_threshold": None}}
    return {}


class BaseConfig:
    """Settings shared by every environment."""

    # --- Security -----------------------------------------------------------
    # The secret key signs session cookies. It MUST be a long random value in
    # production; never commit the real one to Git.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    # Cookies cannot be read by JavaScript (protects against XSS stealing them).
    SESSION_COOKIE_HTTPONLY = True
    # Cookies are not sent on cross-site POSTs (extra CSRF protection).
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    # Users are logged out automatically after 30 minutes of inactivity.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)

    # Lock an account for a short time after too many wrong passwords.
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    # --- Database -----------------------------------------------------------
    SQLALCHEMY_DATABASE_URI = _database_url()
    # Connection-pool options are built per app in create_app() from the final
    # database URL (see engine_options above).
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Academic rules -----------------------------------------------------
    # Highest CA and exam marks a lecturer can enter. CA + Exam = 100.
    MAX_CA_SCORE = 40
    MAX_EXAM_SCORE = 60

    # A student cannot register more than this many units in one semester.
    MAX_UNITS_PER_SEMESTER = 24

    # Academic levels the university offers (100 Level to 500 Level).
    ACADEMIC_LEVELS = [100, 200, 300, 400, 500]

    # GRADING SCALE (Nigerian 5-point scale).
    # Each row: (lowest total score, grade letter, grade point).
    # Rows are checked from the top; the first row whose minimum the total
    # reaches is the grade. To change the scale, edit only this list.
    GRADING_SCALE = [
        (70, "A", 5.0),
        (60, "B", 4.0),
        (50, "C", 3.0),
        (45, "D", 2.0),
        (40, "E", 1.0),
        (0, "F", 0.0),
    ]

    # Rows shown per page in long tables.
    PER_PAGE = 20

    # When "1", the app creates tables and loads demo data on start-up if the
    # database is empty. Handy for a hosted demo; leave off for real use.
    AUTO_SEED = os.environ.get("AUTO_SEED") == "1"


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    # Tests use a throw-away in-memory SQLite database by default. Set
    # TEST_DATABASE_URL to run the same tests against PostgreSQL (e.g. in CI).
    # WARNING: tests DROP every table in that database — never point it at real data.
    SQLALCHEMY_DATABASE_URI = normalise_db_url(os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:"))
    # Tests load their own demo data; never auto-seed (whatever .env says).
    AUTO_SEED = False
    # Forms in tests do not need a CSRF token.
    WTF_CSRF_ENABLED = False
    # A fast (weaker) hash keeps the test suite quick. NEVER use in production.
    PASSWORD_HASH_METHOD = "pbkdf2:sha256:1000"


class ProductionConfig(BaseConfig):
    DEBUG = False
    # Only send cookies over HTTPS in production.
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    # Browsers may keep CSS/JS for a year: every static URL carries ?v=<file
    # version>, so a new deploy still loads the new files at once.
    SEND_FILE_MAX_AGE_DEFAULT = 31_536_000


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None):
    """Return the settings class for the given environment name."""
    name = name or os.environ.get("UEMP_ENV", "development")
    return CONFIGS.get(name, DevelopmentConfig)
