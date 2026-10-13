"""Jobs & Gigs input validation and anti-scam registration safeguards."""
from datetime import date

from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, SelectField, SelectMultipleField, TextAreaField, IntegerField,
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



class JobPreferenceForm(FlaskForm):
    preferred_state = SelectField(
        "Preferred work state", choices=[("", "Use my NYSC posting state")] + STATES[1:],
        validators=[Optional()])
    preferred_kinds = SelectMultipleField(
        "Opportunity types", choices=JOB_KINDS,
        validators=[Optional()],
        description="Select more than one with Ctrl-click; leave blank to see all types.")
    available_hours = IntegerField(
        "Maximum hours available per week (optional)",
        validators=[Optional(), NumberRange(min=1, max=84)])
    remote_ok = BooleanField("Include remote opportunities", default=True)
    enabled = BooleanField(
        "Send me in-app alerts when a newly approved job matches these preferences",
        default=False)
    submit = SubmitField("Save discovery preferences")



class GigOwnerRegistrationForm(EmployerRegistrationForm):
    """Dedicated gig-owner onboarding with explicit safety agreement."""
    safety_agreement = BooleanField(
        "I will post genuine paid work, disclose the working conditions, and never charge applicants fees.",
        validators=[DataRequired(message="Accept the posting rules to continue.")])
    submit = SubmitField("Create my gig owner account")


class GigOwnerClaimForm(EmployerEditForm):
    """Members may post gigs without replacing their NYSC member account."""
    safety_agreement = BooleanField(
        "I will post genuine paid work, disclose the working conditions, and never charge applicants fees.",
        validators=[DataRequired(message="Accept the posting rules to continue.")])
    submit = SubmitField("Create gig owner profile")


class GigPostingForm(FlaskForm):
    """Shorter one-off gig form; all critical pay and safety fields remain required."""
    title = StringField("What work do you need done?",
        validators=[DataRequired(), Length(min=5, max=160)])
    work_mode = SelectField("Where will the work happen?", choices=WORK_MODES,
        validators=[DataRequired()])
    state = SelectField("State", choices=STATES, validators=[DataRequired()])
    lga = StringField("LGA", validators=[Optional(), Length(max=100)])
    location_description = StringField("General work location or landmark (optional)",
        validators=[Optional(), Length(max=255)])
    description = TextAreaField("Describe the tasks clearly",
        validators=[DataRequired(), Length(min=40, max=6000)])
    requirements = TextAreaField("Who is suitable for this gig?",
        validators=[DataRequired(), Length(min=15, max=4000)])
    hours_per_week = IntegerField("Estimated hours of work per week (optional)",
        validators=[Optional(), NumberRange(min=1, max=84)])
    schedule_notes = StringField("When will the work happen?",
        validators=[DataRequired(), Length(min=5, max=240)])
    pay_amount = IntegerField("Guaranteed advertised payment (₦)",
        validators=[DataRequired(), NumberRange(min=1, max=1000000000)])
    pay_unit = SelectField("Payment basis", choices=PAY_UNITS,
        validators=[DataRequired()], default="project")
    closing_date = DateField("Application deadline", format="%Y-%m-%d",
        validators=[DataRequired()])
    serving_only = BooleanField("Only serving NYSC members can apply")
    safety_agreement = BooleanField(
        "I confirm this is paid work with no application fee. The listing must pass moderation before publication.",
        validators=[DataRequired(message="Confirm the posting rules to submit.")])
    submit = SubmitField("Submit gig for publication")

    def validate_closing_date(self, field):
        if field.data and field.data < date.today():
            raise ValidationError("The deadline cannot be in the past.")
