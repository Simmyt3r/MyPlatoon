"""Form-level checks and cohort assignment for NYSC membership.

PCMs must never be assigned a placeholder or inferred platoon. One valid
identity uses state, service year, batch, stream and platoon number.
"""
from app.models.platoon import Platoon, NYSC_STATES, BATCH_CHOICES, STREAM_CHOICES


def validate_platoon_fields(form):
    if form.service_stage.data == "pcm":
        return True

    valid = True
    fields = (
        (form.nysc_state, NYSC_STATES, "Select the NYSC orientation state."),
        (form.nysc_batch, BATCH_CHOICES, "Select the NYSC batch."),
        (form.nysc_stream, STREAM_CHOICES, "Select the NYSC stream."),
    )
    for field, allowed, message in fields:
        if not field.data or field.data not in allowed:
            field.errors.append(message)
            valid = False

    year = form.service_year.data
    if year is None or not 1973 <= year <= 2100:
        form.service_year.errors.append("Enter the year of your NYSC orientation camp.")
        valid = False

    number = form.platoon_number.data
    if number is None or not 1 <= number <= 99:
        form.platoon_number.errors.append("Enter the number NYSC assigned at camp.")
        valid = False

    return valid


def assign_platoon(profile, form):
    """Set the reported orientation platoon. Called only after valid form."""
    profile.service_stage = form.service_stage.data
    if form.service_stage.data == "pcm":
        profile.platoon = None
        return
    profile.platoon = Platoon.find_or_create(
        state=form.nysc_state.data,
        service_year=form.service_year.data,
        batch=form.nysc_batch.data,
        stream=form.nysc_stream.data,
        number=form.platoon_number.data,
    )


def set_form_assignment_defaults(form, profile):
    """Keep existing camp assignment selected when editing a profile."""
    if not profile or not profile.platoon or form.is_submitted():
        return
    p = profile.platoon
    form.nysc_state.data = p.state
    form.service_year.data = p.service_year
    form.nysc_batch.data = p.batch
    form.nysc_stream.data = p.stream
    form.platoon_number.data = p.number
