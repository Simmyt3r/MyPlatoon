"""Jobs & Gigs input validation and anti-scam registration safeguards."""
from datetime import date

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, TextAreaField, IntegerField,
    DateField, BooleanField, SubmitField,
)
from wtforms.validators import (
    DataRequired, Email, EqualTo, Length, Optional, NumberRange, Regexp,
    ValidationError,
)

from app.models import User, EMPLOYER_KINDS, JOB_KINDS, WORK_MODES, PAY_UNITS
from app.models.platoon import NYSC_STATES

STATES = [("", "Choose a Nigerian state")] + [(s, s) for s in NYSC_STATES]


class EmployerFieldsForm(FlaskForm):
    name = StringField("Organisation / School Name",
        validators=[DataRequired(), Length(min=3, max=160)])
    kind = SelectField("Organisation Type", choices=EMPLOYER_KINDS,
        validators=[DataRequired()])
    state = SelectField("State", choices=STATES, validators=[DataRequired()])
    lga = StringField("LGA", validators=[DataRequired(), Length(min=2, max=100)])
    address = StringField("Public office or school address",
        validators=[DataRequired(), Length(min=5, max=255)])
    description = TextAreaField("What does your organisation do?",
        validators=[DataRequired(), Length(min=25, max=1200)])
    contact_email = StringField("Official recruiting email",
        validators=[DataRequired(), Email(), Length(max=255)])
    contact_phone = StringField("Recruiting phone (optional)",
        validators=[Optional(), Length(max=30)])
    website = StringField("Website (optional)",
        validators=[Optional(), Length(max=255),
                    Regexp(r"^https?://", message="Use a full https:// or http:// URL.")])


class EmployerRegistrationForm(EmployerFieldsForm):
    full_name = StringField("Contact Person's Full Name",
        validators=[DataRequired(), Length(min=2, max=120)])
    email = StringField("Account Email",
        validators=[DataRequired(), Email(), Length(max=255)])
    password = PasswordField("Password", validators=[
        DataRequired(), Length(min=8, max=100)])
    confirm_password = PasswordField("Confirm Password", validators=[
        DataRequired(), EqualTo("password")])
    submit = SubmitField("Register Organisation")

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.strip().lower()).first():
            raise ValidationError("That email is already registered. Sign in instead.")

    def validate_password(self, field):
        password = field.data or ""
        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            raise ValidationError("Use at least one letter and one number.")


class EmployerEditForm(EmployerFieldsForm):
    submit = SubmitField("Save organisation details")


class JobForm(FlaskForm):
    title = StringField("Job title", validators=[DataRequired(), Length(min=5, max=160)])
    job_kind = SelectField("Opportunity type", choices=JOB_KINDS,
        validators=[DataRequired()])
    work_mode = SelectField("Work arrangement", choices=WORK_MODES,
        validators=[DataRequired()])
    state = SelectField("Work state (or employer base for remote roles)",
        choices=STATES, validators=[DataRequired()])
    lga = StringField("LGA (optional for remote)",
        validators=[Optional(), Length(max=100)])
    location_description = StringField("General work location / landmark",
        validators=[Optional(), Length(max=255)])
    description = TextAreaField("Responsibilities", validators=[
        DataRequired(), Length(min=40, max=6000)])
    requirements = TextAreaField("Requirements and qualifications", validators=[
        DataRequired(), Length(min=15, max=4000)])
    hours_per_week = IntegerField("Estimated hours per week",
        validators=[Optional(), NumberRange(min=1, max=84)])
    schedule_notes = StringField("Schedule / shift details",
        validators=[Optional(), Length(max=240)])
    pay_min = IntegerField("Minimum pay (₦)",
        validators=[DataRequired(), NumberRange(min=1, max=1000000000)])
    pay_max = IntegerField("Maximum pay (₦)",
        validators=[DataRequired(), NumberRange(min=1, max=1000000000)])
    pay_unit = SelectField("Payment basis", choices=PAY_UNITS,
        validators=[DataRequired()])
    closing_date = DateField("Application deadline", format="%Y-%m-%d",
        validators=[DataRequired()])
    serving_only = BooleanField("For currently serving NYSC members only")
    submit = SubmitField("Submit listing for review")

    def validate_pay_max(self, field):
        if self.pay_min.data is not None and field.data is not None:
            if field.data < self.pay_min.data:
                raise ValidationError("Maximum pay must be at least minimum pay.")

    def validate_closing_date(self, field):
        if field.data and field.data < date.today():
            raise ValidationError("The deadline cannot be in the past.")


class JobApplicationForm(FlaskForm):
    cover_note = TextAreaField("Why are you a good fit?",
        validators=[DataRequired(), Length(min=30, max=1500)])
    contact_email = StringField("Email to share with this employer",
        validators=[DataRequired(), Email(), Length(max=255)])
    contact_phone = StringField("Optional phone to share",
        validators=[Optional(), Length(max=30)])
    consent = BooleanField(
        "I agree to share the details above with this employer for this specific job.",
        validators=[DataRequired(message="Consent is required to submit the application.")])
    submit = SubmitField("Send application")


class JobReviewForm(FlaskForm):
    decision = SelectField("Decision", choices=[
        ("approved", "Approve"), ("rejected", "Reject"),
    ], validators=[DataRequired()])
    note = TextAreaField("Reason / internal moderation notes",
        validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save review")



class JobReportForm(FlaskForm):
    reason = TextAreaField("Why is this opportunity concerning?",
        validators=[DataRequired(), Length(min=15, max=500)],
        description="Examples: recruiting fee, identity-document demand, misleading pay, harassment or suspicious address. Your identity is visible only to moderators.")
    submit = SubmitField("Submit confidential report")
