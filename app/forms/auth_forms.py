from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField, IntegerField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.models import User
from app.models.platoon import SERVICE_STAGES, NYSC_STATES
from app.services.platoon_membership import validate_platoon_fields


class RegistrationForm(FlaskForm):
    full_name = StringField("Full Name", validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[
        DataRequired(),
        Length(min=8, message="Password must be at least 8 characters long."),
    ])
    confirm_password = PasswordField("Confirm Password", validators=[
        DataRequired(),
        EqualTo("password", message="Passwords must match."),
    ])
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower().strip()).first():
            raise ValidationError("An account with this email already exists.")

    def validate_password(self, field):
        pw = field.data
        if not any(c.isdigit() for c in pw) or not any(c.isalpha() for c in pw):
            raise ValidationError("Password must contain both letters and numbers.")


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Email()])
    password = PasswordField("Password", validators=[DataRequired()])
    remember_me = BooleanField("Keep me signed in", default=True)
    submit = SubmitField("Log In")
