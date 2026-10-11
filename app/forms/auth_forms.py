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
    service_stage = SelectField("NYSC Journey", choices=SERVICE_STAGES,
                                default="pcm")
    nysc_state = SelectField("Orientation Camp State",
                             choices=[("", "Choose your camp state")] + [(s, s) for s in NYSC_STATES],
                             default="")
    service_year = IntegerField("Year of Orientation Camp")
    nysc_batch = SelectField("NYSC Batch", choices=[("", "Select batch"), ("A", "Batch A"), ("B", "Batch B"), ("C", "Batch C")], default="")
    nysc_stream = SelectField("NYSC Stream", choices=[("", "Select stream"), ("I", "Stream I"), ("II", "Stream II")], default="")
    platoon_number = IntegerField("Platoon Number (assigned at camp)")
    submit = SubmitField("Create Account")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        return validate_platoon_fields(self) and valid

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
