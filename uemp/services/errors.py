"""
errors.py — The one error type used by the service layer.

When a business rule is broken (e.g. "you already registered this course"),
a service raises ServiceError with a friendly message. The web route catches
it and shows the message to the user as a red alert. The database is never
left half-updated because the route rolls back on error.
"""


class ServiceError(Exception):
    """A rule was broken. `str(error)` is safe to show to the user."""
