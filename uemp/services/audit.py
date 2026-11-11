"""
audit.py — Writing entries to the audit trail.

    record(actor, "result.approved", "Approved CSC 201 results", sheet)

IMPORTANT: this function does NOT commit. The audit row is saved in the SAME
database transaction as the change it describes, so either both are saved or
neither is. You can never get an approval without its audit entry.
"""

from flask import has_request_context, request

from ..extensions import db
from ..models import AuditLog


def _client_ip() -> str | None:
    """The user's IP address, if we are inside a web request."""
    if not has_request_context():
        return None
    # When running behind a proxy (e.g. Render, Nginx) the real IP is in X-Forwarded-For.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return (forwarded.split(",")[0].strip() or request.remote_addr) if forwarded else request.remote_addr


def record(actor, action: str, description: str, entity=None) -> AuditLog:
    """Add one audit entry to the current transaction."""
    entry = AuditLog(
        actor_id=getattr(actor, "id", None),
        actor_name=getattr(actor, "display_name", None),
        actor_role=getattr(actor, "role", None),
        action=action,
        description=description,
        entity_type=type(entity).__name__ if entity is not None else None,
        entity_id=getattr(entity, "id", None),
        ip_address=_client_ip(),
    )
    db.session.add(entry)
    return entry
