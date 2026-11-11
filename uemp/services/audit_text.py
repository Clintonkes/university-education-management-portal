"""
audit_text.py — Turns technical audit codes into plain English.

The audit table stores short codes such as "result.approved" (good for
searching and for developers). People reading the Audit Trail should not need
to know those codes, so every code is given:

    title       "Results approved"
    category    "Results"            — used for the filter buttons
    icon/tone   how the entry looks on the page
    meaning     one sentence explaining what the action means

`describe(entry)` returns everything a template needs to show one entry as a
readable sentence, e.g.

    Samuel Ogbu (Department Admin) approved results
    "Approved CSC 201 results for First Semester 2026/2027"

To support a new action, add ONE line to ACTIONS below.
"""

from dataclasses import dataclass

# code -> (title, category, icon, tone, meaning)
ACTIONS: dict[str, tuple[str, str, str, str, str]] = {
    # Sign-ins
    "auth.login": ("Signed in", "Sign-ins", "box-arrow-in-right", "slate", "Opened the portal with their password."),
    "auth.logout": ("Signed out", "Sign-ins", "box-arrow-right", "slate", "Closed their session."),
    "auth.locked": ("Account locked", "Sign-ins", "lock", "rose",
                    "Too many wrong passwords; the account is blocked for a short time."),
    # Results
    "result.draft_saved": ("Scores saved as draft", "Results", "save", "slate",
                           "The lecturer saved scores. Nobody else can see them yet."),
    "result.modified": ("Scores changed", "Results", "pencil-square", "gold",
                        "Scores that were already entered were changed. Old and new values are listed."),
    "result.submitted": ("Results submitted", "Results", "send-check", "blue",
                         "The lecturer sent the results to the department for approval. They are now locked."),
    "result.approved": ("Results approved", "Results", "patch-check", "green",
                        "The department approved the results. Students can now see them."),
    "result.rejected": ("Results returned", "Results", "arrow-return-left", "rose",
                        "The department sent the results back to the lecturer to correct."),
    "result.reopened": ("Approved results reopened", "Results", "unlock", "rose",
                        "Approved results were unlocked for an authorised correction. Students cannot see them until re-approved."),
    "result.correction_requested": ("Correction requested", "Results", "question-circle", "gold",
                                    "The lecturer asked permission to change results they had already submitted."),
    "result.correction_granted": ("Correction allowed", "Results", "unlock", "gold",
                                  "The department allowed the lecturer to edit their submitted results."),
    "result.correction_declined": ("Correction refused", "Results", "x-circle", "slate",
                                   "The department refused the lecturer's request to edit results."),
    # Registration
    "registration.created": ("Courses registered", "Registrations", "journal-plus", "green",
                             "A student registered courses for the semester."),
    "registration.dropped": ("Course dropped", "Registrations", "journal-minus", "gold",
                             "A student removed a course from their registration."),
    "registration.updated": ("Registration edited", "Registrations", "pencil", "gold",
                             "An administrator changed a student's course registration."),
    "registration.deleted": ("Registration deleted", "Registrations", "trash", "rose",
                             "An administrator removed a student's course registration."),
    "registration.opened": ("Registration opened", "Calendar", "door-open", "green",
                            "Students can now register courses for this semester."),
    "registration.closed": ("Registration closed", "Calendar", "door-closed", "slate",
                            "Students can no longer add or drop courses."),
    # Calendar
    "session.created": ("Session created", "Calendar", "calendar-plus", "green", "A new academic session was added."),
    "session.updated": ("Session edited", "Calendar", "calendar", "slate", "A session's name or dates were changed."),
    "session.deleted": ("Session deleted", "Calendar", "calendar-x", "rose", "An unused academic session was removed."),
    "session.completed": ("Session completed", "Calendar", "calendar-check", "blue", "The whole session was marked as finished."),
    "session.reopened": ("Session reopened", "Calendar", "calendar", "gold", "A finished session was opened again."),
    "semester.created": ("Semester added", "Calendar", "calendar-plus", "green", "A semester was added to a session."),
    "semester.updated": ("Semester edited", "Calendar", "calendar", "slate", "A semester's dates were changed."),
    "semester.deleted": ("Semester deleted", "Calendar", "calendar-x", "rose", "An unused semester was removed."),
    "semester.current_set": ("Current semester changed", "Calendar", "calendar-event", "blue",
                             "The whole portal now works in this semester."),
    "semester.completed": ("Semester completed", "Calendar", "calendar-check", "blue",
                           "The semester was marked as finished; registration is closed for good."),
    "semester.reopened": ("Semester reopened", "Calendar", "calendar", "gold", "A finished semester was opened again."),
    # Structure
    "faculty.created": ("Faculty created", "University structure", "building-add", "green", "A new faculty was added."),
    "faculty.updated": ("Faculty edited", "University structure", "building", "slate", "A faculty's name or code changed."),
    "faculty.deleted": ("Faculty deleted", "University structure", "building-dash", "rose", "An empty faculty was removed."),
    "department.created": ("Department created", "University structure", "diagram-2", "green", "A new department was added."),
    "department.updated": ("Department edited", "University structure", "diagram-2", "slate", "A department's details changed."),
    "department.deleted": ("Department deleted", "University structure", "diagram-2", "rose", "An empty department was removed."),
    "program.created": ("Programme created", "University structure", "diagram-3", "green", "A new degree programme was added."),
    "program.updated": ("Programme edited", "University structure", "diagram-3", "slate", "A programme's details changed."),
    "program.deleted": ("Programme deleted", "University structure", "diagram-3", "rose", "A programme with no students was removed."),
    # Courses
    "course.created": ("Course created", "Courses", "journal-plus", "green", "A new course was added to the catalogue."),
    "course.updated": ("Course edited", "Courses", "journal-text", "slate", "A course's details changed."),
    "allocation.created": ("Lecturer assigned", "Courses", "person-check", "green", "A lecturer was assigned to teach a course."),
    "allocation.changed": ("Lecturer changed", "Courses", "person-check", "gold", "A course was given to a different lecturer."),
    "allocation.removed": ("Lecturer unassigned", "Courses", "person-dash", "rose", "A lecturer was removed from a course."),
    # Accounts
    "user.created": ("Account created", "Accounts", "person-plus", "green", "A new user account was created."),
    "user.updated": ("Account edited", "Accounts", "person-gear", "slate", "A person's record was changed."),
    "user.deleted": ("Account deleted", "Accounts", "person-x", "rose", "A user account was permanently removed."),
    "user.status_changed": ("Account status changed", "Accounts", "toggle-on", "gold",
                            "An account was activated, deactivated, suspended or unsuspended."),
    "user.role_changed": ("Role changed", "Accounts", "shield-lock", "gold", "A staff member was given a different role."),
    "user.password_reset": ("Password reset", "Accounts", "key", "gold", "An administrator set a new password for someone."),
    "user.password_changed": ("Password changed", "Accounts", "key", "slate", "A person changed their own password."),
    "profile.updated": ("Profile updated", "Accounts", "person-vcard", "slate", "A student updated their personal details."),
}

# Filter buttons on the Audit Trail page, in display order.
CATEGORIES = ["Results", "Registrations", "Calendar", "Courses", "Accounts", "University structure", "Sign-ins"]


def codes_in(category: str) -> list[str]:
    """Every action code that belongs to a category (for filtering the table)."""
    return [code for code, info in ACTIONS.items() if info[1] == category]


@dataclass
class ReadableEntry:
    title: str
    category: str
    icon: str
    tone: str
    meaning: str
    who: str
    who_role: str
    details: str


def describe(entry) -> ReadableEntry:
    """Everything the Audit Trail page needs to show one entry in plain English."""
    fallback_title = entry.action.split(".")[-1].replace("_", " ").capitalize()
    title, category, icon, tone, meaning = ACTIONS.get(entry.action, (fallback_title, "Other", "dot", "slate", ""))
    return ReadableEntry(title=title, category=category, icon=icon, tone=tone, meaning=meaning,
                         who=entry.who, who_role=entry.who_role, details=entry.description)
