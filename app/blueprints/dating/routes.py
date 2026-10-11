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
    block_persona, delete_dating_persona, sent_interest_ids,
    mutual_connections, express_interest, withdraw_interest,
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
    connections = mutual_connections(persona)
    return render_template("dating/home.html", persona=persona,
                            top_matches=top_matches, mutuals=mutuals,
                            connections=connections, liked_ids=sent_interest_ids(persona))


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
    return render_template("dating/browse.html", persona=persona, matches=matches,
                           liked_ids=sent_interest_ids(persona))


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
    return render_template("dating/matches.html", persona=persona, mutuals=mutuals,
                           liked_ids=sent_interest_ids(persona))


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
                           target=target, shared=shared,
                           interested=target.id in sent_interest_ids(viewer))


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



@bp.route("/connections")
@login_required
@dating_enabled_required
def connections():
    persona = getattr(current_user.profile, "dating_persona", None)
    if not persona:
        return redirect(url_for("dating.home"))
    if persona.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    people = mutual_connections(persona)
    return render_template("dating/connections.html", persona=persona, people=people)


@bp.route("/interest/<int:persona_id>", methods=["POST"])
@login_required
@dating_enabled_required
@limiter.limit("20 per hour")
def interest(persona_id):
    viewer = getattr(current_user.profile, "dating_persona", None)
    if not viewer or viewer.age_confirmed_at is None:
        abort(403)
    target = DatingPersona.query.get_or_404(persona_id)
    if target.id == viewer.id:
        abort(400)
    try:
        created, reciprocal = express_interest(viewer, target)
    except ValueError:
        abort(403)
    if reciprocal and created:
        flash("You both expressed interest! This connection is now in your Dating connections.", "success")
    elif created:
        flash("Interest recorded privately. The other person won't be notified unless they also express interest.", "info")
    else:
        flash("You've already expressed interest in this persona.", "info")
    return redirect(url_for("dating.person_detail", persona_id=target.id))


@bp.route("/interest/<int:persona_id>/withdraw", methods=["POST"])
@login_required
@dating_enabled_required
@limiter.limit("20 per hour")
def interest_withdraw(persona_id):
    viewer = getattr(current_user.profile, "dating_persona", None)
    if not viewer or viewer.age_confirmed_at is None:
        abort(403)
    changed = withdraw_interest(viewer, persona_id)
    if changed:
        log_action(current_user, "dating.interest_withdrawn", "DatingPersona", persona_id)
    flash("Your expression of interest has been withdrawn.", "info")
    return redirect(url_for("dating.browse"))



@bp.route("/messages/<int:persona_id>", methods=["GET", "POST"])
@login_required
@dating_enabled_required
@limiter.limit("40 per hour", methods=["POST"])
def conversation(persona_id):
    """A private text conversation only for two actively consenting adults."""
    from app.forms.dating_forms import DatingMessageForm
    from app.services.dating_chat_service import can_message, conversation_query, send_text

    viewer = getattr(current_user.profile, "dating_persona", None)
    if viewer is None or viewer.age_confirmed_at is None:
        return redirect(url_for("dating.persona"))
    target = DatingPersona.query.get_or_404(persona_id)
    if not can_message(viewer, target):
        # Respond the same whether the user was blocked, interest was withdrawn,
        # the target paused, or the pair was never connected.
        abort(404)

    form = DatingMessageForm()
    if form.validate_on_submit():
        try:
            send_text(viewer, target, form.body.data)
        except (PermissionError, ValueError):
            abort(403)
        return redirect(url_for("dating.conversation", persona_id=target.id, page=1))

    # Latest 30 messages first in DB for efficient bounded reads; reverse on
    # display to show chronological text bubbles. Older pages are explicit.
    page = max(1, request.args.get("page", 1, type=int))
    pagination = (conversation_query(viewer.id, target.id)
                  .order_by(db.desc("created_at"), db.desc("id"))
                  .paginate(page=page, per_page=30, error_out=False))
    return render_template(
        "dating/conversation.html", viewer=viewer, target=target,
        form=form, messages=list(reversed(pagination.items)),
        pagination=pagination,
    )


@bp.route("/messages/report/<int:message_id>", methods=["GET", "POST"])
@login_required
@dating_enabled_required
@limiter.limit("5 per day", methods=["POST"])
def report_message(message_id):
    """The recipient may report received text even after unmatching/blocking."""
    from app.models import DatingMessage, DatingMessageReport, User
    from app.forms.dating_forms import DatingMessageReportForm
    from app.services.dating_chat_service import received_message
    from app.services.notification_service import notify

    viewer = getattr(current_user.profile, "dating_persona", None)
    if viewer is None or viewer.age_confirmed_at is None:
        abort(403)
    message = DatingMessage.query.get_or_404(message_id)
    if not received_message(message, viewer.id):
        abort(404)
    previous = DatingMessageReport.query.filter_by(
        message_id=message.id, reporter_id=viewer.id).first()
    if previous:
        flash("You've already reported this message. A moderator can review it.", "info")
        return redirect(url_for("dating.connections"))

    form = DatingMessageReportForm()
    if form.validate_on_submit():
        report = DatingMessageReport(
            message_id=message.id, reporter_id=viewer.id,
            reason=form.reason.data.strip(),
        )
        db.session.add(report)
        db.session.commit()
        log_action(current_user, "dating.message_report", "DatingMessage", message.id)
        for admin in User.query.filter_by(role="admin").all():
            notify(admin, "A private Dating message was reported for moderation.",
                   category="warning")
        flash("Your report has been submitted confidentially. You may also block the person.", "success")
        return redirect(url_for("dating.connections"))
    return render_template("dating/report_message.html", form=form, message=message)


@bp.route("/moderation/messages")
@login_required
def reported_messages():
    """Private message report queue; never visible to ordinary members."""
    from app.services.dating_chat_service import message_reports_for_admin
    if not current_user.is_admin:
        abort(403)
    status = request.args.get("status", "pending")
    if status not in ("pending", "removed", "dismissed"):
        status = "pending"
    return render_template("dating/moderate_messages.html",
                           reports=message_reports_for_admin(status), status=status)


@bp.route("/moderation/messages/<int:report_id>/review", methods=["POST"])
@login_required
@limiter.limit("120 per hour")
def moderate_message(report_id):
    """Explicit admin action: hide abusive message or dismiss report."""
    from app.models import DatingMessageReport
    if not current_user.is_admin:
        abort(403)
    report = DatingMessageReport.query.get_or_404(report_id)
    decision = request.form.get("decision")
    if decision not in ("removed", "dismissed"):
        abort(400)
    if report.status != "pending":
        flash("This report has already been reviewed.", "info")
        return redirect(url_for("dating.reported_messages"))
    report.status = decision
    report.reviewed_by_id = current_user.id
    report.reviewed_at = datetime.utcnow()
    if decision == "removed":
        report.message.is_removed = True
    db.session.commit()
    log_action(current_user, "dating.message_" + decision,
               "DatingMessageReport", report.id)
    flash("Message report reviewed.", "success")
    return redirect(url_for("dating.reported_messages"))
