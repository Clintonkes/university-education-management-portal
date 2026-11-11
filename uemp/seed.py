"""
seed.py — Demo data so evaluators can test every workflow without typing.

WHAT GETS CREATED
    * 3 faculties, 4 departments, 4 programmes
    * Sessions 2025/2026 (finished) and 2026/2027 (current = First Semester,
      registration OPEN)
    * 1 Super Admin, 2 Department Admins, 5 Lecturers, 24 Students
    * Courses for 100 and 200 Level
    * 2025/2026 results for the 200 Level students — APPROVED, so CGPA shows
    * 2026/2027 First Semester:
        - CSC 201 (Dr. Okafor): students registered, sheet in DRAFT
                                -> log in as the lecturer and submit it
        - CSC 203 (Prof. Bakare): scores SUBMITTED, waiting for review
                                -> log in as the CSC department admin and approve
        - student@uemp.edu.ng has NOT registered yet
                                -> log in as the student and register

All demo passwords are listed in DEMO_ACCOUNTS (and in the README).
Random scores use a fixed seed so the data is the same every time.
"""

import random
from datetime import date, datetime

from .extensions import db
from .models import (
    AcademicSession, AccountStatus, AuditLog, Course, CourseAllocation, CourseRegistration, Department,
    Faculty, LecturerProfile, Program, ResultEntry, ResultSheet, ResultStatus, Role, Semester,
    SemesterTerm, StudentProfile, User,
)
from .services.grading import grade_for

# (email, password, role) — printed in the README for evaluators.
DEMO_ACCOUNTS = [
    ("admin@uemp.edu.ng", "Admin@1234", Role.SUPER_ADMIN),
    ("csc.admin@uemp.edu.ng", "Admin@1234", Role.DEPT_ADMIN),
    ("eco.admin@uemp.edu.ng", "Admin@1234", Role.DEPT_ADMIN),
    ("lecturer@uemp.edu.ng", "Lecturer@1234", Role.LECTURER),
    ("student@uemp.edu.ng", "Student@1234", Role.STUDENT),
]

FIRST_NAMES = ["Chinedu", "Aisha", "Tunde", "Ngozi", "Emeka", "Fatima", "Segun", "Amaka", "Ibrahim", "Kemi",
               "Obinna", "Zainab", "Femi", "Chioma", "Yusuf", "Bisi", "Uche", "Hauwa", "Dayo", "Ifeoma"]
LAST_NAMES = ["Okeke", "Bello", "Adeyemi", "Eze", "Nwosu", "Abubakar", "Ogunleye", "Obi", "Musa", "Adebayo",
              "Okafor", "Lawal", "Balogun", "Nnamdi", "Sani", "Ajayi", "Chukwu", "Garba", "Olawale", "Umeh"]


def _user(email, password, first, last, role, department=None, phone=None) -> User:
    user = User(email=email, first_name=first, last_name=last, role=role, status=AccountStatus.ACTIVE,
                department=department, phone=phone)
    user.set_password(password)
    db.session.add(user)
    return user


def _lecturer(email, first, last, title, staff_id, rank, department, password="Lecturer@1234") -> User:
    user = _user(email, password, first, last, Role.LECTURER, department)
    user.lecturer_profile = LecturerProfile(staff_id=staff_id, title=title, rank=rank)
    return user


def _student(email, first, last, matric, program, level, entry_year, password="Student@1234") -> User:
    user = _user(email, password, first, last, Role.STUDENT, program.department,
                 phone=f"080{random.randint(10000000, 99999999)}")
    user.student_profile = StudentProfile(matric_number=matric, program=program, level=level,
                                          entry_year=entry_year, gender=random.choice(["Male", "Female"]))
    return user


def _course(code, title, units, level, term, department, programs) -> Course:
    course = Course(code=code, title=title, units=units, level=level, semester_term=term,
                    department=department, programs=programs)
    db.session.add(course)
    return course


