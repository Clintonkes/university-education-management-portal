"""
reports.py — Numbers for dashboards and reports.

Every function accepts `department_ids`:
    None        -> whole university (Super Admin)
    [3]         -> only department 3 (Department Admin)
This way the SAME report code serves both admin levels; the caller decides
the scope using security/scope.py.
"""

from sqlalchemy import func
from sqlalchemy.orm import joinedload, selectinload

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
         .options(selectinload(ResultSheet.entries))
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


# --------------------------------------------------------------------------- #
#  Department report — one page summarising a department for a semester
# --------------------------------------------------------------------------- #
# The formulas shown on the report page. Kept next to the code that computes
# them, so the explanation and the calculation cannot drift apart.
REPORT_FORMULAS = [
    ("Student–lecturer ratio", "active students ÷ active lecturers"),
    ("Allocation coverage", "courses with a lecturer ÷ courses offered this semester × 100"),
    ("Registration rate", "students who registered at least one course ÷ active students × 100"),
    ("Average load", "total registered units ÷ students who registered"),
    ("Result completion", "approved result sheets ÷ all result sheets this semester × 100"),
    ("Average score", "sum of approved totals ÷ number of approved results"),
    ("Pass rate", "approved results with grade point above 0 ÷ approved results × 100"),
    ("Semester GPA", "for each student: Σ(units × grade point) ÷ Σ(units) for this semester's approved results; "
                     "the report shows the average of those GPAs"),
    ("CGPA", "the same formula over ALL of a student's approved results"),
    ("At risk", "students whose CGPA is below 1.50"),
]

GPA_BANDS = [  # (lowest GPA in band, label) — matches grading.degree_class()
    (4.5, "First Class (4.50–5.00)"),
    (3.5, "Second Class Upper (3.50–4.49)"),
    (2.4, "Second Class Lower (2.40–3.49)"),
    (1.5, "Third Class (1.50–2.39)"),
    (0.0, "Below 1.50"),
]
AT_RISK_CGPA = 1.5


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def _band(gpa: float) -> str:
    return next(label for low, label in GPA_BANDS if gpa >= low)


def _gpa_by_student(rows) -> dict[int, float]:
    """rows: (student_id, units, grade_point) -> {student_id: GPA}."""
    from .grading import calculate_gpa

    grouped: dict[int, list[tuple[int, float]]] = {}
    for student_id, units, point in rows:
        grouped.setdefault(student_id, []).append((units, point or 0))
    return {sid: calculate_gpa(items) for sid, items in grouped.items()}


