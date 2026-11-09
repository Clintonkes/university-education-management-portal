"""
reports.py — Numbers for dashboards and reports.

Every function accepts `department_ids`:
    None        -> whole university (Super Admin)
    [3]         -> only department 3 (Department Admin)
This way the SAME report code serves both admin levels; the caller decides
the scope using security/scope.py.
"""

from sqlalchemy import func

from ..extensions import db
from ..models import (
    AccountStatus, Course, CourseAllocation, CourseRegistration, Department, Faculty,
    Program, ResultEntry, ResultSheet, ResultStatus, Role, Semester, StudentProfile, User,
)
from .grading import pass_mark


def _limit(query, column, department_ids):
    return query if department_ids is None else query.where(column.in_(department_ids))


def _count(query) -> int:
    return db.session.scalar(query) or 0


def overview_counts(department_ids: list[int] | None, semester: Semester | None) -> dict:
    """Headline numbers for a dashboard."""
    def users(role):
        q = db.select(func.count(User.id)).where(User.role == role, User.status == AccountStatus.ACTIVE)
        return _count(_limit(q, User.department_id, department_ids))

    counts = {
        "students": users(Role.STUDENT),
        "lecturers": users(Role.LECTURER),
        "courses": _count(_limit(db.select(func.count(Course.id)).where(Course.is_active.is_(True)),
                                 Course.department_id, department_ids)),
        "programs": _count(_limit(db.select(func.count(Program.id)), Program.department_id, department_ids)),
        "registrations": 0,
        "pending_results": 0,
        "approved_results": 0,
        "unallocated_courses": 0,
    }
    if department_ids is None:
        counts["faculties"] = _count(db.select(func.count(Faculty.id)))
        counts["departments"] = _count(db.select(func.count(Department.id)))

    if semester is not None:
        reg_q = (db.select(func.count(CourseRegistration.id)).join(CourseRegistration.course)
                 .where(CourseRegistration.semester_id == semester.id))
        counts["registrations"] = _count(_limit(reg_q, Course.department_id, department_ids))

        def sheets(status):
            q = (db.select(func.count(ResultSheet.id)).join(ResultSheet.course)
                 .where(ResultSheet.semester_id == semester.id, ResultSheet.status == status))
            return _count(_limit(q, Course.department_id, department_ids))

        counts["pending_results"] = sheets(ResultStatus.SUBMITTED)
        counts["approved_results"] = sheets(ResultStatus.APPROVED)

        allocated = db.select(CourseAllocation.course_id).where(CourseAllocation.semester_id == semester.id)
        unalloc_q = (db.select(func.count(Course.id))
                     .where(Course.is_active.is_(True), Course.semester_term == semester.term,
                            Course.id.not_in(allocated)))
        counts["unallocated_courses"] = _count(_limit(unalloc_q, Course.department_id, department_ids))
    return counts


def result_status_breakdown(department_ids, semester: Semester | None) -> dict[str, int]:
    """How many result sheets are in each status this semester."""
    if semester is None:
        return {}
    q = (db.select(ResultSheet.status, func.count(ResultSheet.id)).join(ResultSheet.course)
         .where(ResultSheet.semester_id == semester.id).group_by(ResultSheet.status))
    return {status: n for status, n in db.session.execute(_limit(q, Course.department_id, department_ids))}


def students_per_department(department_ids=None) -> list[tuple[Department, int]]:
    q = (db.select(Department, func.count(User.id))
         .outerjoin(User, (User.department_id == Department.id) & (User.role == Role.STUDENT)
                    & (User.status == AccountStatus.ACTIVE))
         .group_by(Department.id).order_by(Department.name))
    return list(db.session.execute(_limit(q, Department.id, department_ids)))


def students_per_level(department_ids) -> list[tuple[int, int]]:
    q = (db.select(StudentProfile.level, func.count(StudentProfile.id)).join(StudentProfile.user)
         .where(User.status == AccountStatus.ACTIVE).group_by(StudentProfile.level).order_by(StudentProfile.level))
    return list(db.session.execute(_limit(q, User.department_id, department_ids)))


def course_registration_report(department_ids, semester: Semester) -> list[dict]:
    """For each course this semester: lecturer and number of students registered."""
    reg_count = (db.select(CourseRegistration.course_id, func.count(CourseRegistration.id).label("n"))
                 .where(CourseRegistration.semester_id == semester.id)
                 .group_by(CourseRegistration.course_id).subquery())
    q = (db.select(Course, func.coalesce(reg_count.c.n, 0))
         .outerjoin(reg_count, reg_count.c.course_id == Course.id)
         .where(Course.semester_term == semester.term, Course.is_active.is_(True))
         .order_by(Course.code))
    rows = []
    allocations = {a.course_id: a for a in db.session.scalars(
        db.select(CourseAllocation).filter_by(semester_id=semester.id))}
    for course, count in db.session.execute(_limit(q, Course.department_id, department_ids)):
        allocation = allocations.get(course.id)
        rows.append({"course": course, "students": count,
                     "lecturer": allocation.lecturer if allocation else None})
    return rows


def performance_report(department_ids, semester: Semester) -> list[dict]:
    """Average score, pass rate and grade spread for each APPROVED course."""
    q = (db.select(ResultSheet).join(ResultSheet.course)
         .where(ResultSheet.semester_id == semester.id, ResultSheet.status == ResultStatus.APPROVED)
         .order_by(Course.code))
    threshold = pass_mark()
    rows = []
    for sheet in db.session.scalars(_limit(q, Course.department_id, department_ids)):
        totals = [e.total for e in sheet.entries if e.total is not None]
        grades: dict[str, int] = {}
        for entry in sheet.entries:
            if entry.grade:
                grades[entry.grade] = grades.get(entry.grade, 0) + 1
        rows.append({
            "sheet": sheet,
            "students": len(totals),
            "average": round(sum(totals) / len(totals), 1) if totals else None,
            "pass_rate": round(100 * sum(t >= threshold for t in totals) / len(totals)) if totals else None,
            "grades": grades,
        })
    return rows


def grade_distribution(department_ids, semester: Semester) -> dict[str, int]:
    """Count of each grade across all approved results this semester."""
    q = (db.select(ResultEntry.grade, func.count(ResultEntry.id)).join(ResultEntry.sheet).join(ResultSheet.course)
         .where(ResultSheet.semester_id == semester.id, ResultSheet.status == ResultStatus.APPROVED,
                ResultEntry.grade.is_not(None))
         .group_by(ResultEntry.grade))
    return {g: n for g, n in db.session.execute(_limit(q, Course.department_id, department_ids))}
