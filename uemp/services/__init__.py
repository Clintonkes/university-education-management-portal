"""
services package — the "brain" of the portal (business rules).

Routes (web pages) stay thin: they read the form, call a service, then show
the result. All rules live here, so they are:
    * written once and reused by every page that needs them,
    * easy to unit-test without a browser,
    * ready to be reused by a future mobile API without rewriting logic.

    accounts.py      create/update users, status, roles, passwords
    academic.py      sessions, semesters, opening registration
    registration.py  Workflow 1 – student course registration
    results.py       Workflows 2 & 3 – score entry, submission, approval
    grading.py       grades, GPA and CGPA
    reports.py       dashboard numbers and reports
    audit.py         the audit trail
    errors.py        ServiceError (friendly rule-breaking messages)
"""

from .errors import ServiceError

__all__ = ["ServiceError"]
