"""PPA submission and review forms. No third-party geocoding or private location collection."""
from flask_wtf import FlaskForm
from wtforms import (
    StringField, SelectField, TextAreaField, DecimalField, SubmitField
)
from wtforms.validators import DataRequired, Length, Optional, NumberRange, URL, Regexp
from app.models.platoon import NYSC_STATES
from app.models.ppa import PPA_SECTORS, PPA_YES_NO


class PPAForm(FlaskForm):
    name = StringField("PPA / Organisation name", validators=[
        DataRequired(), Length(min=3, max=180)])
    state = SelectField("NYSC posting state",
        choices=[("", "Choose state")] + [(s, s) for s in NYSC_STATES],
        validators=[DataRequired()])
    lga = StringField("Local government area", validators=[
        DataRequired(), Length(min=2, max=100)])
    town = StringField("Town / district", validators=[Optional(), Length(max=120)])
    address = StringField("Public workplace address or landmark", validators=[
        Optional(), Length(max=250)])
    sector = SelectField("Organisation sector", choices=PPA_SECTORS,
        validators=[DataRequired()])
    website = StringField("Official organisation website (optional)",
        validators=[Optional(), URL(require_tld=True), Regexp(r"^https?://", message="Use an http or https URL."), Length(max=250)])
    accommodation = SelectField("Does the PPA offer corps-member accommodation?",
        choices=PPA_YES_NO, default="unknown", validators=[DataRequired()])
    allowance = SelectField("Does the PPA pay a separate allowance?",
        choices=PPA_YES_NO, default="unknown", validators=[DataRequired()])
    experience_notes = TextAreaField(
        "What should incoming corps members know?",
        validators=[Optional(), Length(max=1500)],
        description="Share firsthand general experience, not names, phone numbers, or sensitive personal details.")
    latitude = DecimalField("PPA workplace latitude (optional)", places=6,
        validators=[Optional(), NumberRange(min=-90, max=90)],
        description="Pin only the public workplace, never a member's residence.")
    longitude = DecimalField("PPA workplace longitude (optional)", places=6,
        validators=[Optional(), NumberRange(min=-180, max=180)])
    submit = SubmitField("Submit PPA for review")

    def validate(self, extra_validators=None):
        valid = super().validate(extra_validators)
        # Prevent the user from accidentally creating a point at 0/0 or a one-axis pin.
        if (self.latitude.data is None) != (self.longitude.data is None):
            self.longitude.errors.append("Provide both coordinates or leave both blank.")
            valid = False
        return valid


class PPAReviewForm(FlaskForm):
    reason = TextAreaField("Reason (needed when rejecting)",
        validators=[Optional(), Length(max=500)])
    submit = SubmitField("Save decision")



class PPAExperienceForm(FlaskForm):
    service_year = DecimalField("Year you served at this PPA", places=0, validators=[
        DataRequired(), NumberRange(min=1973, max=2100)])
    accommodation = SelectField("Accommodation while you served",
        choices=PPA_YES_NO, validators=[DataRequired()], default="unknown")
    allowance = SelectField("Separate PPA allowance while you served",
        choices=PPA_YES_NO, validators=[DataRequired()], default="unknown")
    notes = TextAreaField("Your experience / practical advice", validators=[
        Optional(), Length(max=1200)],
        description="No personal phone numbers, private addresses or unsupported allegations.")
    submit = SubmitField("Send contribution for review")
