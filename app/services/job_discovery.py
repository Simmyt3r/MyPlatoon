"""Transparent personalised job ranking and explicitly opted-in IN-APP alerts.

Uses NYSC service state (not state of origin) and self-declared skills;
never tracks GPS/home location or automatically shares personal profiles.
"""
import re
from datetime import date, datetime

from app.extensions import db
from app.models import (
    Employer, JobListing, JobAlertPreference, JobAlertDelivery,
    Notification, Profile, User,
)

SUGGESTION_LIMIT = 24


def service_state(profile):
    return profile.platoon.state if profile and profile.platoon else None


def member_eligible(user):
    return bool(user and user.is_active and user.role == "member"
                and user.profile and user.profile.status == "approved")


def _words(text):
    return {w.casefold() for w in re.findall(r"[A-Za-z][A-Za-z0-9+#]{2,}", text or "")}


def match_score(profile, job, preference=None):
    """Deterministic 0-100 suitability heuristic, not a hiring decision.

    Return None when a member explicitly excludes the vacancy.
    """
    if not profile or profile.status != "approved":
        return None
    if job.serving_only and profile.service_stage != "serving":
        return None
    if preference:
        kinds = {v for v in (preference.preferred_kinds or "").split(",") if v}
        if kinds and job.job_kind not in kinds:
            return None
        if job.work_mode == "remote" and not preference.remote_ok:
            return None
        if (preference.available_hours and job.hours_per_week
                and job.hours_per_week > preference.available_hours):
            return None

    # User-defined preferred state takes precedence over actual posting state.
    state = ((preference.preferred_state if preference and preference.preferred_state else None)
             or service_state(profile))
    if job.work_mode != "remote" and state and job.state != state:
        return None

    score = 10
    if job.work_mode == "remote":
        score += 26
    elif state and job.state == state:
        score += 34

    if job.job_kind in ("gig", "part_time"):
        score += 15
    elif job.job_kind == "internship":
        score += 10

    if profile.service_stage == "serving" and job.serving_only:
        score += 8

    if preference and preference.available_hours and job.hours_per_week:
        score += 8 if job.hours_per_week <= preference.available_hours else 0
    elif job.hours_per_week and job.hours_per_week <= 16:
        score += 6

    advertised = _words(job.title + " " + job.requirements)
    self_declared = set()
    for skill in profile.skills:
        self_declared.update(_words(skill.name))
    self_declared.update(_words(profile.profession))
    overlap = advertised & self_declared
    score += min(25, len(overlap) * 9)

    return min(score, 100)


def visible_jobs():
    return (JobListing.query.join(Employer).join(User, Employer.owner_user_id == User.id)
            .filter(JobListing.status == "published", Employer.status == "approved",
                    JobListing.closing_date >= date.today(),
                    User.is_active_account.is_(True), User.is_suspended.is_(False)))


def recommended_jobs(user, limit=SUGGESTION_LIMIT):
    if not member_eligible(user):
        return []
    pref = JobAlertPreference.query.filter_by(user_id=user.id).first()
    # Bounded discovery for predictable serverless memory; site can
    # paginate public postings independently. Never expose hidden posts.
    jobs = visible_jobs().order_by(JobListing.created_at.desc()).limit(300).all()
    ranked = []
    for job in jobs:
        score = match_score(user.profile, job, pref)
        if score is not None:
            ranked.append((job, score))
    ranked.sort(key=lambda pair: (-pair[1], -pair[0].id))
    return ranked[:limit]


def dispatch_job_alerts(job):
    """On admin publication, send matching opted-in in-app alerts once.

    This is not SMS, email, background polling or a claim of nearby GPS
    distance. Delivery is idempotent per (user, job). Run only for
    published, public listings.
    """
    if not job.is_open:
        return 0
    sent = 0
    prefs = (JobAlertPreference.query.filter_by(enabled=True)
             .join(User, JobAlertPreference.user_id == User.id)
             .filter(User.role == "member",
                     User.is_active_account.is_(True),
                     User.is_suspended.is_(False)).all())
    for pref in prefs:
        user = db.session.get(User, pref.user_id)
        if not member_eligible(user):
            continue
        if JobAlertDelivery.query.filter_by(user_id=user.id, job_id=job.id).first():
            continue
        score = match_score(user.profile, job, pref)
        if score is None or score < 38:
            continue
        db.session.add(JobAlertDelivery(user_id=user.id, job_id=job.id))
        db.session.add(Notification(
            user_id=user.id,
            message="New Jobs & Gigs opportunity: " + job.title[:170],
            category="info",
        ))
        sent += 1
    if sent:
        db.session.commit()
    return sent