def department_report(department_ids, semester: Semester | None) -> dict:
    """
    Everything on the Department Report, for one department (or the whole
    university when department_ids is None) in one semester.
    """
    def students_q(*columns):
        q = db.select(*columns).join(StudentProfile.user).where(User.status == AccountStatus.ACTIVE,
                                                               User.role == Role.STUDENT)
        return _limit(q, User.department_id, department_ids)

    report: dict = {"semester": semester, "formulas": REPORT_FORMULAS}

    # ---- People -------------------------------------------------------------
    students = _count(students_q(func.count(StudentProfile.id)))
    lecturers = _count(_limit(db.select(func.count(User.id)).where(
        User.role == Role.LECTURER, User.status == AccountStatus.ACTIVE), User.department_id, department_ids))
    report["students"] = students
    report["lecturers"] = lecturers
    report["ratio"] = round(students / lecturers, 1) if lecturers else None
    report["by_level"] = list(db.session.execute(
        students_q(StudentProfile.level, func.count(StudentProfile.id))
        .group_by(StudentProfile.level).order_by(StudentProfile.level)))
    report["by_program"] = [(f"{p.degree} {p.name}", n) for p, n in db.session.execute(
        students_q(Program, func.count(StudentProfile.id)).join(StudentProfile.program)
        .group_by(Program.id).order_by(Program.name))]
    report["by_gender"] = [(g or "Not stated", n) for g, n in db.session.execute(
        students_q(StudentProfile.gender, func.count(StudentProfile.id)).group_by(StudentProfile.gender))]

    # ---- Standing across all semesters (CGPA) -------------------------------
    all_rows = db.session.execute(
        _limit(db.select(CourseRegistration.student_id, Course.units, ResultEntry.grade_point)
               .join(ResultEntry.registration).join(ResultEntry.sheet).join(CourseRegistration.course)
               .join(User, User.id == CourseRegistration.student_id)
               .where(ResultSheet.status == ResultStatus.APPROVED, User.status == AccountStatus.ACTIVE),
               User.department_id, department_ids))
    cgpas = _gpa_by_student(all_rows)
    report["cgpa_bands"] = [(label, sum(1 for g in cgpas.values() if _band(g) == label)) for _, label in GPA_BANDS]
    report["average_cgpa"] = round(sum(cgpas.values()) / len(cgpas), 2) if cgpas else None
    at_risk_ids = [sid for sid, g in cgpas.items() if g < AT_RISK_CGPA]
    at_risk_users = db.session.scalars(db.select(User).where(User.id.in_(at_risk_ids))
                                       .options(joinedload(User.student_profile))) if at_risk_ids else []
    report["at_risk"] = sorted([(u, cgpas[u.id]) for u in at_risk_users], key=lambda pair: pair[1])

    report.update(registered_students=0, registrations=0, registered_units=0, registration_rate=None,
                  average_load=None, offered=0, allocated=0, coverage=None, sheet_status={}, sheets=0,
                  completion=None, corrections_pending=0, average_score=None, pass_rate=None, grades={},
                  best=[], weakest=[], average_gpa=None, gpa_bands=[], workload=[], new_intake=0)
    if semester is None:
        return report

    # ---- Intake ---------------------------------------------------------------
    report["new_intake"] = _count(students_q(func.count(StudentProfile.id))
                                  .where(StudentProfile.entry_year == int(semester.session.name[:4])))

    # ---- Courses and allocation ----------------------------------------------
    offered_q = _limit(db.select(Course).where(Course.is_active.is_(True), Course.semester_term == semester.term),
                       Course.department_id, department_ids)
    offered = list(db.session.scalars(offered_q))
    allocations = {a.course_id: a for a in db.session.scalars(
        db.select(CourseAllocation).filter_by(semester_id=semester.id).options(joinedload(CourseAllocation.course)))}
    report["offered"] = len(offered)
    report["allocated"] = sum(1 for c in offered if c.id in allocations)
    report["coverage"] = _pct(report["allocated"], report["offered"])

    # ---- Registration (by the STUDENT's department) --------------------------
    reg_q = _limit(db.select(CourseRegistration.student_id, Course.units)
                   .join(CourseRegistration.course).join(User, User.id == CourseRegistration.student_id)
                   .where(CourseRegistration.semester_id == semester.id), User.department_id, department_ids)
    reg_rows = list(db.session.execute(reg_q))
    registered = {sid for sid, _ in reg_rows}
    report["registered_students"] = len(registered)
    report["registrations"] = len(reg_rows)
    report["registered_units"] = sum(units for _, units in reg_rows)
    report["registration_rate"] = _pct(len(registered), students)
    report["average_load"] = round(report["registered_units"] / len(registered), 1) if registered else None

    # ---- Result sheets (by the COURSE's department) --------------------------
    sheet_q = _limit(db.select(ResultSheet).join(ResultSheet.course).where(ResultSheet.semester_id == semester.id),
                     Course.department_id, department_ids)
    sheets = list(db.session.scalars(sheet_q))
    status_counts: dict[str, int] = {}
    for sheet in sheets:
        status_counts[sheet.status] = status_counts.get(sheet.status, 0) + 1
    report["sheets"] = len(sheets)
    report["sheet_status"] = status_counts
    report["completion"] = _pct(status_counts.get(ResultStatus.APPROVED, 0), len(sheets))
    report["corrections_pending"] = sum(1 for s in sheets if s.correction_pending)

    # ---- Performance of approved results -------------------------------------
    performance = performance_report(department_ids, semester)
    approved = [e for row in performance for e in row["sheet"].entries if e.total is not None]
    report["average_score"] = round(sum(e.total for e in approved) / len(approved), 1) if approved else None
    report["pass_rate"] = _pct(sum(1 for e in approved if (e.grade_point or 0) > 0), len(approved))
    report["grades"] = grade_distribution(department_ids, semester)
    ranked = sorted([r for r in performance if r["average"] is not None], key=lambda r: r["average"], reverse=True)
    report["best"] = ranked[:3]
    report["weakest"] = ranked[::-1][:3] if len(ranked) > 3 else []

    # ---- Semester GPA of the department's students ---------------------------
    gpa_rows = db.session.execute(
        _limit(db.select(CourseRegistration.student_id, Course.units, ResultEntry.grade_point)
               .join(ResultEntry.registration).join(ResultEntry.sheet).join(CourseRegistration.course)
               .join(User, User.id == CourseRegistration.student_id)
               .where(ResultSheet.status == ResultStatus.APPROVED, CourseRegistration.semester_id == semester.id),
               User.department_id, department_ids))
    gpas = _gpa_by_student(gpa_rows)
    report["average_gpa"] = round(sum(gpas.values()) / len(gpas), 2) if gpas else None
    report["gpa_bands"] = [(label, sum(1 for g in gpas.values() if _band(g) == label)) for _, label in GPA_BANDS]

    # ---- Lecturer workload -----------------------------------------------------
    reg_counts = dict(db.session.execute(
        db.select(CourseRegistration.course_id, func.count(CourseRegistration.id))
        .where(CourseRegistration.semester_id == semester.id).group_by(CourseRegistration.course_id)).all())
    sheets_by_course = {s.course_id: s for s in sheets}
    lecturer_q = _limit(db.select(User).where(User.role == Role.LECTURER, User.status == AccountStatus.ACTIVE)
                        .options(joinedload(User.lecturer_profile)),
                        User.department_id, department_ids).order_by(User.last_name)
    workload = []
    for lecturer in db.session.scalars(lecturer_q):
        courses = [a.course for a in allocations.values() if a.lecturer_id == lecturer.id]
        workload.append({
            "lecturer": lecturer,
            "courses": courses,
            "students": sum(reg_counts.get(c.id, 0) for c in courses),
            "units": sum(c.units for c in courses),
            "statuses": [sheets_by_course[c.id].status if c.id in sheets_by_course else "draft" for c in courses],
        })
    report["workload"] = workload
    return report


