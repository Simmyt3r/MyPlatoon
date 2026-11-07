"""Privacy-minimal operational metrics for the recruitment pilot.

Only aggregated, server-side database counts are returned. No tracking
pixel, user fingerprint, analytics cookie, external vendor, or revenue
assumptions. 'Recently logged in' is intentionally NOT a DAU/WAU metric.
"""
from datetime import datetime, timedelta
from sqlalchemy import func, distinct, case

from app.extensions import db
from app.models import User, Employer, JobListing, JobApplication


def recruitment_metrics(now=None):
    now = now or datetime.utcnow()
    past_7 = now - timedelta(days=7)
    past_30 = now - timedelta(days=30)
    today = now.date()

    kpis = {
        "members_total": User.query.filter_by(role="member").count(),
        "member_registrations_30d": User.query.filter(
            User.role == "member", User.created_at >= past_30,
        ).count(),
        "member_last_login_7d": User.query.filter(
            User.role == "member", User.last_login_at >= past_7,
        ).count(),
        "employers_total": Employer.query.count(),
        "employers_approved": Employer.query.filter_by(status="approved").count(),
        "employers_pending": Employer.query.filter_by(status="pending").count(),
        "schools_approved": Employer.query.filter_by(
            kind="school", status="approved",
        ).count(),
        "listings_published": JobListing.query.filter_by(status="published").count(),
        "listings_pending": JobListing.query.filter_by(status="pending").count(),
        "listings_created_30d": JobListing.query.filter(
            JobListing.created_at >= past_30,
        ).count(),
        "vacancies_open": JobListing.query.join(Employer).join(
            User, User.id == Employer.owner_user_id,
        ).filter(
            JobListing.status == "published", JobListing.closing_date >= today,
            Employer.status == "approved", User.is_active_account.is_(True),
            User.is_suspended.is_(False),
        ).count(),
        "applications_total": JobApplication.query.count(),
        "applications_30d": JobApplication.query.filter(
            JobApplication.created_at >= past_30,
        ).count(),
        "applications_current_shortlisted": JobApplication.query.filter_by(
            status="shortlisted",
        ).count(),
        "applications_current_hired": JobApplication.query.filter_by(
            status="hired",
        ).count(),
    }

    # PostgreSQL- and SQLite-compatible aggregated employer acquisition
    # overview. Only admins receive this data; no applicant PII is exposed.
    employers = db.session.query(
        Employer.id, Employer.name, Employer.kind, Employer.status,
        func.count(distinct(JobListing.id)).label("listing_count"),
        func.count(JobApplication.id).label("application_count"),
        func.sum(case((JobApplication.status == "hired", 1), else_=0)).label("hired_count"),
    ).outerjoin(
        JobListing, JobListing.employer_id == Employer.id,
    ).outerjoin(
        JobApplication, JobApplication.job_id == JobListing.id,
    ).group_by(
        Employer.id, Employer.name, Employer.kind, Employer.status,
    ).order_by(
        func.count(JobApplication.id).desc(), Employer.id,
    ).limit(20).all()

    activity_weeks = []
    for index in range(4):
        end = now - timedelta(days=7 * (3 - index))
        start = end - timedelta(days=7)
        activity_weeks.append({
            "label": "{}–{}".format(start.strftime("%d %b"), end.strftime("%d %b")),
            "applications": JobApplication.query.filter(
                JobApplication.created_at >= start,
                JobApplication.created_at < end,
            ).count(),
            "new_members": User.query.filter(
                User.role == "member", User.created_at >= start,
                User.created_at < end,
            ).count(),
        })

    return {
        "kpis": kpis,
        "employers": employers,
        "activity_weeks": activity_weeks,
        "as_of": now,
    }


def security_readiness(config):
    """Classify configuration without returning secrets or connection URLs."""
    uri = str(config.get("RATELIMIT_STORAGE_URI") or "memory://").lower()
    shared_limiter = not (
        uri.startswith("memory://") or uri in ("", "none", "null")
    )
    return {
        "shared_ratelimiter_configured": shared_limiter,
        "strict_ratelimiter_enforced": bool(config.get("REQUIRE_SHARED_RATELIMIT")),
        "production": not bool(config.get("TESTING")) and not bool(config.get("DEBUG")),
        "remember_cookie_days": int(config["REMEMBER_COOKIE_DURATION"].total_seconds() // 86400),
        "session_hours": int(config["PERMANENT_SESSION_LIFETIME"].total_seconds() // 3600),
    }
