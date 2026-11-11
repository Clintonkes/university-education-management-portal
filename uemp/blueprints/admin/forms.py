"""
Admin forms (used by Department Admins and the Super Admin).

Drop-down choices (departments, programmes, lecturers...) are filled in by the
route at request time, because they depend on WHO is logged in: a department
admin only sees their own department's options.
"""

from datetime import date

from flask_wtf import FlaskForm
from wtforms import (
    BooleanField, EmailField, IntegerField, PasswordField, SelectField, SelectMultipleField,
    StringField, SubmitField, TextAreaField,
)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional, Regexp

from ...models import SemesterTerm

PHONE = Regexp(r"^\+?[0-9 ]{7,20}$", message="Enter a valid phone number.")
CODE = Regexp(r"^[A-Za-z0-9 /\-]+$", message="Use letters, numbers, spaces, '/' or '-' only.")
TITLES = [("", "—"), ("Mr.", "Mr."), ("Mrs.", "Mrs."), ("Ms.", "Ms."), ("Dr.", "Dr."), ("Prof.", "Prof."), ("Engr.", "Engr.")]
GENDERS = [("", "—"), ("Male", "Male"), ("Female", "Female")]


class _PersonFields(FlaskForm):
    """Fields shared by every type of person."""

    first_name = StringField("First name", validators=[DataRequired(), Length(max=60)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=60)])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    phone = StringField("Phone", validators=[Optional(), PHONE])
    password = PasswordField(
        "Initial password", validators=[Optional(), Length(min=8, max=128)],
        description="At least 8 characters with letters and numbers. The user should change it after first login.",
    )


class StudentForm(_PersonFields):
    matric_number = StringField("Matric number", validators=[DataRequired(), Length(max=30), CODE])
    program_id = SelectField("Programme", coerce=int, validators=[DataRequired()])
    level = SelectField("Level", coerce=int, validators=[DataRequired()])
    entry_year = IntegerField("Year of entry", default=date.today().year,
                              validators=[DataRequired(), NumberRange(min=1990, max=2100)])
    gender = SelectField("Gender", choices=GENDERS, validators=[Optional()])
    submit = SubmitField("Save student")


class LecturerForm(_PersonFields):
    title = SelectField("Title", choices=TITLES, validators=[Optional()])
    staff_id = StringField("Staff ID", validators=[DataRequired(), Length(max=30), CODE])
    department_id = SelectField("Department", coerce=int, validators=[DataRequired()])
    rank = StringField("Rank", validators=[Optional(), Length(max=60)],
                       description="e.g. Lecturer II, Senior Lecturer, Professor")
    specialization = StringField("Specialisation", validators=[Optional(), Length(max=120)])
    submit = SubmitField("Save lecturer")


class ProgramForm(FlaskForm):
    name = StringField("Programme name", validators=[DataRequired(), Length(max=150)],
                       description="e.g. Computer Science")
    code = StringField("Code", validators=[DataRequired(), Length(max=20), CODE])
    degree = StringField("Degree awarded", default="B.Sc.", validators=[DataRequired(), Length(max=20)])
    duration_years = IntegerField("Duration (years)", default=4, validators=[DataRequired(), NumberRange(1, 7)])
    department_id = SelectField("Department", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Save programme")


class CourseForm(FlaskForm):
    code = StringField("Course code", validators=[DataRequired(), Length(max=15), CODE],
                       description="e.g. CSC 201")
    title = StringField("Course title", validators=[DataRequired(), Length(max=150)])
    units = IntegerField("Credit units", default=3, validators=[DataRequired(), NumberRange(1, 6)])
    level = SelectField("Level", coerce=int, validators=[DataRequired()])
    semester_term = SelectField("Semester", choices=[(t.value, t.label) for t in SemesterTerm])
    department_id = SelectField("Owning department", coerce=int, validators=[DataRequired()])
    program_ids = SelectMultipleField("Offered to programmes", coerce=int, validators=[DataRequired()],
                                      description="Hold Ctrl (Cmd on Mac) to select more than one.")
    description = TextAreaField("Description", validators=[Optional(), Length(max=2000)])
    is_active = BooleanField("Active (students can register it)", default=True)
    submit = SubmitField("Save course")


class AllocationForm(FlaskForm):
    course_id = SelectField("Course", coerce=int, validators=[DataRequired()])
    lecturer_id = SelectField("Lecturer", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Assign lecturer")


class ReviewForm(FlaskForm):
    comment = TextAreaField("Comment / feedback for the lecturer", validators=[Optional(), Length(max=2000)])


class PasswordResetForm(FlaskForm):
    new_password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)])
    submit = SubmitField("Reset password")


class RegistrationEditForm(FlaskForm):
    """Super Admin correction of one course registration."""
    course_id = SelectField("Course", coerce=int, validators=[DataRequired()],
                            description="Only courses for this registration's semester are listed.")
    registration_type = SelectField("Registration type", description="Carry-over = repeating a course failed before.")
    remarks = TextAreaField("Remarks", validators=[Optional(), Length(max=500)],
                            description="Optional note, e.g. 'Approved late registration'.")
    submit = SubmitField("Save changes")