def department_comparison(semester: Semester | None) -> list[dict]:
    """
    One summary row per department, for the Super Admin's overview.

    Same figures and formulas as department_report(), but computed for ALL
    departments at once with GROUP BY queries, so the page costs the same
    handful of database queries whether there are 3 departments or 60.
    """
    departments = list(db.session.scalars(db.select(Department).order_by(Department.name)))

    def per_department(query) -> dict:
        return {dept_id: n for dept_id, n in db.session.execute(query)}

    active = (User.status == AccountStatus.ACTIVE)
    students = per_department(db.select(User.department_id, func.count(StudentProfile.id))
                              .join(StudentProfile.user).where(active, User.role == Role.STUDENT)
                              .group_by(User.department_id))
    lecturers = per_department(db.select(User.department_id, func.count(User.id))
                               .where(active, User.role == Role.LECTURER).group_by(User.department_id))

    # CGPA over all approved results, by the student's department.
    def gpa_rows(*conditions):
        return db.session.execute(
            db.select(User.department_id, CourseRegistration.student_id, Course.units, ResultEntry.grade_point)
            .join(ResultEntry.registration).join(ResultEntry.sheet).join(CourseRegistration.course)
            .join(User, User.id == CourseRegistration.student_id)
            .where(ResultSheet.status == ResultStatus.APPROVED, *conditions))

    def gpas_by_department(rows) -> dict[int, list[float]]:
        split: dict[int, list] = {}
        for dept_id, student_id, units, point in rows:
            split.setdefault(dept_id, []).append((student_id, units, point))
        return {dept_id: list(_gpa_by_student(r).values()) for dept_id, r in split.items()}

    cgpas = gpas_by_department(gpa_rows(active))   # standing: current (active) students only

    registered, sheet_status, entries, gpas = {}, {}, {}, {}
    if semester is not None:
        registered = per_department(
            db.select(User.department_id, func.count(func.distinct(CourseRegistration.student_id)))
            .join(User, User.id == CourseRegistration.student_id)
            .where(CourseRegistration.semester_id == semester.id).group_by(User.department_id))
        for dept_id, status, n in db.session.execute(
                db.select(Course.department_id, ResultSheet.status, func.count(ResultSheet.id))
                .join(ResultSheet.course).where(ResultSheet.semester_id == semester.id)
                .group_by(Course.department_id, ResultSheet.status)):
            sheet_status.setdefault(dept_id, {})[status] = n
        # Approved scores by the COURSE's department: (scored entries, passed entries).
        for dept_id, scored, passed in db.session.execute(
                db.select(Course.department_id, func.count(ResultEntry.id),
                          func.count(ResultEntry.id).filter(ResultEntry.grade_point > 0))
                .join(ResultEntry.sheet).join(ResultSheet.course)
                .where(ResultSheet.semester_id == semester.id, ResultSheet.status == ResultStatus.APPROVED,
                       ResultEntry.total.is_not(None))
                .group_by(Course.department_id)):
            entries[dept_id] = (scored, passed)
        gpas = gpas_by_department(gpa_rows(CourseRegistration.semester_id == semester.id))

    rows = []
    for department in departments:
        d = department.id
        statuses = sheet_status.get(d, {})
        scored, passed = entries.get(d, (0, 0))
        semester_gpas = gpas.get(d, [])
        rows.append({
            "department": department,
            "students": students.get(d, 0),
            "lecturers": lecturers.get(d, 0),
            "registration_rate": _pct(registered.get(d, 0), students.get(d, 0)) if semester else None,
            "completion": _pct(statuses.get(ResultStatus.APPROVED, 0), sum(statuses.values())) if semester else None,
            "pass_rate": _pct(passed, scored) if semester else None,
            "average_gpa": round(sum(semester_gpas) / len(semester_gpas), 2) if semester_gpas else None,
            "at_risk": sum(1 for g in cgpas.get(d, []) if g < AT_RISK_CGPA),
        })
    return rows
