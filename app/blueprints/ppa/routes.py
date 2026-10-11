"""Community-sourced PPA lookup and moderation, not an official NYSC listing."""
from datetime import datetime

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import func

from app.extensions import db, limiter
from app.forms.ppa_forms import PPAForm, PPAReviewForm, PPAExperienceForm
from app.models import PPA, PPAExperience, PPA_SECTORS, NYSC_STATES
from app.services.audit_service import log_action
from app.services.notification_service import notify
from app.services.ppa_geo import (
    filter_local_near, lookup_query, public_feature, valid_near,
)

bp = Blueprint("ppa", __name__)


def _filters():
    q = request.args.get("q", "").strip()[:80]
    state = request.args.get("state", "")
    sector = request.args.get("sector", "")
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    radius = request.args.get("radius", 20, type=float)

      # Radius alone is harmless: the form pre-selects a radius but has no
    # "nearby" search until both coordinates are explicitly given.
    if "lat" in request.args or "lng" in request.args:
        if not valid_near(lat, lng, radius):
            abort(400)
    else:
        lat = lng = radius = None
    return dict(q=q, state=state, sector=sector, lat=lat, lng=lng, radius_km=radius)


def _can_submit():
    if not current_user.is_authenticated or not current_user.is_active:
        return False
    if current_user.is_admin:
        return True
    p = current_user.profile
    return bool(p and p.status == "approved" and p.platoon_id and
                p.service_stage in ("serving", "alumni"))


def _apply_form(ppa, form):
    ppa.name = " ".join(form.name.data.strip().split())
    ppa.name_key = PPA.normalize_name(ppa.name)
    ppa.state = form.state.data
    ppa.lga = " ".join(form.lga.data.strip().split())
    ppa.town = (form.town.data or "").strip() or None
    ppa.address = (form.address.data or "").strip() or None
    ppa.sector = form.sector.data
    ppa.website = (form.website.data or "").strip() or None
    ppa.accommodation = form.accommodation.data
    ppa.allowance = form.allowance.data
    ppa.experience_notes = (form.experience_notes.data or "").strip() or None
    ppa.latitude = float(form.latitude.data) if form.latitude.data is not None else None
    ppa.longitude = float(form.longitude.data) if form.longitude.data is not None else None


def _duplicate(ppa, form):
    lookup = PPA.query.filter_by(
        name_key=PPA.normalize_name(form.name.data), state=form.state.data
    ).filter(func.lower(PPA.lga) == form.lga.data.strip().lower())
    if ppa.id:
        lookup = lookup.filter(PPA.id != ppa.id)
    return lookup.first()


@bp.route("/")
def index():
    filters = _filters()
    query = lookup_query(**filters).order_by(PPA.name.asc())
    page = max(1, request.args.get("page", 1, type=int))
    pagination = None
    if filters["lat"] is not None and db.engine.dialect.name != "postgresql":
        # In-memory exact haversine refinement is used for local SQLite tests.
        # Production always uses ST_DWithin on an indexed PostGIS expression.
        matches = filter_local_near(
            query.limit(500).all(), filters["lat"], filters["lng"], filters["radius_km"])
        entries = matches[(page-1)*12:page*12]
        total = len(matches)
    else:
        pagination = query.paginate(page=page, per_page=12, error_out=False)
        entries, total = pagination.items, pagination.total
    return render_template(
        "ppa/index.html", entries=entries, total=total, pagination=pagination,
        filters=filters, states=NYSC_STATES, sectors=PPA_SECTORS, can_submit=_can_submit(),
    )


@bp.route("/geojson")
@limiter.limit("60 per hour")
def geojson():
    filters = _filters()
    query = lookup_query(**filters).filter(
        PPA.latitude.isnot(None), PPA.longitude.isnot(None)
    )
    # Deliberate response cap; full nationwide tiling/cluster paging is a
    # future feature. No reporter identifiers or coordinates of residences.
    rows = query.order_by(PPA.id.asc()).limit(251).all()
    rows = filter_local_near(
        rows, filters["lat"], filters["lng"], filters["radius_km"])
    features = [f for p in rows[:250] if (f := public_feature(p)) is not None]
    response = jsonify({"type": "FeatureCollection", "features": features,
                        "truncated": len(rows) > 250})
    response.headers["Cache-Control"] = "public, max-age=60"
    return response


