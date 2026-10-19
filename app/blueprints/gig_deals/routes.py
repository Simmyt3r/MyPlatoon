"""Private end-to-end gig hiring lifecycle.

An application is not an accepted work contract. Offers, acceptance,
completion and payment acknowledgement require explicit independent actions.
No money flows through MyPlatoon.
"""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from sqlalchemy import or_

from app.extensions import db, limiter
from app.models import (
    Employer, JobApplication, GigDeal, GigDispute, GigReview, User,
    Notification, GigWorkUpdate, GigTerminationRequest,
)
from app.services.audit_service import log_action

bp = Blueprint("gig_deals", __name__)


def _deal_locked(deal_id):
    return GigDeal.query.filter_by(id=deal_id).with_for_update().first_or_404()


def _roles(deal):
    owner = (current_user.id == deal.employer.owner_user_id)
    worker = (current_user.id == deal.worker_id)
    return owner, worker


def _participant(deal):
    owner, worker = _roles(deal)
    if not (owner or worker):
        abort(403)
    return owner, worker


def _pending_termination(deal_id):
    return GigTerminationRequest.query.filter_by(
        deal_id=deal_id, status="pending").first()


def _cancel_pending_termination(deal):
    pending = _pending_termination(deal.id)
    if pending:
        pending.status = "superseded"
        pending.responded_at = datetime.utcnow()
    return pending


def _notify(user_id, message, category="info"):
    db.session.add(Notification(user_id=user_id, message=message[:255],
                                category=category))


def _success(deal, action, message):
    db.session.commit()
    log_action(current_user, "gig_deal." + action, "GigDeal", deal.id)
    flash(message, "success")
    return redirect(url_for("gig_deals.detail", deal_id=deal.id))


@bp.route("/")
@login_required
def index():
    employer = Employer.query.filter_by(owner_user_id=current_user.id).first()
    # NYSC members can also own a registered gig business. Show both
    # work agreements they accepted AND their own employer-side deals.
    filters = [GigDeal.worker_id == current_user.id]
    if employer is not None:
        filters.append(GigDeal.employer_id == employer.id)
    deals = GigDeal.query.filter(or_(*filters)).order_by(
        GigDeal.updated_at.desc()).all()
    return render_template("gig_deals/index.html", deals=deals)


@bp.route("/offer/<int:application_id>", methods=["GET", "POST"])
@login_required
@limiter.limit("12 per hour", methods=["POST"])
def offer(application_id):
    from app.forms.gig_deal_forms import GigOfferForm
    employer = Employer.query.filter_by(owner_user_id=current_user.id).first()
    if employer is None or employer.status != "approved" or not current_user.is_active:
        abort(403)
    application = JobApplication.query.filter_by(id=application_id).with_for_update().first_or_404()
    job = application.listing
    if job.employer_id != employer.id:
        abort(403)
    if job.job_kind != "gig":
        abort(400)
    existing = GigDeal.query.filter_by(application_id=application.id).first()
    if existing:
        return redirect(url_for("gig_deals.detail", deal_id=existing.id))
    if not job.is_open or application.status in ("declined", "hired"):
        abort(409)
    candidate = application.applicant
    if candidate.id == employer.owner_user_id or candidate.role != "member":
        abort(403)  # no self-deals, fabricated reciprocal hiring or fake ratings
    if not candidate.is_active or not candidate.profile or candidate.profile.status != "approved":
        abort(409)
    if job.serving_only and candidate.profile.service_stage != "serving":
        abort(409)
    form = GigOfferForm()
    if request.method == "GET":
        form.scope.data = job.description[:2500]
        form.schedule.data = (job.schedule_notes or "Agree a suitable schedule before starting")[:300]
        form.pay_amount.data = job.pay_min
    if form.validate_on_submit():
        amount = form.pay_amount.data
        if not (job.pay_min <= amount <= job.pay_max):
            form.pay_amount.errors.append(
                "Pay must stay inside the advertised range (₦{:,.0f}–₦{:,.0f}).".format(
                    job.pay_min, job.pay_max))
        else:
            deal = GigDeal(application_id=application.id,
                           employer_id=employer.id, worker_id=candidate.id,
                           scope=form.scope.data.strip(),
                           schedule=form.schedule.data.strip(),
                           pay_amount=amount, pay_unit=job.pay_unit)
            db.session.add(deal)
            _notify(candidate.id, "New gig offer for " + job.title + ". Review and accept or decline.")
            return _success(deal, "offered", "Your offer was sent. Work must not start until the member accepts.")
    return render_template("gig_deals/offer.html", form=form, application=application, job=job)


