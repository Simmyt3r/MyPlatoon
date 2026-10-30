"""Cloudinary connection tests using the administrator's saved credentials.

No live network calls or asset modifications are made in CI.
"""
import re

import cloudinary.api
import cloudinary.uploader

from tests.conftest import login
from tests.test_cloudinary_profile_upload import _save_admin_cloudinary


def test_setup_renders_admin_connection_test_only_for_admin(client, admin_user, member_user):
    assert b"Test Cloudinary connection" not in client.get("/setup", follow_redirects=True).data
    login(client, member_user.email)
    assert client.get("/setup").status_code == 403
    client.post("/auth/logout")

    login(client, admin_user.email)
    page = client.get("/setup")
    assert page.status_code == 200
    assert b"Test Cloudinary connection" in page.data
    assert b'name="action" value="cloudinary_test"' in page.data
    assert b'name="csrf_token"' in page.data


def test_admin_cloudinary_ping_uses_saved_credentials_without_asset_upload(
    client, app, admin_user, db, monkeypatch,
):
    _save_admin_cloudinary(app, admin_user)
    credentials = {}
    calls = []

    def fake_config(**options):
        credentials.update(options)

    def fake_ping():
        calls.append("ping")
        return {"status": "ok"}

    def forbidden(*args, **kwargs):
        raise AssertionError("Connection test must not modify assets")

    monkeypatch.setattr("cloudinary.config", fake_config)
    monkeypatch.setattr(cloudinary.api, "ping", fake_ping)
    monkeypatch.setattr(cloudinary.uploader, "upload", forbidden)
    monkeypatch.setattr(cloudinary.uploader, "destroy", forbidden)

    from app.models import SiteSecret, AuditLog
    before = [(s.key, s.ciphertext) for s in SiteSecret.query.all()]

    login(client, admin_user.email)
    response = client.post("/setup", data={
        "action": "cloudinary_test",
        "admin_password": "Password123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Cloudinary connection verified successfully" in response.data
    assert calls == ["ping"]
    assert credentials == {
        "cloud_name": "unit-test-cloud",
        "api_key": "unit-test-api-key",
        "api_secret": "unit-test-api-secret",
        "secure": True,
    }
    assert before == [(s.key, s.ciphertext) for s in SiteSecret.query.all()]
    assert AuditLog.query.filter_by(action="integrations.test").count() == 1


def test_cloudinary_ping_refuses_wrong_admin_password(client, admin_user, monkeypatch):
    def forbidden():
        raise AssertionError("Bad password must never call Cloudinary")

    monkeypatch.setattr(cloudinary.api, "ping", forbidden)
    login(client, admin_user.email)
    response = client.post("/setup", data={
        "action": "cloudinary_test",
        "admin_password": "incorrect",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"password verification failed" in response.data


def test_cloudinary_ping_failure_does_not_expose_secrets(
    client, app, admin_user, monkeypatch,
):
    _save_admin_cloudinary(app, admin_user)
    secret = "CLOUDINARY_PRIVATE_TEST_KEY_SHOULD_NEVER_APPEAR"

    def failed_ping():
        raise RuntimeError(secret)

    monkeypatch.setattr(cloudinary.api, "ping", failed_ping)
    login(client, admin_user.email)
    response = client.post("/setup", data={
        "action": "cloudinary_test", "admin_password": "Password123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Cloudinary connection test failed" in response.data
    assert secret.encode() not in response.data
    assert b"unit-test-api-secret" not in response.data


def test_cloudinary_ping_missing_settings_reports_configuration_issue(
    client, app, admin_user, monkeypatch,
):
    from app.services import site_secrets

    for key in site_secrets.ALLOWED_KEYS:
        app.config[key] = None

    monkeypatch.setattr(
        cloudinary.api, "ping",
        lambda: (_ for _ in ()).throw(AssertionError("No config; do not ping")),
    )
    login(client, admin_user.email)
    response = client.post("/setup", data={
        "action": "cloudinary_test", "admin_password": "Password123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"Image storage is not configured" in response.data


def test_cloudinary_ping_unexpected_status_is_safe(
    client, app, admin_user, monkeypatch,
):
    _save_admin_cloudinary(app, admin_user)
    monkeypatch.setattr(cloudinary.api, "ping", lambda: {"status": "degraded"})
    login(client, admin_user.email)
    response = client.post("/setup", data={
        "action": "cloudinary_test", "admin_password": "Password123",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"did not confirm a healthy API connection" in response.data
    assert b"unit-test-api-secret" not in response.data


def test_cloudinary_admin_test_requires_https_csrf_token(
    client, app, admin_user, monkeypatch,
):
    monkeypatch.setattr(cloudinary.api, "ping", lambda: {"status": "ok"})
    # Log in with CSRF disabled (fixture convention), using the SAME host
    # as the HTTPS setup request so the session cookie remains available.
    auth = client.post(
        "/auth/login", base_url="https://myplatoon.vercel.app",
        data={"email": admin_user.email, "password": "Password123"},
    )
    assert auth.status_code == 302
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.get("/setup", base_url="https://myplatoon.vercel.app")
    assert page.status_code == 200
    match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    assert match is not None

    without_csrf = client.post(
        "/setup", base_url="https://myplatoon.vercel.app",
        headers={"Referer": "https://myplatoon.vercel.app/setup"},
        data={"action": "cloudinary_test", "admin_password": "Password123"},
    )
    assert without_csrf.status_code == 400

    with_csrf = client.post(
        "/setup", base_url="https://myplatoon.vercel.app",
        headers={"Referer": "https://myplatoon.vercel.app/setup"},
        data={
            "csrf_token": match.group(1).decode(),
            "action": "cloudinary_test",
            "admin_password": "Password123",
        },
    )
    assert with_csrf.status_code == 302
