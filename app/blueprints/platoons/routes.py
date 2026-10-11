"""Public on-platform platoon leaderboard with one mini rating per member."""
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.extensions import db, limiter
from app.models import Platoon, PlatoonRating
from app.models.platoon import NYSC_STATES
from app.services.audit_service import log_action
from app.services.platoon_rankings import leaderboard, MIN_MEMBERS, MIN_RATINGS

bp = Blueprint("platoons", __name__)


def _eligible_member(platoon_id):
    if not current_user.is_authenticated or current_user.role != "member" or not current_user.is_active:
        return False
    p = current_user.profile
    return bool(p and p.status == "approved"
                and p.service_stage in ("serving", "alumni")
                and p.platoon_id == platoon_id)


@bp.route("/rankings")
def rankings():
    state = request.args.get("state", "")
    if state not in NYSC_STATES:
        state = None
    raw_year = request.args.get("year", "")
    year = int(raw_year) if len(raw_year) == 4 and raw_year.isdigit() and 2020 <= int(raw_year) <= 2100 else None
    batch = request.args.get("batch", "")
    if batch not in ("A", "B", "C"):
        batch = None
    stream = request.args.get("stream", "")
    if stream not in ("I", "II"):
        stream = None
    rows = leaderboard(state=state, year=year, batch=batch, stream=stream)
    my_platoon = None
    my_vote = None
    if current_user.is_authenticated and current_user.role == "member":
        my_platoon = current_user.profile.platoon if current_user.profile else None
        rating = PlatoonRating.query.filter_by(user_id=current_user.id).first()
        if my_platoon and rating and rating.platoon_id == my_platoon.id:
            my_vote = rating.stars
    return render_template(
        "platoons/rankings.html", rows=rows, states=NYSC_STATES,
        state=state, year=year, batch=batch, stream=stream,
        my_platoon=my_platoon, my_vote=my_vote,
        can_rate=bool(my_platoon and _eligible_member(my_platoon.id)),
        min_members=MIN_MEMBERS, min_ratings=MIN_RATINGS,
    )


@bp.route("/<int:platoon_id>/rate", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def rate(platoon_id):
    """Vote only for the member's own verified NYSC cohort, one vote/person."""
    cohort = Platoon.query.get_or_404(platoon_id)
    if not _eligible_member(cohort.id):
        abort(403)
    try:
        stars = int(request.form.get("stars", ""))
    except (TypeError, ValueError):
        abort(400)
    if not 1 <= stars <= 5:
        abort(400)
    rating = PlatoonRating.query.filter_by(user_id=current_user.id).first()
    if rating is None:
        rating = PlatoonRating(user_id=current_user.id, platoon_id=cohort.id, stars=stars)
        db.session.add(rating)
    else:
        # Reassignment never allows two live ratings from one account.
        rating.platoon_id = cohort.id
        rating.stars = stars
        rating.updated_at = datetime.utcnow()
    db.session.commit()
    log_action(current_user, "platoon.rating", "Platoon", cohort.id)
    flash("Your platoon rating is saved. One rating per eligible member.", "success")
    return redirect(url_for("platoons.rankings"))