@bp.route("/<int:deal_id>")
@login_required
def detail(deal_id):
    deal = GigDeal.query.get_or_404(deal_id)
    owner, worker = _participant(deal)
    my_rating = GigReview.query.filter_by(deal_id=deal.id, reviewer_id=current_user.id).first()
    latest_resolution = (GigDispute.query.filter_by(deal_id=deal.id, status="resolved")
                         .order_by(GigDispute.reviewed_at.desc()).first())
    notes = (GigWorkUpdate.query.filter_by(deal_id=deal.id)
             .order_by(GigWorkUpdate.created_at.desc(), GigWorkUpdate.id.desc())
             .limit(40).all())
    terminations = (GigTerminationRequest.query.filter_by(deal_id=deal.id)
                    .order_by(GigTerminationRequest.created_at.desc(),
                              GigTerminationRequest.id.desc()).limit(10).all())
    pending_termination = next((t for t in terminations if t.status == "pending"), None)
    return render_template("gig_deals/detail.html", deal=deal,
                           owner=owner, worker=worker, my_rating=my_rating,
                           latest_resolution=latest_resolution, notes=list(reversed(notes)),
                           terminations=terminations, pending_termination=pending_termination)


@bp.route("/<int:deal_id>/respond", methods=["POST"])
@login_required
@limiter.limit("12 per hour")
def respond(deal_id):
    deal = _deal_locked(deal_id)
    _owner, worker = _participant(deal)
    if not worker:
        abort(403)
    if deal.status != "offered":
        abort(409)
    decision = request.form.get("decision")
    if decision not in ("accept", "decline"):
        abort(400)
    if decision == "accept":
        if request.form.get("accept_terms") != "yes":
            abort(400)
        if not current_user.is_active or not current_user.profile or current_user.profile.status != "approved":
            abort(403)
        if (deal.employer.status != "approved" or not deal.employer.owner.is_active or
                deal.application.listing.status != "published" or
                (deal.application.listing.serving_only and
                 current_user.profile.service_stage != "serving")):
            abort(409)
        deal.status = "active"
        deal.accepted_at = datetime.utcnow()
        deal.application.status = "hired"
    else:
        deal.status = "declined"
        deal.closed_at = datetime.utcnow()
    _notify(deal.employer.owner_user_id,
            "{} your gig offer: {}".format("Accepted" if decision == "accept" else "Declined",
                                          deal.application.listing.title))
    return _success(deal, decision, "Offer {}.".format("accepted" if decision == "accept" else "declined"))


@bp.route("/<int:deal_id>/cancel", methods=["POST"])
@login_required
def cancel(deal_id):
    deal = _deal_locked(deal_id)
    owner, _worker = _participant(deal)
    if not owner:
        abort(403)
    # Employer may only cancel an UNACCEPTED offer. After acceptance,
    # use mutual discussion or confidential dispute review.
    if deal.status != "offered":
        abort(409)
    deal.status = "cancelled"
    deal.closed_at = datetime.utcnow()
    _notify(deal.worker_id, "Gig offer withdrawn: " + deal.application.listing.title)
    return _success(deal, "cancelled", "Your unaccepted offer has been withdrawn.")


