"""
Student forms.

Students may only edit "permitted" personal details. Name, matric number,
programme and level are official records — only admins can change those, so
they are simply NOT fields on this form (the server never reads them).
"""

from flask_wtf import FlaskForm
from wtforms import DateField, SelectField, StringField, SubmitField
from wtforms.validators import Length, Optional, Regexp

PHONE = Regexp(r"^\+?[0-9 ]{7,20}$", message="Enter a valid phone number.")


class StudentProfileForm(FlaskForm):
    phone = StringField("Phone number", validators=[Optional(), PHONE])
    address = StringField("Home address", validators=[Optional(), Length(max=255)])
    date_of_birth = DateField("Date of birth", validators=[Optional()])
    gender = SelectField("Gender", choices=[("", "Prefer not to say"), ("Male", "Male"), ("Female", "Female")],
                         validators=[Optional()])
    next_of_kin = StringField("Next of kin", validators=[Optional(), Length(max=120)])
    next_of_kin_phone = StringField("Next of kin phone", validators=[Optional(), PHONE])
    submit = SubmitField("Save changes")