def _score_sheet(course, semester, lecturer, students, status, rng, reviewer=None):
    """Register students for a course and (optionally) fill in their scores."""
    sheet = ResultSheet(course=course, semester=semester, lecturer=lecturer, status=status)
    db.session.add(sheet)
    for student in students:
        registration = CourseRegistration(student=student, course=course, semester=semester)
        db.session.add(registration)
        entry = ResultEntry(sheet=sheet, registration=registration)
        if status != ResultStatus.DRAFT:
            entry.ca_score = float(rng.randint(15, 38))
            entry.exam_score = float(rng.randint(18, 58))
            entry.total = entry.ca_score + entry.exam_score
            entry.grade, entry.grade_point = grade_for(entry.total)
        db.session.add(entry)
    db.session.flush()  # gives the sheet an ID for the audit entries below
    if status in (ResultStatus.SUBMITTED, ResultStatus.APPROVED):
        sheet.submitted_at = datetime(2026, 10, 30, 10, 0) if status == ResultStatus.SUBMITTED else datetime(2026, 7, 10, 9, 0)
        _audit(lecturer, "result.submitted", f"Submitted {course.code} results ({len(students)} students) "
               f"for {semester.term_label} {semester.session.name}", sheet, sheet.submitted_at)
    if status == ResultStatus.APPROVED:
        sheet.reviewed_by, sheet.reviewed_at = reviewer, datetime(2026, 7, 15, 12, 0)
        _audit(reviewer, "result.approved", f"Approved {course.code} results for "
               f"{semester.term_label} {semester.session.name}", sheet, sheet.reviewed_at)
    return sheet


def _audit(actor, action, description, entity, when):
    """Write a back-dated audit entry so the demo history looks realistic."""
    db.session.add(AuditLog(actor=actor, actor_name=actor.display_name, actor_role=actor.role, action=action,
                            description=description, entity_type=type(entity).__name__,
                            entity_id=entity.id, created_at=when, ip_address="seed"))