@bp.route("/<int:deal_id>/finish", methods=["POST"])
@login_required
def finish(deal_id):
    deal = _deal_locked(deal_id)
    _owner, worker = _participant(deal)
    if not worker:
        abort(403)
    if deal.status != "active" or _pending_termination(deal.id):
        abort(409)
    deal.status = "completion_requested"
    deal.completion_requested_at = datetime.utcnow()
    _notify(deal.employer.owner_user_id,
            "Worker marked a gig ready for completion review: " + deal.application.listing.title)
    return _success(deal, "completion_requested",
                    "Completion requested. The employer must confirm the work was delivered.")


@bp.route("/<int:deal_id>/confirm", methods=["POST"])
@login_required
def confirm(deal_id):
    deal = _deal_locked(deal_id)
    owner, _worker = _participant(deal)
    if not owner:
        abort(403)
    if deal.status != "completion_requested" or _pending_termination(deal.id):
        abort(409)
    deal.status = "completed"
    deal.completed_at = datetime.utcnow()
    _notify(deal.worker_id, "Work completion confirmed for " + deal.application.listing.title)
    return _success(deal, "completed", "Work completion confirmed. Payment is tracked separately.")


@bp.route("/<int:deal_id>/payment", methods=["POST"])
@login_required
def payment(deal_id):
    deal = _deal_locked(deal_id)
    owner, worker = _participant(deal)
    if deal.status != "completed":
        abort(409)
    if owner and request.form.get("action") == "report_paid":
        if deal.payment_status != "not_reported":
            abort(409)
        deal.payment_status = "reported_paid"
        _notify(deal.worker_id, "Employer reports paying for " +
                deal.application.listing.title + ". Confirm ONLY after you receive payment.")
        return _success(deal, "payment_reported",
                        "Payment marked reported. Only the worker can confirm receipt.")
    if worker and request.form.get("action") == "confirm_receipt":
        if deal.payment_status != "reported_paid":
            abort(409)
        deal.payment_status = "confirmed_paid"
        _notify(deal.employer.owner_user_id,
                "Worker has acknowledged receipt of your gig payment.")
        return _success(deal, "payment_acknowledged", "You acknowledged receiving payment.")
    abort(403)


@bp.route("/<int:deal_id>/dispute", methods=["POST"])
@login_required
@limiter.limit("6 per day")
def dispute(deal_id):
    deal = _deal_locked(deal_id)
    owner, worker = _participant(deal)
    if deal.status not in ("active", "completion_requested", "completed"):
        abort(409)
    reason = (request.form.get("reason") or "").strip()
    if not (20 <= len(reason) <= 1500):
        flash("Please describe the issue in 20–1,500 characters.", "warning")
        return redirect(url_for("gig_deals.detail", deal_id=deal.id))
    if GigDispute.query.filter_by(deal_id=deal.id, status="open").first():
        abort(409)
    db.session.add(GigDispute(deal_id=deal.id, raised_by_id=current_user.id,
                              reason=reason))
    _cancel_pending_termination(deal)
    # Re-review ratings following disputes. Previously approved ratings
    # are hidden, even if the employer later confirms completion again.
    for rating in deal.reviews:
        if rating.public_consent and rating.moderation_status == "approved":
            rating.moderation_status = "pending"
            rating.reviewed_at = None
            rating.reviewed_by_id = None
    deal.status = "disputed"
    opposite = deal.worker_id if owner else deal.employer.owner_user_id
    _notify(opposite, "A gig dispute is under private moderation review: " +
            deal.application.listing.title, category="warning")
    admins = User.query.filter_by(role="admin").all()
    for admin in admins:
        _notify(admin.id, "Gig dispute needs admin review (#{}).".format(deal.id),
                category="warning")
    return _success(deal, "disputed",
                    "Your private dispute was submitted to moderators. Work status is paused.")


