"""Grading scale, GPA and CGPA calculations."""

import pytest

from uemp.services.grading import academic_history, calculate_gpa, degree_class, grade_for

from .conftest import user


@pytest.mark.parametrize("total, grade, point", [
    (100, "A", 5.0), (70, "A", 5.0), (69.9, "B", 4.0), (60, "B", 4.0), (59, "C", 3.0),
    (50, "C", 3.0), (49, "D", 2.0), (45, "D", 2.0), (44, "E", 1.0), (40, "E", 1.0), (39.5, "F", 0.0), (0, "F", 0.0),
])
def test_grade_boundaries(app, total, grade, point):
    assert grade_for(total) == (grade, point)


def test_gpa_is_credit_unit_weighted():
    # Example from the docs: 3 units of A (5) + 2 units of C (3) = 21 / 5 = 4.20
    assert calculate_gpa([(3, 5.0), (2, 3.0)]) == 4.2


def test_gpa_with_no_courses_is_zero():
    assert calculate_gpa([]) == 0.0


def test_degree_class():
    assert degree_class(4.6) == "First Class"
    assert degree_class(3.6) == "Second Class Upper"
    assert degree_class(2.5) == "Second Class Lower"
    assert degree_class(0.5) == "—"


def test_history_counts_only_approved_results(app):
    # The demo student has 2 approved semesters last session, while this
    # semester's CSC 203 sheet is only SUBMITTED for other students.
    history = academic_history(user("csc25002@uemp.edu.ng").id)
    assert len(history.semesters) == 2
    assert all(e.sheet.status == "approved" for e in history.all_entries)
    assert 0 < history.cgpa <= 5