def seed_demo_data() -> bool:
    """Insert demo records. Returns False (and does nothing) if users already exist."""
    if db.session.scalar(db.select(User).limit(1)):
        return False
    random.seed(7)
    rng = random.Random(42)

    # ---- Structure -------------------------------------------------------
    sci = Faculty(name="Faculty of Science", code="SCI")
    eng = Faculty(name="Faculty of Engineering", code="ENG")
    ssc = Faculty(name="Faculty of Social Sciences", code="SSC")
    csc = Department(name="Computer Science", code="CSC", faculty=sci)
    mth = Department(name="Mathematics", code="MTH", faculty=sci)
    eee = Department(name="Electrical Engineering", code="EEE", faculty=eng)
    eco = Department(name="Economics", code="ECO", faculty=ssc)
    db.session.add_all([sci, eng, ssc, csc, mth, eee, eco])

    p_csc = Program(name="Computer Science", code="BSC-CSC", degree="B.Sc.", duration_years=4, department=csc)
    p_mth = Program(name="Mathematics", code="BSC-MTH", degree="B.Sc.", duration_years=4, department=mth)
    p_eee = Program(name="Electrical Engineering", code="BENG-EEE", degree="B.Eng.", duration_years=5, department=eee)
    p_eco = Program(name="Economics", code="BSC-ECO", degree="B.Sc.", duration_years=4, department=eco)
    db.session.add_all([p_csc, p_mth, p_eee, p_eco])

    # ---- Calendar ----------------------------------------------------------
    s_prev = AcademicSession(name="2025/2026", start_date=date(2025, 10, 1), end_date=date(2026, 8, 31))
    s_prev.semesters = [Semester(term=SemesterTerm.FIRST), Semester(term=SemesterTerm.SECOND)]
    s_now = AcademicSession(name="2026/2027", start_date=date(2026, 10, 1), end_date=date(2027, 8, 31), is_current=True)
    s_now.semesters = [Semester(term=SemesterTerm.FIRST, is_current=True, registration_open=True),
                       Semester(term=SemesterTerm.SECOND)]
    db.session.add_all([s_prev, s_now])
    prev_first, prev_second = s_prev.semesters
    now_first = s_now.semesters[0]

    # ---- Staff -------------------------------------------------------------
    _user("admin@uemp.edu.ng", "Admin@1234", "Grace", "Adewale", Role.SUPER_ADMIN)
    csc_admin = _user("csc.admin@uemp.edu.ng", "Admin@1234", "Samuel", "Ogbu", Role.DEPT_ADMIN, csc)
    _user("eco.admin@uemp.edu.ng", "Admin@1234", "Halima", "Yusuf", Role.DEPT_ADMIN, eco)

    okafor = _lecturer("lecturer@uemp.edu.ng", "Adaeze", "Okafor", "Dr.", "STF/CSC/001", "Senior Lecturer", csc)
    bakare = _lecturer("bakare@uemp.edu.ng", "Tunde", "Bakare", "Prof.", "STF/CSC/002", "Professor", csc)
    musa = _lecturer("musa@uemp.edu.ng", "Ibrahim", "Musa", "Mr.", "STF/CSC/003", "Lecturer II", csc)
    eze = _lecturer("eze@uemp.edu.ng", "Ngozi", "Eze", "Dr.", "STF/MTH/001", "Lecturer I", mth)
    _lecturer("adeyemi@uemp.edu.ng", "Femi", "Adeyemi", "Dr.", "STF/ECO/001", "Senior Lecturer", eco)

    # ---- Courses -----------------------------------------------------------
    F, S = SemesterTerm.FIRST, SemesterTerm.SECOND
    csc101 = _course("CSC 101", "Introduction to Computer Science", 3, 100, F, csc, [p_csc])
    mth101 = _course("MTH 101", "Elementary Mathematics I", 3, 100, F, mth, [p_csc, p_mth])
    gst101 = _course("GST 101", "Use of English I", 2, 100, F, csc, [p_csc])
    csc102 = _course("CSC 102", "Introduction to Programming", 3, 100, S, csc, [p_csc])
    mth102 = _course("MTH 102", "Elementary Mathematics II", 3, 100, S, mth, [p_csc, p_mth])
    csc201 = _course("CSC 201", "Data Structures and Algorithms", 3, 200, F, csc, [p_csc])
    csc203 = _course("CSC 203", "Discrete Structures", 3, 200, F, csc, [p_csc])
    csc205 = _course("CSC 205", "Computer Architecture", 2, 200, F, csc, [p_csc])
    mth201 = _course("MTH 201", "Mathematical Methods I", 3, 200, F, mth, [p_csc, p_mth])
    _course("CSC 202", "Object-Oriented Programming", 3, 200, S, csc, [p_csc])
    _course("CSC 204", "Operating Systems I", 3, 200, S, csc, [p_csc])
    _course("ECO 101", "Principles of Economics I", 3, 100, F, eco, [p_eco])
    _course("ECO 201", "Intermediate Microeconomics", 3, 200, F, eco, [p_eco])

    # ---- Students ----------------------------------------------------------
    demo = _student("student@uemp.edu.ng", "Chinedu", "Okeke", "CSC/2025/001", p_csc, 200, 2025)
    cohort_200 = [demo]
    for i in range(2, 13):
        first, last = FIRST_NAMES[i % 20], LAST_NAMES[(i * 3) % 20]
        cohort_200.append(_student(f"csc25{i:03d}@uemp.edu.ng", first, last, f"CSC/2025/{i:03d}", p_csc, 200, 2025))
    for i in range(1, 7):
        first, last = FIRST_NAMES[(i + 7) % 20], LAST_NAMES[(i * 7) % 20]
        _student(f"csc26{i:03d}@uemp.edu.ng", first, last, f"CSC/2026/{i:03d}", p_csc, 100, 2026)
    for i in range(1, 7):
        first, last = FIRST_NAMES[(i + 11) % 20], LAST_NAMES[(i * 9) % 20]
        _student(f"eco26{i:03d}@uemp.edu.ng", first, last, f"ECO/2026/{i:03d}", p_eco, 100, 2026)
    db.session.flush()

    # ---- Last session: approved 100 Level results (gives every 200L student a CGPA)
    for course, semester, lecturer in [(csc101, prev_first, okafor), (mth101, prev_first, eze),
                                       (gst101, prev_first, musa), (csc102, prev_second, bakare),
                                       (mth102, prev_second, eze)]:
        db.session.add(CourseAllocation(course=course, semester=semester, lecturer=lecturer))
        _score_sheet(course, semester, lecturer, cohort_200, ResultStatus.APPROVED, rng, reviewer=csc_admin)

    # ---- This semester -------------------------------------------------------
    for course, lecturer in [(csc201, okafor), (csc203, bakare), (csc205, musa), (mth201, eze)]:
        db.session.add(CourseAllocation(course=course, semester=now_first, lecturer=lecturer))
    registered_now = cohort_200[1:]  # everyone except the demo student
    _score_sheet(csc201, now_first, okafor, registered_now, ResultStatus.DRAFT, rng)       # lecturer to submit
    _score_sheet(csc203, now_first, bakare, registered_now, ResultStatus.SUBMITTED, rng)   # admin to approve
    for student in registered_now:
        db.session.add(CourseRegistration(student=student, course=mth201, semester=now_first))

    db.session.commit()
    return True