@bp.route("/<int:deal_id>/updates", methods=["POST"])
@login_required
@limiter.limit("15 per hour")
def add_work_update(deal_id):
    """Short append-only updates, visible only to the two deal participants."""
    deal = _deal_locked(deal_id)
    owner, _worker = _participant(deal)
    if deal.status not in ("active", "completion_requested", "completed"):
        abort(409)
    body = (request.form.get("body") or "").strip()
    if not (5 <= len(body) <= 1200):
        abort(400)
    db.session.add(GigWorkUpdate(
        deal_id=deal.id, author_id=current_user.id, kind="message", body=body))
    target_id = deal.worker_id if owner else deal.employer.owner_user_id
    _notify(target_id, "A new private work update was posted for: " +
            deal.application.listing.title)
    return _success(deal, "work_update", "Work update shared with your gig partner.")


@bp.route("/<int:deal_id>/revision", methods=["POST"])
@login_required
@limiter.limit("8 per hour")
def request_revision(deal_id):
    """Clarify unfinished original scope; no unilateral new contract terms."""
    deal = _deal_locked(deal_id)
    owner, _worker = _participant(deal)
    if not owner:
        abort(403)
    if deal.status != "completion_requested" or _pending_termination(deal.id):
        abort(409)
    reason = (request.form.get("reason") or "").strip()
    if not (20 <= len(reason) <= 1200):
        abort(400)
    db.session.add(GigWorkUpdate(
        deal_id=deal.id, author_id=current_user.id,
        kind="revision_requested", body=reason))
    deal.status = "active"
    deal.completion_requested_at = None
    _notify(deal.worker_id, "Your employer requested clarification before confirming: " +
            deal.application.listing.title, category="warning")
    return _success(deal, "revision_requested",
                    "The worker has been notified. The original agreed scope and pay remain unchanged.")


@bp.route("/<int:deal_id>/termination", methods=["POST"])
@login_required
@limiter.limit("6 per hour")
def propose_termination(deal_id):
    """Offer a mutual end to an accepted gig, never a one-sided cancellation."""
    deal = _deal_locked(deal_id)
    owner, _worker = _participant(deal)
    if deal.status not in ("active", "completion_requested") or _pending_termination(deal.id):
        abort(409)
    reason = (request.form.get("reason") or "").strip()
    if not (20 <= len(reason) <= 1000):
        abort(400)
    record = GigTerminationRequest(deal_id=deal.id, proposer_id=current_user.id,
                                   reason=reason)
    db.session.add(record)
    target_id = deal.worker_id if owner else deal.employer.owner_user_id
    _notify(target_id, "A mutual cancellation proposal needs your response: " +
            deal.application.listing.title, category="warning")
    return _success(deal, "termination_proposed",
                    "Cancellation requested. The gig is NOT cancelled until the other party accepts.")


@bp.route("/<int:deal_id>/termination/<int:request_id>/respond", methods=["POST"])
@login_required
@limiter.limit("8 per hour")
def respond_termination(deal_id, request_id):
    deal = _deal_locked(deal_id)
    _participant(deal)
    item = GigTerminationRequest.query.filter_by(id=request_id, deal_id=deal.id).first_or_404()
    if current_user.id == item.proposer_id:
        abort(403)
    if item.status != "pending" or deal.status not in ("active", "completion_requested"):
        abort(409)
    decision = request.form.get("decision")
    if decision not in ("accept", "decline"):
        abort(400)
    item.status = "accepted" if decision == "accept" else "declined"
    item.respondent_id = current_user.id
    item.responded_at = datetime.utcnow()
    if decision == "accept":
        deal.status = "cancelled"
        deal.closed_at = datetime.utcnow()
    _notify(item.proposer_id,
            "Mutual cancellation was {}: {}".format(
                item.status, deal.application.listing.title))
    return _success(deal, "termination_" + item.status,
                    "Cancellation {}.".format("accepted: gig closed" if decision == "accept"
                                             else "declined: original gig stays active"))