@bp.route("/<int:ppa_id>")
def detail(ppa_id):
    ppa = PPA.query.get_or_404(ppa_id)
    owned = (current_user.is_authenticated and ppa.submitted_by_id == current_user.id)
    admin = current_user.is_authenticated and current_user.is_admin
    if ppa.status != "verified" and not (owned or admin):
        abort(404)
    experiences = (ppa.experiences.filter_by(status="verified")
                   .order_by(PPAExperience.service_year.desc()).limit(20).all())
    return render_template("ppa/detail.html", ppa=ppa, owned=owned, admin=admin,
                           experiences=experiences, can_submit=_can_submit())


@bp.route("/mine")
@login_required
def mine():
    entries = PPA.query.filter_by(submitted_by_id=current_user.id).order_by(
        PPA.created_at.desc()).limit(100).all()
    return render_template("ppa/mine.html", entries=entries)


@bp.route("/new", methods=["GET", "POST"])
@login_required
@limiter.limit("10 per day", methods=["POST"])
def create():
    if not _can_submit():
        flash("Complete and obtain approval for your NYSC member profile and platoon before submitting PPAs.", "warning")
        return redirect(url_for("profile.dashboard"))
    form = PPAForm()
    if form.validate_on_submit():
        ppa = PPA(submitted_by_id=current_user.id)
        if _duplicate(ppa, form):
            form.name.errors.append("This PPA is already listed for that state and LGA. Search it first.")
        else:
            _apply_form(ppa, form)
            db.session.add(ppa)
            db.session.commit()
            log_action(current_user, "ppa.submit", "PPA", ppa.id)
            flash("PPA submitted for moderator review. It is not public yet.", "success")
            return redirect(url_for("ppa.mine"))
    return render_template("ppa/form.html", form=form, ppa=None)


@bp.route("/<int:ppa_id>/edit", methods=["GET", "POST"])
@login_required
@limiter.limit("20 per day", methods=["POST"])
def edit(ppa_id):
    ppa = PPA.query.get_or_404(ppa_id)
    if ppa.submitted_by_id != current_user.id and not current_user.is_admin:
        abort(403)
    form = PPAForm(obj=ppa)
    if form.validate_on_submit():
        if _duplicate(ppa, form):
            form.name.errors.append("A PPA with that name, state and LGA already exists.")
        else:
            _apply_form(ppa, form)
            # Material change always removes the public listing pending review.
            ppa.status = "pending"
            ppa.verified_at = None
            ppa.verified_by_id = None
            ppa.rejection_reason = None
            db.session.commit()
            log_action(current_user, "ppa.update", "PPA", ppa.id)
            flash("Your changes have been submitted for review.", "success")
            return redirect(url_for("ppa.detail", ppa_id=ppa.id))
    return render_template("ppa/form.html", form=form, ppa=ppa)


@bp.route("/review")
@login_required
def review_queue():
    if not current_user.is_admin:
        abort(403)
    status = request.args.get("status", "pending")
    if status not in ("pending", "verified", "rejected"):
        status = "pending"
    entries = PPA.query.filter_by(status=status).order_by(
        PPA.updated_at.asc()).limit(100).all()
    return render_template("ppa/review.html", entries=entries, status=status,
                           review_form=PPAReviewForm())


