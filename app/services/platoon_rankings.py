"""Transparent on-platform cohort leaderboard; not an official NYSC performance table.

Only APPROVED active serving/alumni members contribute. Public scores
aggregate cohorts; no individual profile details or identities are exposed.
Metrics are capped per person to resist spam and size-based dominance.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from sqlalchemy.orm import selectinload

from app.models import (
    Platoon, PlatoonRating, Profile, User, PPA, PPAExperience, Business,
)

MIN_MEMBERS = 3
MIN_RATINGS = 2
ACTIVITY_DAYS = 90


def leaderboard(state=None, year=None, batch=None, stream=None):
    # Enumerate all eligible real cohorts. Limiting the raw list to the
    # alphabetically first 100 would produce incorrect national ranks.
    base = Platoon.query
    if state:
        base = base.filter(Platoon.state == state)
    if year:
        base = base.filter(Platoon.service_year == year)
    if batch:
        base = base.filter(Platoon.batch == batch)
    if stream:
        base = base.filter(Platoon.stream == stream)
    cohorts = (base.order_by(Platoon.service_year.desc(), Platoon.state,
                             Platoon.batch, Platoon.stream, Platoon.number).all())
    if not cohorts:
        return []

    ids = [p.id for p in cohorts]
    profiles = (Profile.query.options(
                    selectinload(Profile.user),
                    selectinload(Profile.skills),
                    selectinload(Profile.businesses),
                ).join(User, Profile.user_id == User.id)
                .filter(Profile.platoon_id.in_(ids),
                        Profile.status == "approved",
                        Profile.service_stage.in_(("serving", "alumni")),
                        User.is_active_account.is_(True),
                        User.is_suspended.is_(False)).all())
    by_platoon = defaultdict(list)
    eligible_users = set()
    user_cohort = {}
    for member in profiles:
        by_platoon[member.platoon_id].append(member)
        eligible_users.add(member.user_id)
        user_cohort[member.user_id] = member.platoon_id

    ratings = (PlatoonRating.query.filter(PlatoonRating.platoon_id.in_(ids)).all())
    rating_by_cohort = defaultdict(list)
    for rating in ratings:
        if rating.user_id in eligible_users and user_cohort.get(rating.user_id) == rating.platoon_id:
            rating_by_cohort[rating.platoon_id].append(rating.stars)

    # One verified public contribution counts per approved member,
    # regardless of how many records that member submitted.
    contributing_users = set()
    for (uid,) in PPA.query.filter(
            PPA.status == "verified",
            PPA.submitted_by_id.in_(eligible_users)).with_entities(PPA.submitted_by_id).all():
        contributing_users.add(uid)
    for (uid,) in PPAExperience.query.filter(
            PPAExperience.status == "verified",
            PPAExperience.submitted_by_id.in_(eligible_users)).with_entities(
            PPAExperience.submitted_by_id).all():
        contributing_users.add(uid)
    # Active registered businesses count once per individual owner;
    # jobs applied for do NOT count (private candidate information).
    for (uid,) in Business.query.join(Profile, Business.profile_id == Profile.id).filter(
            Profile.user_id.in_(eligible_users), Business.is_active.is_(True)
            ).with_entities(Profile.user_id).all():
        contributing_users.add(uid)

    recent = datetime.utcnow() - timedelta(days=ACTIVITY_DAYS)
    result = []
    for cohort in cohorts:
        members = by_platoon[cohort.id]
        n = len(members)
        stars = rating_by_cohort[cohort.id]
        rated = len(stars)
        # Bayesian smoothing: a handful of perfect votes cannot defeat
        # a mature cohort with many genuine community evaluations.
        smoothed_stars = (sum(stars) + 5 * 3.5) / (rated + 5)
        shown_stars = (sum(stars) / rated) if rated else None
        completed = sum(1 for m in members if m.completion_percent() >= 60)
        active = sum(1 for m in members if m.updated_at and m.updated_at >= recent)
        contributing = sum(1 for m in members if m.user_id in contributing_users)
        # All metrics are normalised by eligible membership size, NOT raw
        # activity counts. 30/25/20/25 max = 100 points.
        score = round(
            30 * completed / n + 25 * active / n +
            20 * contributing / n + 25 * smoothed_stars / 5, 1
        ) if n else 0
        qualified = n >= MIN_MEMBERS and rated >= MIN_RATINGS
        result.append({
            "platoon": cohort, "members": n, "ratings": rated,
            "stars": round(shown_stars, 2) if shown_stars is not None else None,
            "score": score, "qualified": qualified,
            "completed": completed, "active": active, "contributors": contributing,
        })

    # Provisional groups follow ranked cohorts regardless of apparent score.
    result.sort(key=lambda row: (
        not row["qualified"], -row["score"], -row["members"], row["platoon"].id))
    for i, row in enumerate([r for r in result if r["qualified"]], start=1):
        row["rank"] = i
    for row in result:
        row.setdefault("rank", None)
    return result
