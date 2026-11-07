"""Regression checks for security hardening and recruitment pilot insights."""
from datetime import datetime, timedelta

import pytest
from flask import current_app

from app import create_app
from app.config import ProductionConfig
from app.extensions import db
from app.models import JobApplication
from app.services.recruitment_insights import (
    recruitment_metrics, security_readiness,
)
from tests.conftest import login
from tests.test_jobs import prepare_job, prepare_org


def test_insights_restricted_to_admin(client, member_user, admin_user):
    assert client.get("/admin/insights").status_code in (302, 401, 403)
    login(client, member_user.email)
    assert client.get("/admin/insights").status_code == 403
    client.post("/auth/logout")
    login(client, admin_user.email)
    page = client.get("/admin/insights")
    assert page.status_code == 200
    assert b"Recruitment &amp; Growth Insights" in page.data
    assert page.headers["Cache-Control"] == "private, no-store"
    assert b"Revenue collection:" in page.data
    assert b"Not implemented or verified" in page.data


def test_insights_use_real_aggregates_without_applicant_pii(
    client, db, admin_user, member_user,
):
    owner, school = prepare_org(db)
    vacancy = prepare_job(db, school)
    applicant = JobApplication(
        job_id=vacancy.id, applicant_user_id=member_user.id,
        contact_email="private-job-candidate@example.com",
        cover_note="Private cover note that must not appear in admin totals.",
        status="shortlisted",
    )
    db.session.add(applicant)
    db.session.commit()

    metrics = recruitment_metrics()
    assert metrics["kpis"]["members_total"] >= 1
    assert metrics["kpis"]["employers_total"] == 1
    assert metrics["kpis"]["schools_approved"] == 1
    assert metrics["kpis"]["vacancies_open"] == 1
    assert metrics["kpis"]["applications_total"] == 1
    assert metrics["kpis"]["applications_30d"] == 1
    assert metrics["kpis"]["applications_current_shortlisted"] == 1
    assert len(metrics["activity_weeks"]) == 4
    employer = metrics["employers"][0]
    assert employer.name == school.name
    assert employer.listing_count == 1
    assert employer.application_count == 1
    assert employer.hired_count == 0

    login(client, admin_user.email)
    body = client.get("/admin/insights").get_data(as_text=True)
    assert school.name in body
    assert "private-job-candidate@example.com" not in body
    assert "Private cover note" not in body
    assert "Revenue collection" in body
    assert "Last login within 7 days" in body
    assert "not weekly active users" in body


def test_insights_observes_last_login_not_fabricated_wau(
    db, admin_user, member_user,
):
    member_user.last_login_at = datetime.utcnow() - timedelta(days=8)
    db.session.commit()
    metrics = recruitment_metrics()
    assert metrics["kpis"]["member_last_login_7d"] == 0
    member_user.last_login_at = datetime.utcnow() - timedelta(days=2)
    db.session.commit()
    assert recruitment_metrics()["kpis"]["member_last_login_7d"] == 1


def test_login_remember_me_opt_in_and_shorter_cookie(client, member_user, app):
    from app.forms.auth_forms import LoginForm

    with app.test_request_context():
        assert LoginForm().remember_me.data is False
    assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(hours=12)
    assert app.config["REMEMBER_COOKIE_DURATION"] == timedelta(days=14)

    resp = client.post("/auth/login", data={
        "email": member_user.email, "password": "Password123",
    })
    assert resp.status_code == 302
    assert not any(
        cookie.startswith("remember_token=")
        for cookie in resp.headers.getlist("Set-Cookie")
    )
    with client.session_transaction() as session:
        assert session.permanent
    client.post("/auth/logout")

    remembered = client.post("/auth/login", data={
        "email": member_user.email, "password": "Password123", "remember_me": "y",
    })
    assert remembered.status_code == 302
    assert any(
        cookie.startswith("remember_token=")
        for cookie in remembered.headers.getlist("Set-Cookie")
    )


def test_account_login_rate_key_hides_email_and_normalizes_case(app):
    from app.blueprints.auth.routes import _account_login_rate_key

    with app.test_request_context(
        "/auth/login", method="POST",
        data={"email": "  Member@example.com  "},
    ):
        first = _account_login_rate_key()
    with app.test_request_context(
        "/auth/login", method="POST",
        data={"email": "member@EXAMPLE.COM"},
    ):
        second = _account_login_rate_key()
    with app.test_request_context(
        "/auth/login", method="POST", data={"email": "other@example.com"},
    ):
        different = _account_login_rate_key()
    assert first == second
    assert first != different
    assert len(first) > 50
    assert "member@example.com" not in first


def test_failed_login_audit_does_not_copy_attempted_email(client, db):
    from app.models import AuditLog

    posted = "private-guess@example.com"
    assert client.post("/auth/login", data={
        "email": posted, "password": "Incorrect123",
    }).status_code == 200
    entries = AuditLog.query.filter_by(action="auth.login_failed").all()
    assert entries
    assert all(posted not in (entry.detail or "") for entry in entries)


def test_strict_redis_gate_rejects_in_memory_production(monkeypatch):
    monkeypatch.setattr(ProductionConfig, "SECRET_KEY", "secure-test-key-" * 4)
    monkeypatch.setattr(ProductionConfig, "REQUIRE_SHARED_RATELIMIT", True)
    monkeypatch.setattr(ProductionConfig, "RATELIMIT_STORAGE_URI", "memory://")
    with pytest.raises(RuntimeError, match="requires a shared"):
        create_app("production")


def test_security_dashboard_never_exposes_shared_redis_credentials(app):
    config = dict(app.config)
    config["RATELIMIT_STORAGE_URI"] = "rediss://user:PRIVATE_PASSWORD@server:6380/0"
    config["REQUIRE_SHARED_RATELIMIT"] = True
    readiness = security_readiness(config)
    assert readiness["shared_ratelimiter_configured"] is True
    assert readiness["strict_ratelimiter_enforced"] is True
    assert "PRIVATE_PASSWORD" not in str(readiness)
    config["RATELIMIT_STORAGE_URI"] = "memory://"
    assert security_readiness(config)["shared_ratelimiter_configured"] is False
