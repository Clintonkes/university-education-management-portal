"""Super Admin forms."""

from flask_wtf import FlaskForm
from wtforms import DateField, EmailField, PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, Length, Optional, Regexp

from ...models import Role

CODE = Regexp(r"^[A-Za-z0-9]+$", message="Use letters and numbers only (no spaces).")


class FacultyForm(FlaskForm):
    name = StringField("Faculty name", validators=[DataRequired(), Length(max=120)],
                       description="e.g. Faculty of Science")
    code = StringField("Short code", validators=[DataRequired(), Length(max=12), CODE], description="e.g. SCI")
    submit = SubmitField("Save faculty")


class DepartmentForm(FlaskForm):
    name = StringField("Department name", validators=[DataRequired(), Length(max=120)])
    code = StringField("Short code", validators=[DataRequired(), Length(max=12), CODE], description="e.g. CSC")
    faculty_id = SelectField("Faculty", coerce=int, validators=[DataRequired()])
    submit = SubmitField("Save department")


class SessionForm(FlaskForm):
    name = StringField("Session", validators=[DataRequired(), Length(max=20)], description="Format: 2026/2027")
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    submit = SubmitField("Create session")


class SemesterForm(FlaskForm):
    start_date = DateField("Start date", validators=[Optional()])
    end_date = DateField("End date", validators=[Optional()])
    submit = SubmitField("Save dates")


class AdminUserForm(FlaskForm):
    role = SelectField("Role", choices=[(Role.DEPT_ADMIN.value, Role.DEPT_ADMIN.label),
                                        (Role.SUPER_ADMIN.value, Role.SUPER_ADMIN.label)])
    first_name = StringField("First name", validators=[DataRequired(), Length(max=60)])
    last_name = StringField("Last name", validators=[DataRequired(), Length(max=60)])
    email = EmailField("Email", validators=[DataRequired(), Email(), Length(max=150)])
    department_id = SelectField("Department", coerce=int, validators=[Optional()],
                                description="Required for Department Admins.")
    password = PasswordField("Initial password", validators=[DataRequired(), Length(min=8, max=128)])
    submit = SubmitField("Create account")


class RoleForm(FlaskForm):
    role = SelectField("New role", choices=[(r.value, r.label) for r in (Role.LECTURER, Role.DEPT_ADMIN, Role.SUPER_ADMIN)])
    department_id = SelectField("Department", coerce=int, validators=[Optional()])
    submit = SubmitField("Change role")