@bp.route("/<int:deal_id>/termination/<int:request_id>/withdraw", methods=["POST"])
@login_required
@limiter.limit("8 per hour")
def withdraw_termination(deal_id, request_id):
    deal = _deal_locked(deal_id)
    _participant(deal)
    item = GigTerminationRequest.query.filter_by(id=request_id, deal_id=deal.id).first_or_404()
    if item.proposer_id != current_user.id:
        abort(403)
    if item.status != "pending" or deal.status not in ("active", "completion_requested"):
        abort(409)
    item.status = "withdrawn"
    item.responded_at = datetime.utcnow()
    other_id = deal.worker_id if deal.employer.owner_user_id == current_user.id else deal.employer.owner_user_id
    _notify(other_id, "A previous cancellation proposal was withdrawn: " +
            deal.application.listing.title)
    return _success(deal, "termination_withdrawn",
                    "Cancellation proposal withdrawn. The gig remains in progress.")


@bp.route("/<int:deal_id>/review", methods=["POST"])
@login_required
def review(deal_id):
    deal = _deal_locked(deal_id)
    owner, _worker = _participant(deal)
    if deal.status != "completed":
        abort(409)
    if GigReview.query.filter_by(deal_id=deal.id, reviewer_id=current_user.id).first():
        abort(409)
    try:
        stars = int(request.form.get("stars", ""))
    except (TypeError, ValueError):
        abort(400)
    if stars not in (1, 2, 3, 4, 5):
        abort(400)
    comment = (request.form.get("comment") or "").strip()
    if len(comment) > 500:
        abort(400)
    public_consent = bool(not owner and request.form.get("public_consent") == "yes")
    db.session.add(GigReview(
        deal_id=deal.id, reviewer_id=current_user.id,
        role="employer" if owner else "worker",
        stars=stars, comment=comment or None,
        public_consent=public_consent,
        moderation_status="pending" if public_consent else "private"))
    if public_consent:
        _notify_admin_review()
    return _success(deal, "reviewed",
                    "Rating saved. " + ("Public sharing requires moderator approval." if
                    public_consent else "Your feedback is private."))


def _notify_admin_review():
    for admin in User.query.filter_by(role="admin").all():
        if admin.is_active:
            _notify(admin.id, "A consented gig review is awaiting public-rating moderation.")


