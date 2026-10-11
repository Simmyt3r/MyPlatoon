from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, TextAreaField, SelectField, SubmitField
from wtforms.validators import DataRequired, Optional, Length, Email, Regexp


class BusinessForm(FlaskForm):
    logo = FileField("Business Logo", validators=[
        Optional(), FileAllowed(["jpg", "jpeg", "png", "webp"], "Images only.")])
    name = StringField("Business Name", validators=[DataRequired(), Length(max=150)])
    category_id = SelectField("Business Category", coerce=int, validators=[DataRequired()])
    description = TextAreaField("Business Description", validators=[Optional(), Length(max=2000)])
    address = StringField("Business Address", validators=[Optional(), Length(max=255)])
    phone = StringField("Business Phone", validators=[
        Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")])
    whatsapp = StringField("Business WhatsApp", validators=[
        Optional(), Regexp(r"^[0-9+\-\s()]{7,20}$", message="Enter a valid phone number.")])
    email = StringField("Business Email", validators=[Optional(), Email(), Length(max=255)])
    website = StringField("Website", validators=[Optional(), Length(max=255)])
    facebook = StringField("Facebook", validators=[Optional(), Length(max=255)])
    instagram = StringField("Instagram", validators=[Optional(), Length(max=255)])
    tiktok = StringField("TikTok", validators=[Optional(), Length(max=255)])
    twitter_x = StringField("X / Twitter", validators=[Optional(), Length(max=255)])
    submit = SubmitField("Save Business")
