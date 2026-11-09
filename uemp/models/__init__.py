"""
models package — Every database table in the portal.

Import models from here, e.g.  `from uemp.models import User, Course`.
Each file groups related tables:

    enums.py     allowed values (roles, statuses)
    academic.py  Faculty, Department, Program, AcademicSession, Semester
    user.py      User, StudentProfile, LecturerProfile
    course.py    Course, CourseAllocation, CourseRegistration
    result.py    ResultSheet, ResultEntry
    audit.py     AuditLog
"""

from .academic import AcademicSession, Department, Faculty, Program, Semester
from .audit import AuditLog
from .course import Course, CourseAllocation, CourseRegistration, course_programs
from .enums import AccountStatus, ResultStatus, Role, SemesterTerm
from .result import ResultEntry, ResultSheet
from .user import LecturerProfile, StudentProfile, User

__all__ = [
    "AcademicSession", "AccountStatus", "AuditLog", "Course", "CourseAllocation",
    "CourseRegistration", "Department", "Faculty", "LecturerProfile", "Program",
    "ResultEntry", "ResultSheet", "ResultStatus", "Role", "Semester", "SemesterTerm",
    "StudentProfile", "User", "course_programs",
]