@bp.route("/<int:deal_id>/review/publish", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def publish_review(deal_id):
    """Explicit, reversible consent for older private worker reviews."""
    deal = _deal_locked(deal_id)
    _owner, worker = _participant(deal)
    if not worker:
        abort(403)
    rating = GigReview.query.filter_by(deal_id=deal.id,
                                       reviewer_id=current_user.id).first_or_404()
    if rating.role != "worker" or deal.status != "completed":
        abort(409)
    if request.form.get("public_consent") != "yes":
        abort(400)
    if rating.public_consent and rating.moderation_status in ("pending", "approved"):
        abort(409)
    rating.public_consent = True
    rating.moderation_status = "pending"
    rating.moderation_note = None
    rating.reviewed_by_id = None
    rating.reviewed_at = None
    _notify_admin_review()
    return _success(deal, "review_public_requested",
                    "Your review is still private until a moderator approves public sharing.")


@bp.route("/<int:deal_id>/review/withdraw", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def withdraw_review(deal_id):
    deal = _deal_locked(deal_id)
    _owner, worker = _participant(deal)
    if not worker:
        abort(403)
    rating = GigReview.query.filter_by(deal_id=deal.id,
                                       reviewer_id=current_user.id).first_or_404()
    if not rating.public_consent:
        abort(409)
    rating.public_consent = False
    rating.moderation_status = "private"
    rating.moderation_note = None
    rating.reviewed_by_id = None
    rating.reviewed_at = None
    return _success(deal, "review_public_withdrawn",
                    "Public sharing withdrawn. Your rating remains private.")


@bp.route("/admin/reviews")
@login_required
def admin_reviews():
    if not current_user.is_admin:
        abort(403)
    status = request.args.get("status", "pending")
    if status not in ("pending", "approved", "rejected"):
        abort(400)
    reviews = (GigReview.query.filter_by(moderation_status=status)
               .order_by(GigReview.created_at.asc()).limit(100).all())
    return render_template("gig_deals/admin_reviews.html",
                           reviews=reviews, status=status)


@bp.route("/admin/reviews/<int:review_id>", methods=["POST"])
@login_required
def moderate_review(review_id):
    if not current_user.is_admin:
        abort(403)
    rating = GigReview.query.filter_by(id=review_id).with_for_update().first_or_404()
    decision = request.form.get("decision")
    if decision not in ("approved", "rejected"):
        abort(400)
    if rating.moderation_status not in ("pending", "approved", "rejected"):
        abort(409)
    note = (request.form.get("note") or "").strip()
    if len(note) > 500 or (decision == "rejected" and len(note) < 10):
        abort(400)
    deal = rating.deal
    # A moderator cannot override privacy, fabricate completion or publish
    # an employer's rating of an individual member.
    if decision == "approved" and not (
        rating.public_consent and rating.role == "worker"
        and rating.reviewer_id == deal.worker_id
        and deal.status == "completed" and deal.completed_at is not None
        and not GigDispute.query.filter_by(deal_id=deal.id, status="open").first()
        and deal.employer.status == "approved" and deal.employer.owner.is_active
        and rating.reviewer.is_active and rating.reviewer.role == "member"
        and rating.reviewer.profile
        and rating.reviewer.profile.status == "approved"
    ):
        abort(409)
    rating.moderation_status = decision
    rating.moderation_note = note or None
    rating.reviewed_by_id = current_user.id
    rating.reviewed_at = datetime.utcnow()
    _notify(rating.reviewer_id,
            "Your optional public gig review was {} by moderation.".format(decision))
    db.session.commit()
    log_action(current_user, "gig_review." + decision, "GigReview", rating.id)
    flash("Review moderation updated.", "success")
    return redirect(url_for("gig_deals.admin_reviews", status="pending"))


@bp.route("/admin/disputes")
@login_required
def admin_disputes():
    if not current_user.is_admin:
        abort(403)
    rows = (GigDispute.query.filter_by(status="open")
            .order_by(GigDispute.created_at.asc()).limit(100).all())
    # Load a bounded history only for disputes moderators explicitly open.
    # These notes are never exposed on public job or reputation pages.
    for report in rows:
        report.deal_work_notes = (GigWorkUpdate.query.filter_by(deal_id=report.deal_id)
                                 .order_by(GigWorkUpdate.created_at.desc())
                                 .limit(30).all())
    return render_template("gig_deals/admin_disputes.html", disputes=rows)


@bp.route("/admin/disputes/<int:dispute_id>", methods=["POST"])
@login_required
def resolve_dispute(dispute_id):
    if not current_user.is_admin:
        abort(403)
    report = (GigDispute.query.filter_by(id=dispute_id)
              .with_for_update().first_or_404())
    if report.status != "open" or report.deal.status != "disputed":
        abort(409)
    action = request.form.get("action")
    note = (request.form.get("resolution") or "").strip()
    if action not in ("resume", "cancel") or not (20 <= len(note) <= 1000):
        abort(400)
    report.status = "resolved"
    report.resolution = note
    report.reviewed_by_id = current_user.id
    report.reviewed_at = datetime.utcnow()
    deal = report.deal
    # Moderators cannot falsely attest that work is completed or paid.
    _cancel_pending_termination(deal)
    deal.status = "active" if action == "resume" else "cancelled"
    if action == "cancel":
        deal.closed_at = datetime.utcnow()
    else:
        deal.completion_requested_at = None
    for uid in (deal.worker_id, deal.employer.owner_user_id):
        _notify(uid, "Gig dispute reviewed. Deal now: {}. See workspace.".format(deal.status))
    db.session.commit()
    log_action(current_user, "gig_deal.dispute_resolved", "GigDeal", deal.id)
    flash("Dispute reviewed. Both parties have been notified.", "success")
    return redirect(url_for("gig_deals.admin_disputes"))
