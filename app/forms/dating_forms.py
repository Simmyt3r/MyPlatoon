from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, SubmitField, BooleanField
from wtforms.validators import DataRequired, Optional, Length

GENDER_FORM_CHOICES = [("male", "Man"), ("female", "Woman"), ("nonbinary", "Nonbinary")]
INTERESTED_IN_CHOICES = [("female", "Women"), ("male", "Men"),
                         ("nonbinary", "Nonbinary people"), ("any", "Everyone")]


class DatingPersonaForm(FlaskForm):
    display_name = StringField("Display Name", validators=[Optional(), Length(max=80)],
                                description="Shown to potential matches instead of your full name, if you'd like.")
    tagline = StringField("Tagline", validators=[Optional(), Length(max=140)],
                           description="A short, fun one-liner about you.")
    bio = TextAreaField("About You", validators=[Optional(), Length(max=1000)])
    gender = SelectField("I am a", choices=GENDER_FORM_CHOICES, validators=[DataRequired()])
    interested_in = SelectField("Looking to meet", choices=INTERESTED_IN_CHOICES,
                                 validators=[DataRequired()])
    interests = StringField("Interests (comma-separated)", validators=[Optional(), Length(max=500)],
                             description="e.g. hiking, movies, cooking, football")
    show_profile_photo = BooleanField(
        "Show my MyPlatoon profile picture to other Dating participants",
        description="Off by default. Your profile picture stays hidden in Dating until you enable it.")
    age_confirm = BooleanField(
        "I confirm that I am at least 18 years old and agree to use Dating respectfully.",
        validators=[DataRequired(message="You must confirm that you are 18 or older.")],
        description="Dating is an optional adults-only feature. We do not collect your date of birth for it.")
    submit = SubmitField("Save My Dating Persona")


class DatingReportForm(FlaskForm):
    reason = TextAreaField("Why are you reporting this person?",
                            validators=[DataRequired(), Length(min=5, max=500)])
    submit = SubmitField("Submit Report")
