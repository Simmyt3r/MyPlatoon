from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length


class RejectionForm(FlaskForm):
    reason = TextAreaField("Rejection Reason", validators=[DataRequired(), Length(min=5, max=1000)])
    submit = SubmitField("Reject Profile")


class AnnouncementForm(FlaskForm):
    title = StringField("Title", validators=[DataRequired(), Length(max=200)])
    body = TextAreaField("Message", validators=[DataRequired(), Length(max=4000)])
    submit = SubmitField("Publish Announcement")


class CategoryForm(FlaskForm):
    name = StringField("Category Name", validators=[DataRequired(), Length(max=80)])
    submit = SubmitField("Add Category")
