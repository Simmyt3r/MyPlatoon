from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.forms.dating_forms import DatingPersonaForm, DatingReportForm
from app.models import DatingPersona
from app.models.dating import score_label
from app.services.dating_service import (
    generate_matches_for_persona, browse_matches_for_persona,
    mutual_matches_for_persona, report_persona,
)
from app.services.audit_service import log_action

bp = Blueprint("dating", __name__)


def dating_enabled_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_app.config.get("ENABLE_DATING", True):
            abort(404)
        return view(*args, **kwargs)
    return wrapped


def _require_approved_profile():
    """A dating persona can only exist on top of an admin-approved main
    profile -- the same trust bar the rest of the platform already uses,
    rather than inventing separate age/identity verification from scratch.
    """
    profile = current_user.profile
    if not profile or profile.status != "approved":
        flash("Your main profile needs to be approved before you can use Dating. "
              "Complete your profile and submit it for admin review first.", "warning")
        return False
    return True


@bp.route("/")
@login_required
@dating_enabled_required
def home():
    persona = DatingPersona.query.filter_by(profile_id=current_user.profile.id).first() \
        if current_user.profile else None
    if not persona:
        return render_template("dating/intro.html")

    top_matches = browse_matches_for_persona(persona)[:5]
    mutuals = mutual_matches_for_persona(persona)
    return render_template("dating/home.html", persona=persona,
                            top_matches=top_matches, mutuals=mutuals)


@bp.route("/persona", methods=["GET", "POST"])
@login_required
@dating_enabled_required
def persona():
    if not _require_approved_profile():
        return redirect(url_for("profile.dashboard"))

    existing = DatingPersona.query.filter_by(profile_id=current_user.profile.id).first()
    form = DatingPersonaForm(obj=existing)
    if not form.is_submitted() and existing:
        form.interests.data = existing.interests

    if form.validate_on_submit():
        is_new = existing is None
        target = existing or DatingPersona(profile_id=current_user.profile.id)
        target.display_name = form.display_name.data.strip() or current_user.full_name.split(" ")[0]
        target.tagline = form.tagline.data.strip() if form.tagline.data else None
        target.bio = form.bio.data.strip() if form.bio.data else None
        target.gender = form.gender.data
        target.interested_in = form.interested_in.data
        target.interests = form.interests.data.strip() if form.interests.data else None
        if is_new:
            db.session.add(target)
        db.session.commit()

        log_action(current_user, "dating.persona_create" if is_new else "dating.persona_update",
                   "DatingPersona", target.id)

        generate_matches_for_persona(target)

        flash("Your dating persona is live! We're finding your matches now.", "success")
        return redirect(url_for("dating.home"))

    return render_template("dating/persona_form.html", form=form, persona=existing)


@bp.route("/refresh", methods=["POST"])
@login_required
@dating_enabled_required
@limiter.limit("20 per hour")
def refresh():
    persona = DatingPersona.query.filter_by(profile_id=current_user.profile.id).first() \
        if current_user.profile else None
    if not persona:
        return redirect(url_for("dating.home"))
    generate_matches_for_persona(persona)
    flash("Your matches have been refreshed!", "success")
    return redirect(url_for("dating.browse"))


@bp.route("/browse")
@login_required
@dating_enabled_required
def browse():
    persona = DatingPersona.query.filter_by(profile_id=current_user.profile.id).first() \
        if current_user.profile else None
    if not persona:
        return redirect(url_for("dating.home"))
    matches = browse_matches_for_persona(persona)
    return render_template("dating/browse.html", persona=persona, matches=matches)


@bp.route("/matches")
@login_required
@dating_enabled_required
def matches():
    persona = DatingPersona.query.filter_by(profile_id=current_user.profile.id).first() \
        if current_user.profile else None
    if not persona:
        return redirect(url_for("dating.home"))
    mutuals = mutual_matches_for_persona(persona)
    return render_template("dating/matches.html", persona=persona, mutuals=mutuals)


@bp.route("/pause", methods=["POST"])
@login_required
@dating_enabled_required
def toggle_pause():
    persona = DatingPersona.query.filter_by(profile_id=current_user.profile.id).first() \
        if current_user.profile else None
    if not persona:
        return redirect(url_for("dating.home"))
    persona.status = "paused" if persona.status == "active" else "active"
    db.session.commit()
    log_action(current_user, f"dating.persona_{persona.status}", "DatingPersona", persona.id)
    flash("Your dating persona is now " + ("paused -- you won't appear in anyone's matches until you resume."
          if persona.status == "paused" else "active again!"), "info")
    return redirect(url_for("dating.home"))


@bp.route("/report/<int:persona_id>", methods=["GET", "POST"])
@login_required
@dating_enabled_required
def report(persona_id):
    target = DatingPersona.query.get_or_404(persona_id)
    if current_user.profile and target.profile_id == current_user.profile.id:
        abort(400)  # can't report yourself

    form = DatingReportForm()
    if form.validate_on_submit():
        report_persona(target, form.reason.data)
        log_action(current_user, "dating.report", "DatingPersona", target.id, detail=form.reason.data)

        from app.models import User
        for admin in User.query.filter_by(role="admin").all():
            from app.services.notification_service import notify
            notify(admin, f"A dating persona was reported and needs review.", category="warning")

        flash("Thanks for letting us know -- an admin will review this.", "success")
        return redirect(url_for("dating.browse"))

    return render_template("dating/report.html", form=form, target=target)
