from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, NumberRange, Regexp
from app.models.platoon import SERVICE_STAGES, NYSC_STATES
from app.services.platoon_membership import validate_platoon_fields

VISIBILITY_CHOICES = [
    ("public", "Public"),
    ("platoon", "Platoon Members Only"),
    ("private", "Private"),
]
ADDRESS_VISIBILITY_CHOICES = [
    ("general", "General Location Only"),
    ("exact", "Exact Address"),
    ("private", "Private"),
]
GENDER_CHOICES = [("", "Prefer not to say"), ("male", "Male"), ("female", "Female")]


class ProfileForm(FlaskForm):
    service_stage = SelectField("NYSC Journey", choices=SERVICE_STAGES,
                                default="pcm")
    nysc_state = SelectField("Orientation Camp State",
                             choices=[("", "Choose your camp state")] + [(s, s) for s in NYSC_STATES], default="")
    service_year = IntegerField("Orientation Year")
    nysc_batch = SelectField("Batch", choices=[("", "Choose batch"), ("A", "A"), ("B", "B"), ("C", "C")], default="")
    nysc_stream = SelectField("Stream", choices=[("", "Choose stream"), ("I", "I"), ("II", "II")], default="")
    platoon_number = IntegerField("Platoon Number (from camp)")
    photo = FileField("Profile Photograph", validators=[
        Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])
    nickname = StringField("Nickname", validators=[Optional(), Length(max=80)])
    gender = SelectField("Gender", choices=GENDER_CHOICES, validators=[Optional()])
    state_of_origin = StringField("State of Origin", validators=[Optional(), Length(max=60)])
    lga = StringField("LGA", validators=[Optional(), Length(max=80)])
    phone_number = StringField("Phone Number", validators=[
        Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")])
    whatsapp_number = StringField("WhatsApp Number", validators=[
        Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")])
    current_location = StringField("Current Location", validators=[Optional(), Length(max=120)])
    address = StringField("Address", validators=[Optional(), Length(max=255)])

    profession = StringField("Profession", validators=[Optional(), Length(max=120)])
    course_of_study = StringField("Course of Study", validators=[Optional(), Length(max=150)])
    institution = StringField("Institution", validators=[Optional(), Length(max=150)])
    graduation_year = IntegerField("Graduation Year", validators=[
        Optional(), NumberRange(min=1970, max=2100)])
    certifications = TextAreaField("Certifications", validators=[Optional(), Length(max=2000)])
    biography = TextAreaField("Short Biography", validators=[Optional(), Length(max=2000)])
    skills = StringField("Skills (comma-separated)", validators=[Optional(), Length(max=500)])

    website = StringField("Website", validators=[Optional(), Length(max=255)])
    facebook = StringField("Facebook", validators=[Optional(), Length(max=255)])
    instagram = StringField("Instagram", validators=[Optional(), Length(max=255)])
    tiktok = StringField("TikTok", validators=[Optional(), Length(max=255)])
    twitter_x = StringField("X / Twitter", validators=[Optional(), Length(max=255)])

    submit = SubmitField("Save Profile")


class PrivacyForm(FlaskForm):
    profile_visibility = SelectField("Profile Visibility", choices=VISIBILITY_CHOICES,
                                      validators=[DataRequired()])
    phone_visibility = SelectField("Phone Visibility", choices=VISIBILITY_CHOICES,
                                    validators=[DataRequired()])
    whatsapp_visibility = SelectField("WhatsApp Visibility", choices=VISIBILITY_CHOICES,
                                       validators=[DataRequired()])
    address_visibility = SelectField("Address Visibility", choices=ADDRESS_VISIBILITY_CHOICES,
                                      validators=[DataRequired()])
    submit = SubmitField("Save Privacy Settings")


class SubmitForApprovalForm(FlaskForm):
    submit = SubmitField("Submit for Approval")
