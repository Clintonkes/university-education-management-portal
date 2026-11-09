"""
grading.py — Turning scores into grades, GPA and CGPA.

GRADING SCALE (set in config.py → GRADING_SCALE)
    Total score   Grade   Grade point
    70 – 100        A         5
    60 – 69         B         4
    50 – 59         C         3
    45 – 49         D         2
    40 – 44         E         1
     0 – 39         F         0

GPA FORMULA (credit-unit weighted)
                 sum( course units × grade point )
        GPA  =  ---------------------------------
                      sum( course units )

    Example: CSC 201 (3 units, A=5) and MTH 201 (2 units, C=3)
             GPA = (3×5 + 2×3) / (3+2) = 21 / 5 = 4.20

    GPA  uses one semester's approved results.
    CGPA uses ALL approved results across every semester.

Only APPROVED results are ever counted — draft or pending scores never affect
a student's GPA.
"""

from collections import OrderedDict
from dataclasses import dataclass, field

from flask import current_app

from ..extensions import db
from ..models import CourseRegistration, ResultEntry, ResultSheet, ResultStatus, Semester, AcademicSession


def grading_scale() -> list[tuple[float, str, float]]:
    """The scale from config, highest band first."""
    return sorted(current_app.config["GRADING_SCALE"], key=lambda row: row[0], reverse=True)


def grade_for(total: float) -> tuple[str, float]:
    """Return (grade letter, grade point) for a total score, e.g. 72 -> ("A", 5.0)."""
    for minimum, grade, point in grading_scale():
        if total >= minimum:
            return grade, point
    return "F", 0.0


def pass_mark() -> float:
    """Lowest total that is not an F."""
    passing = [minimum for minimum, _grade, point in grading_scale() if point > 0]
    return min(passing) if passing else 0


def calculate_gpa(items: list[tuple[int, float]]) -> float:
    """
    Credit-unit weighted average.
    `items` is a list of (units, grade_point). Returns 0.0 if there is nothing to count.
    """
    total_units = sum(units for units, _ in items)
    if total_units == 0:
        return 0.0
    weighted = sum(units * point for units, point in items)
    return round(weighted / total_units, 2)


def degree_class(cgpa: float) -> str:
    """Standard 5-point classification, shown on the student's history page."""
    if cgpa >= 4.5:
        return "First Class"
    if cgpa >= 3.5:
        return "Second Class Upper"
    if cgpa >= 2.4:
        return "Second Class Lower"
    if cgpa >= 1.5:
        return "Third Class"
    if cgpa >= 1.0:
        return "Pass"
    return "—"


@dataclass
class SemesterRecord:
    """One semester's approved results for a student, ready to display."""

    semester: Semester
    entries: list[ResultEntry] = field(default_factory=list)

    @property
    def total_units(self) -> int:
        return sum(e.registration.course.units for e in self.entries)

    @property
    def units_passed(self) -> int:
        return sum(e.registration.course.units for e in self.entries if (e.grade_point or 0) > 0)

    @property
    def quality_points(self) -> float:
        return sum(e.registration.course.units * (e.grade_point or 0) for e in self.entries)

    @property
    def gpa(self) -> float:
        return calculate_gpa([(e.registration.course.units, e.grade_point or 0) for e in self.entries])


@dataclass
class AcademicHistory:
    semesters: list[SemesterRecord]

    @property
    def all_entries(self) -> list[ResultEntry]:
        return [e for record in self.semesters for e in record.entries]

    @property
    def total_units(self) -> int:
        return sum(r.total_units for r in self.semesters)

    @property
    def cgpa(self) -> float:
        return calculate_gpa([(e.registration.course.units, e.grade_point or 0) for e in self.all_entries])

    @property
    def classification(self) -> str:
        return degree_class(self.cgpa) if self.semesters else "—"


def approved_results_for(student_id: int) -> list[ResultEntry]:
    """All of a student's results whose sheet has been APPROVED, oldest first."""
    query = (
        db.select(ResultEntry)
        .join(ResultEntry.registration)
        .join(ResultEntry.sheet)
        .join(CourseRegistration.semester)
        .join(Semester.session)
        .where(CourseRegistration.student_id == student_id)
        .where(ResultSheet.status == ResultStatus.APPROVED)
        .order_by(AcademicSession.name, Semester.term)
    )
    return list(db.session.scalars(query))


def academic_history(student_id: int) -> AcademicHistory:
    """Group a student's approved results by semester and compute GPA/CGPA."""
    grouped: "OrderedDict[int, SemesterRecord]" = OrderedDict()
    for entry in approved_results_for(student_id):
        semester = entry.registration.semester
        grouped.setdefault(semester.id, SemesterRecord(semester=semester)).entries.append(entry)
    for record in grouped.values():
        record.entries.sort(key=lambda e: e.registration.course.code)
    return AcademicHistory(semesters=list(grouped.values()))
