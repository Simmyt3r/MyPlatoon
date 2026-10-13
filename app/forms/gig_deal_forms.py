"""Validated, consent-first gig offers. The pay unit is fixed by the job post."""
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange


class GigOfferForm(FlaskForm):
    scope = TextAreaField("Agreed work and deliverables",
                          validators=[DataRequired(), Length(min=30, max=2500)])
    schedule = StringField("Agreed work schedule / deadline",
                           validators=[DataRequired(), Length(min=5, max=300)])
    pay_amount = IntegerField("Offered pay (₦)",
                              validators=[DataRequired(), NumberRange(min=1, max=1000000000)])
    submit = SubmitField("Send offer for member acceptance")
