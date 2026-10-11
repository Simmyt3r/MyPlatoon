from functools import wraps
from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, abort
from flask_login import login_required, current_user

from app.extensions import db, limiter
from app.forms.dating_forms import DatingPersonaForm, DatingReportForm
from app.models import DatingPersona, DatingBlock
from app.models.dating import score_label
from app.services.dating_service import (
    generate_matches_for_persona, browse_matches_for_persona,
    mutual_matches_for_persona, report_persona, is_blocked,
    block_persona, delete_dating_persona,
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
    if persona.age_confirmed_at is None:
        flash("Dating is for adults only. Please confirm you are at least 18 before using it.", "warning")
        return redirect(url_for("dating.persona"))

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
        form.age_confirm.data = existing.age_confirmed_at is not None

    if form.validate_on_submit():
        is_new = existing is None
        target = existing or DatingPersona(profile_id=current_user.profile.id)
        target.display_name = form.display_name.data.strip() or current_user.full_name.split(" ")[0]
        target.tagline = form.tagline.data.strip() if form.tagline.data else None
        target.bio = form.bio.data.strip() if form.bio.data else None
        target.gender = form.gender.data
        target.interested_in = form.interested_in.data
        target.interests = form.interests.data.strip() if form.interests.data else None
        target.show_profile_photo = bool(form.show_profile_photo.data)
        # An age declaration is not a government ID check. Never save DOB here.
        target.age_confirmed_at = target.age_confirmed_at or datetime.utcnow()
        if is_new:
            db.session.add(target)
        db.session.commit()

        log_action(current_user, "dating.persona_create" if is_new else "dating.persona_update",
                   "DatingPersona", target.id)

        generate_matches_for_persona(target)

        flash("Your dating persona is saved. Your suggestions are private to opted-in adult participants.", "success")
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
    if persona.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    if persona.status != "active" or persona.is_reported:
        flash("Resume your persona before refreshing suggestions.", "warning")
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
    if persona.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
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
    if persona.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
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
    if persona.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    if persona.is_reported:
        flash("Your persona is under review and cannot be resumed yet.", "warning")
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
@limiter.limit("5 per hour", methods=["POST"])
def report(persona_id):
    target = DatingPersona.query.get_or_404(persona_id)
    if current_user.profile and target.profile_id == current_user.profile.id:
        abort(400)  # can't report yourself
    persona = getattr(current_user.profile, "dating_persona", None)
    if not persona or persona.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    if is_blocked(persona.id, target.id):
        abort(404)

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



@bp.route("/person/<int:persona_id>")
@login_required
@dating_enabled_required
def person_detail(persona_id):
    """Show only the opted-in persona: no general profile/contact leakage."""
    viewer = getattr(current_user.profile, "dating_persona", None)
    if not viewer or viewer.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    target = DatingPersona.query.get_or_404(persona_id)
    if target.id == viewer.id:
        return redirect(url_for("dating.persona"))
    if (not viewer.is_active_and_visible() or not target.is_active_and_visible()
            or not viewer.is_compatible_with(target)
            or is_blocked(viewer.id, target.id)):
        abort(404)
    shared = viewer.shared_interests_with(target)
    return render_template("dating/person_detail.html", viewer=viewer,
                           target=target, shared=shared)


@bp.route("/block/<int:persona_id>", methods=["POST"])
@login_required
@dating_enabled_required
@limiter.limit("30 per hour")
def block(persona_id):
    viewer = getattr(current_user.profile, "dating_persona", None)
    if not viewer or viewer.age_confirmed_at is None:
        abort(403)
    target = DatingPersona.query.get_or_404(persona_id)
    if target.id == viewer.id:
        abort(400)
    block_persona(viewer, target)
    log_action(current_user, "dating.block", "DatingPersona", target.id)
    flash("You won't see each other in Dating suggestions. The other person was not notified.", "info")
    return redirect(url_for("dating.browse"))


@bp.route("/blocked")
@login_required
@dating_enabled_required
def blocked():
    viewer = getattr(current_user.profile, "dating_persona", None)
    if not viewer or viewer.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    rows = (DatingBlock.query.filter_by(blocker_id=viewer.id)
            .order_by(DatingBlock.created_at.desc()).all())
    return render_template("dating/blocked.html", rows=rows)


@bp.route("/unblock/<int:persona_id>", methods=["POST"])
@login_required
@dating_enabled_required
@limiter.limit("30 per hour")
def unblock(persona_id):
    viewer = getattr(current_user.profile, "dating_persona", None)
    if not viewer or viewer.age_confirmed_at is None:
        abort(403)
    row = DatingBlock.query.filter_by(
        blocker_id=viewer.id, blocked_id=persona_id).first_or_404()
    db.session.delete(row)
    db.session.commit()
    log_action(current_user, "dating.unblock", "DatingPersona", persona_id)
    flash("Block removed. Either of you may become visible in future suggestions.", "info")
    return redirect(url_for("dating.blocked"))


@bp.route("/delete", methods=["POST"])
@login_required
@dating_enabled_required
@limiter.limit("5 per hour")
def delete():
    persona = getattr(current_user.profile, "dating_persona", None)
    if persona is None:
        return redirect(url_for("dating.home"))
    deleted_id = persona.id
    delete_dating_persona(persona)
    log_action(current_user, "dating.persona_deleted", "DatingPersona", deleted_id)
    flash("Your dating persona, suggestions and blocks have been removed. Your MyPlatoon account remains.", "success")
    return redirect(url_for("dating.home"))