@bp.route("/<int:ppa_id>/review", methods=["POST"])
@login_required
@limiter.limit("120 per hour", methods=["POST"])
def review(ppa_id):
    if not current_user.is_admin:
        abort(403)
    form = PPAReviewForm()
    if not form.validate_on_submit():
        abort(400)
    ppa = PPA.query.get_or_404(ppa_id)
    decision = request.form.get("decision")
    if decision not in ("verified", "rejected"):
        abort(400)
    if decision == "rejected" and not (form.reason.data or "").strip():
        flash("Please enter a reason before rejecting a PPA.", "warning")
        return redirect(url_for("ppa.review_queue"))
    ppa.status = decision
    ppa.verified_by_id = current_user.id
    ppa.verified_at = datetime.utcnow() if decision == "verified" else None
    ppa.rejection_reason = (form.reason.data or "").strip() if decision == "rejected" else None
    db.session.commit()
    log_action(current_user, "ppa.review_" + decision, "PPA", ppa.id)
    if ppa.submitter:
        notify(ppa.submitter, "Your PPA report for {} was {}.".format(
            ppa.name, "approved for public lookup" if decision == "verified" else "returned for correction"),
            category="success" if decision == "verified" else "warning")
    flash("PPA " + ("approved" if decision == "verified" else "rejected") + ".", "success")
    return redirect(url_for("ppa.review_queue"))



@bp.route("/<int:ppa_id>/experience", methods=["GET", "POST"])
@login_required
@limiter.limit("15 per day", methods=["POST"])
def contribute_experience(ppa_id):
    ppa = PPA.query.get_or_404(ppa_id)
    if ppa.status != "verified":
        abort(404)
    if not _can_submit():
        flash("Only approved serving corps members and alumni can contribute PPA experiences.", "warning")
        return redirect(url_for("ppa.detail", ppa_id=ppa_id))

    existing = PPAExperience.query.filter_by(
        ppa_id=ppa.id, submitted_by_id=current_user.id).first()
    form = PPAExperienceForm(obj=existing)
    if form.validate_on_submit():
        report = existing or PPAExperience(
            ppa_id=ppa.id, submitted_by_id=current_user.id)
        report.service_year = form.service_year.data
        report.accommodation = form.accommodation.data
        report.allowance = form.allowance.data
        report.notes = (form.notes.data or "").strip() or None
        report.status = "pending"
        report.rejection_reason = None
        report.verified_by_id = None
        if existing is None:
            db.session.add(report)
        db.session.commit()
        log_action(current_user, "ppa.experience_submit", "PPAExperience", report.id)
        flash("Your experience has been sent for moderation.", "success")
        return redirect(url_for("ppa.detail", ppa_id=ppa.id))
    return render_template("ppa/experience_form.html", form=form, ppa=ppa,
                           existing=existing)


@bp.route("/review/experiences")
@login_required
def experience_queue():
    if not current_user.is_admin:
        abort(403)
    status = request.args.get("status", "pending")
    if status not in ("pending", "verified", "rejected"):
        status = "pending"
    reports = (PPAExperience.query.filter_by(status=status)
               .order_by(PPAExperience.updated_at.asc()).limit(100).all())
    return render_template("ppa/review_experiences.html", reports=reports,
                           status=status, review_form=PPAReviewForm())


@bp.route("/experience/<int:report_id>/review", methods=["POST"])
@login_required
@limiter.limit("120 per hour", methods=["POST"])
def review_experience(report_id):
    if not current_user.is_admin:
        abort(403)
    form = PPAReviewForm()
    if not form.validate_on_submit():
        abort(400)
    report = PPAExperience.query.get_or_404(report_id)
    decision = request.form.get("decision")
    if decision not in ("verified", "rejected"):
        abort(400)
    reason = (form.reason.data or "").strip()
    if decision == "rejected" and not reason:
        flash("Provide a reason for rejecting a report.", "warning")
        return redirect(url_for("ppa.experience_queue"))
    report.status = decision
    report.verified_by_id = current_user.id
    report.rejection_reason = reason if decision == "rejected" else None
    db.session.commit()
    log_action(current_user, "ppa.experience_review_" + decision,
               "PPAExperience", report.id)
    if report.submitter:
        notify(report.submitter, "Your experience report for {} was {}.".format(
            report.ppa.name, "approved" if decision == "verified" else "returned for correction"),
            category="success" if decision == "verified" else "warning")
    flash("Experience reviewed.", "success")
    return redirect(url_for("ppa.experience_queue"))
