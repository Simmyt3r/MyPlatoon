from flask import Blueprint, render_template, redirect, url_for, flash, current_app
from flask_login import login_required, current_user

from app.extensions import db
from app.forms.profile_forms import ProfileForm, PrivacyForm, SubmitForApprovalForm
from app.models import Skill
from app.services.cloudinary_service import upload_image, delete_image, ImageUploadError
from app.services.audit_service import log_action
from app.services.notification_service import notify
from app.services.platoon_membership import assign_platoon, set_form_assignment_defaults

bp = Blueprint("profile", __name__)


def _sync_skills(profile, raw_skills: str):
    names = [s.strip() for s in (raw_skills or "").split(",") if s.strip()]
    names = list(dict.fromkeys(n.lower() for n in names))[:25]  # dedupe, cap at 25
    skills = []
    for name in names:
        skill = Skill.query.filter(db.func.lower(Skill.name) == name).first()
        if not skill:
            skill = Skill(name=name.title())
            db.session.add(skill)
            db.session.flush()
        skills.append(skill)
    profile.skills = skills


@bp.route("/dashboard")
@login_required
def dashboard():
    profile = current_user.profile
    return render_template("profile/dashboard.html", profile=profile,
                            completion=profile.completion_percent() if profile else 0,
                            breakdown=profile.completion_breakdown() if profile else {})


@bp.route("/edit", methods=["GET", "POST"])
@login_required
def edit():
    profile = current_user.profile
    form = ProfileForm(obj=profile)
    set_form_assignment_defaults(form, profile)
    if not form.is_submitted():
        form.skills.data = ", ".join(s.name for s in profile.skills)

    if form.validate_on_submit():
        from app.utils.urls import ensure_scheme

        for field in ("nickname", "gender", "state_of_origin", "lga", "phone_number",
                      "whatsapp_number", "current_location", "address", "profession",
                      "course_of_study", "institution", "graduation_year",
                      "certifications", "biography"):
            setattr(profile, field, getattr(form, field).data)
        for field in ("website", "facebook", "instagram", "tiktok", "twitter_x"):
            setattr(profile, field, ensure_scheme(getattr(form, field).data))

        _sync_skills(profile, form.skills.data)

        # Editing an approved profile sends it back for a light re-review
        # only if it was previously rejected; approved members can keep
        # editing without losing their listing.
        if profile.status == "rejected":
            profile.status = "draft"

        photo_error = None
        if form.photo.data:
            try:
                result = upload_image(form.photo.data, folder="platoon5/profiles")
                old_public_id = profile.photo_public_id
                profile.photo_url = result["url"]
                profile.photo_public_id = result["public_id"]
                if old_public_id:
                    delete_image(old_public_id)
            except ImageUploadError as exc:
                photo_error = str(exc)

        # Save everything else regardless of whether the photo upload
        # succeeded -- a failed image upload shouldn't discard the rest of
        # what someone just filled in.
        db.session.commit()
        log_action(current_user, "profile.update", "Profile", profile.id)

        if photo_error:
            flash(photo_error, "warning")
        else:
            flash("Profile updated successfully.", "success")
        return redirect(url_for("profile.dashboard"))

    return render_template("profile/edit.html", form=form, profile=profile)


@bp.route("/privacy", methods=["GET", "POST"])
@login_required
def privacy():
    profile = current_user.profile
    form = PrivacyForm(obj=profile)
    if form.validate_on_submit():
        profile.profile_visibility = form.profile_visibility.data
        profile.phone_visibility = form.phone_visibility.data
        profile.whatsapp_visibility = form.whatsapp_visibility.data
        profile.address_visibility = form.address_visibility.data
        db.session.commit()
        log_action(current_user, "profile.privacy_update", "Profile", profile.id)
        flash("Privacy settings saved.", "success")
        return redirect(url_for("profile.dashboard"))
    return render_template("profile/privacy.html", form=form, profile=profile)


@bp.route("/submit", methods=["POST"])
@login_required
def submit_for_approval():
    profile = current_user.profile
    form = SubmitForApprovalForm()
    if not form.validate_on_submit():
        flash("Something went wrong. Please try again.", "danger")
        return redirect(url_for("profile.dashboard"))

    if profile.completion_percent() < 60:
        flash("Please complete more of your profile (at least 60%) before submitting.", "warning")
        return redirect(url_for("profile.dashboard"))

    profile.status = "pending"
    profile.rejection_reason = None
    db.session.commit()
    log_action(current_user, "profile.submit_for_approval", "Profile", profile.id)

    from app.models import User
    for admin in User.query.filter_by(role="admin").all():
        notify(admin, f"{current_user.full_name} submitted their profile for approval.")

    flash("Profile submitted for admin review.", "success")
    return redirect(url_for("profile.dashboard"))


@bp.route("/me")
@login_required
def my_public_profile():
    return redirect(url_for("directory.member_profile", slug=current_user.profile.slug))
