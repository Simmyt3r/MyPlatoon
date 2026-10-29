"""Operator-only setup, schema and encrypted API key regression tests."""
from app.extensions import db as shared_db
from app.models import SiteSecret
from app.services.site_secrets import cloudinary_credentials
from tests.conftest import login


def test_setup_first_visit_requires_secret_and_never_creates_admin(client, app, db):
    app.config["SETUP_TOKEN"] = "t" * 40
    response = client.get("/setup")
    assert response.status_code == 200
    assert b"FIRST-TIME ONLY" in response.data
    response = client.post("/setup", data={
        "setup_token": "wrong-token",
        "name": "First Admin", "email": "admin@example.com",
        "password": "strong-example-password-123",
        "backup_confirm": "yes",
    })
    assert response.status_code == 302
    from app.models import User
    assert User.query.filter_by(role="admin").count() == 0


def test_setup_locks_first_run_once_admin_exists(client, admin_user, member_user):
    assert client.get("/setup").status_code == 302
    login(client, "member@example.com")
    assert client.get("/setup").status_code == 403

    # Sign out securely before changing user.
    client.post("/auth/logout")
    login(client, "admin@example.com")
    page = client.get("/setup")
    assert page.status_code == 200
    assert b"ADMINISTRATOR ONLY" in page.data
    assert b'csrf_token' in page.data
    assert b"FIRST-TIME ONLY" not in page.data


def test_setup_rejects_bad_admin_password_for_migration(client, admin_user):
    login(client, "admin@example.com")
    response = client.post("/setup", data={
        "action": "upgrade",
        "admin_password": "incorrect",
        "backup_confirm": "yes", "confirmation": "MIGRATE MYPLATOON",
    }, follow_redirects=True)
    assert b"password verification failed" in response.data
    assert db_has_no_alembic_version()


def db_has_no_alembic_version():
    from app.services.schema_manager import current_revision
    return current_revision() is None


def test_cloudinary_credentials_are_encrypted_and_hidden(client, admin_user, app):
    app.config["SECRET_KEY"] = "test-only-strong-secret-" + "r" * 40
    login(client, "admin@example.com")
    response = client.post("/setup", data={
        "action": "cloudinary",
        "admin_password": "Password123",
        "CLOUDINARY_CLOUD_NAME": "my-cloud",
        "CLOUDINARY_API_KEY": "12345678",
        "CLOUDINARY_API_SECRET": "confidential-key-value",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"settings saved securely" in response.data
    assert b"confidential-key-value" not in response.data
    rows = SiteSecret.query.all()
    assert len(rows) == 3
    assert all("confidential-key-value" not in row.ciphertext for row in rows)
    assert cloudinary_credentials()["CLOUDINARY_API_SECRET"] == "confidential-key-value"

    response = client.post("/setup", data={
        "action": "cloudinary", "admin_password": "Password123",
        "CLOUDINARY_CLOUD_NAME": "updated-cloud"
    })
    assert response.status_code == 302
    values = cloudinary_credentials()
    assert values["CLOUDINARY_CLOUD_NAME"] == "updated-cloud"
    assert values["CLOUDINARY_API_SECRET"] == "confidential-key-value"


def test_setup_requires_valid_password_to_change_keys(client, admin_user, app):
    app.config["SECRET_KEY"] = "a" * 64
    login(client, "admin@example.com")
    client.post("/setup", data={
        "action": "cloudinary", "admin_password": "wrong",
        "CLOUDINARY_API_SECRET": "dont-save"
    })
    assert SiteSecret.query.count() == 0


def test_migration_runs_on_fresh_database(monkeypatch):
    from app import create_app
    from app.config import TestingConfig
    from app.services.schema_manager import upgrade_to_head, current_revision
    from scripts.check_release_schema import EXPECTED_REVISION
    monkeypatch.setattr(TestingConfig, "AUTO_CREATE_TABLES", False)
    app = create_app("testing")
    with app.app_context():
        try:
            assert current_revision() is None
            assert upgrade_to_head() == EXPECTED_REVISION
            assert current_revision() == EXPECTED_REVISION
            # A repeated deployment/migration is an idempotent no-op.
            assert upgrade_to_head() == EXPECTED_REVISION
        finally:
            shared_db.session.remove()
            shared_db.drop_all()


def test_aiven_setup_reports_missing_env_without_secrets(client, app, monkeypatch):
    """The production-only setup guard explains what is wrong, not the DSN."""
    monkeypatch.delenv("AIVEN_DATABASE_URL", raising=False)
    app.config.update(TESTING=False, DEBUG=False)
    response = client.get("/setup")
    assert response.status_code == 503
    assert b"AIVEN_DATABASE_URL is missing" in response.data
    assert b"connection diagnostics v2" in response.data


def test_aiven_setup_validates_database_and_tls(client, app, monkeypatch):
    """Wrong database and missing SSL fail with actionable, sanitized errors."""
    app.config.update(TESTING=False, DEBUG=False)
    cases = (
        ("postgresql://user:do-not-print@host.example:5432/defaultdb?sslmode=require",
         b"not targeting database", 503),
        ("postgresql://user:do-not-print@host.example:5432/myplatoon",
         b"missing a supported sslmode", 503),
        ("mysql://user:do-not-print@host.example:5432/myplatoon?sslmode=require",
         b"not a PostgreSQL connection", 503),
        ("postgresql://user:do-not-print@host.example:5432/myplatoon?sslmode=require",
         b"FIRST-TIME ONLY", 200),
        ("postgres://user:do-not-print@host.example:5432/myplatoon?sslmode=require",
         b"FIRST-TIME ONLY", 200),
    )
    for url, expected, status in cases:
        monkeypatch.setenv("AIVEN_DATABASE_URL", url)
        response = client.get("/setup")
        assert response.status_code == status
        assert expected in response.data
        assert b"do-not-print" not in response.data


def test_aiven_setup_sanitizes_invalid_url(client, app, monkeypatch):
    app.config.update(TESTING=False, DEBUG=False)
    monkeypatch.setenv("AIVEN_DATABASE_URL", "secret-should-never-appear")
    response = client.get("/setup")
    assert response.status_code == 503
    assert b"cannot be parsed" in response.data
    assert b"secret-should-never-appear" not in response.data


def test_aiven_failure_categories_never_expose_connection_details():
    from types import SimpleNamespace
    from app.services.aiven_diagnostics import diagnose_database_error

    secret = "PASSWORD-NEVER-ECHO-THIS"
    cases = (
        (SimpleNamespace(pgcode="28P01"), "DB_AUTH"),
        (SimpleNamespace(pgcode="3D000"), "DB_MISSING"),
        (SimpleNamespace(pgcode="42501"), "DB_PERMISSIONS"),
        (SimpleNamespace(pgcode="53300"), "DB_LIMIT"),
        (Exception(f"password authentication failed for user secretuser {secret}"), "DB_AUTH"),
        (Exception(f"could not translate host name secret-host {secret}"), "DB_DNS"),
        (Exception(f"connection timed out on host secret-host {secret}"), "DB_TIMEOUT"),
        (Exception(f"connection refused on host secret-host {secret}"), "DB_REFUSED"),
        (Exception(f"SSL error: certificate verify failed {secret}"), "DB_TLS"),
        (Exception(f"no pg_hba.conf entry for host secret-host {secret}"), "DB_ACCESS"),
        (Exception(f"unknown private error {secret}"), "DB_OTHER"),
    )
    for exc, expected_code in cases:
        code, summary, guidance = diagnose_database_error(exc)
        assert code == expected_code
        assert summary and guidance
        assert secret not in (code + summary + guidance)
        assert "secret-host" not in (code + summary + guidance)
        assert "secretuser" not in (code + summary + guidance)


def test_setup_connection_error_explains_cause_without_secret(client, app, monkeypatch):
    from app.blueprints.setup import routes

    secret = "NOT-IN-RESPONSE-OR-LOGS"
    app.config.update(TESTING=False, DEBUG=False)
    monkeypatch.setenv(
        "AIVEN_DATABASE_URL",
        "postgresql://user:placeholder@host.example:5432/myplatoon?sslmode=require",
    )

    def fail_connection():
        raise RuntimeError(f"could not translate host name {secret}")

    monkeypatch.setattr(routes, "_has_admin", fail_connection)
    result = client.get("/setup")
    assert result.status_code == 503
    assert b"DB_DNS" in result.data
    assert b"Connection diagnostics v3" in result.data
    assert secret.encode() not in result.data
    assert b"FIRST-TIME ONLY" not in result.data


def test_setup_connection_error_handles_unknown_errors(client, app, monkeypatch):
    from app.blueprints.setup import routes
    app.config.update(TESTING=False, DEBUG=False)
    monkeypatch.setenv(
        "AIVEN_DATABASE_URL",
        "postgresql://user:placeholder@host.example:5432/myplatoon?sslmode=require",
    )
    monkeypatch.setattr(
        routes, "_has_admin",
        lambda: (_ for _ in ()).throw(Exception("sensitive internal details")),
    )
    result = client.get("/setup")
    assert result.status_code == 503
    assert b"DB_OTHER" in result.data
    assert b"sensitive internal details" not in result.data


def test_setup_missing_csrf_explains_rejection_without_exposing_secrets(client, app, db):
    """A missing form token must be rejected, not treated as DB failure."""
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["SETUP_TOKEN"] = "secret-token-" + "a" * 40
    response = client.post("/setup", data={
        "setup_token": app.config["SETUP_TOKEN"],
        "name": "Demo Admin",
        "email": "demo@example.com",
        "password": "secure-test-password-1234",
        "backup_confirm": "yes",
    })
    assert response.status_code == 400
    assert b"Setup form security check failed" in response.data
    assert b"token was missing" in response.data
    assert b"Setup form diagnostics v6" in response.data
    assert app.config["SETUP_TOKEN"].encode() not in response.data
    from app.models import User
    assert User.query.filter_by(email="demo@example.com").first() is None


def test_setup_invalid_csrf_renders_safe_recovery(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/setup", data={"csrf_token": "not-a-valid-csrf-token"})
    assert response.status_code == 400
    assert b"Setup form security check failed" in response.data
    assert b"fresh setup page" in response.data
    assert b"not-a-valid-csrf-token" not in response.data


def test_setup_valid_csrf_still_requires_one_time_token(client, app):
    import re
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["SETUP_TOKEN"] = "secret-token-" + "b" * 40
    page = client.get("/setup")
    assert page.status_code == 200
    csrf_value = re.search(
        rb'name="csrf_token" value="([^"]+)"', page.data,
    )
    assert csrf_value is not None
    response = client.post("/setup", data={
        "csrf_token": csrf_value.group(1).decode("ascii"),
        "setup_token": "invalid-setup-token",
        "name": "Demo Admin",
        "email": "demo@example.com",
        "password": "secure-test-password-1234",
        "backup_confirm": "yes",
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup")


def test_admin_invalid_setup_operation_reports_action_error(client, admin_user):
    login(client, "admin@example.com")
    response = client.post("/setup", data={
        "action": "unsupported-action",
        "admin_password": "Password123",
    })
    assert response.status_code == 400
    assert b"setup action was not recognized" in response.data


def test_setup_form_probe_passes_with_valid_csrf_and_never_runs_migrations(client, app, monkeypatch):
    import re
    from app.blueprints.setup import routes
    app.config["WTF_CSRF_ENABLED"] = True

    def forbid_migrations(*args, **kwargs):
        raise AssertionError("probe must not touch schema upgrade")

    monkeypatch.setattr(routes, "upgrade_to_head", forbid_migrations)
    page = client.get("/setup")
    csrf_value = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    assert csrf_value is not None

    response = client.post("/setup/form-check", data={
        "csrf_token": csrf_value.group(1).decode("ascii"),
    })
    assert response.status_code == 200
    assert b"Form security check passed" in response.data
    assert b"No database connection or migration was attempted" in response.data


def test_setup_form_probe_missing_csrf_rejected_with_transport_diagnosis(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/setup/form-check", data={
        "marker": "sensitive-value-that-must-not-be-reflected",
    })
    assert response.status_code == 400
    assert b"CSRF_FIELD_OMITTED" in response.data
    assert b"Setup form diagnostics v6" in response.data
    assert b"sensitive-value-that-must-not-be-reflected" not in response.data


def test_setup_form_probe_empty_body_rejected(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/setup/form-check", data={})
    assert response.status_code == 400
    assert b"EMPTY_BODY" in response.data or b"NO_PARSED_FIELDS" in response.data


def test_setup_form_probe_rejects_json_without_csrf_header(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/setup/form-check", json={"marker": "not-an-html-form"})
    assert response.status_code == 400
    assert b"UNSUPPORTED_CONTENT_TYPE" in response.data


def _https_setup_csrf(client, app):
    """Fetch a fresh CSRF token through an HTTPS setup response."""
    import re
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.get(
        "/setup", base_url="https://myplatoon.vercel.app",
    )
    assert response.status_code == 200
    assert response.headers["Referrer-Policy"] == "same-origin"
    token_match = re.search(
        rb'name="csrf_token" value="([^"]+)"', response.data
    )
    assert token_match is not None
    return token_match.group(1).decode("ascii")


def test_https_setup_csrf_probe_passes_with_same_origin_referer(client, app):
    """A valid token and HTTPS Referer must pass strict Flask-WTF CSRF."""
    token = _https_setup_csrf(client, app)
    response = client.post(
        "/setup/form-check",
        base_url="https://myplatoon.vercel.app",
        headers={"Referer": "https://myplatoon.vercel.app/setup"},
        data={"csrf_token": token},
    )
    assert response.status_code == 200
    assert b"Form security check passed" in response.data
    assert response.headers["Referrer-Policy"] == "same-origin"


def test_https_setup_csrf_referrer_missing_explains_actual_cause(client, app):
    token = _https_setup_csrf(client, app)
    response = client.post(
        "/setup/form-check",
        base_url="https://myplatoon.vercel.app",
        data={"csrf_token": token},
    )
    assert response.status_code == 400
    assert b"HTTPS_REFERRER_MISSING" in response.data
    assert b"browser did not send the HTTPS referrer" in response.data
    assert b"form security token was missing" not in response.data
    assert token.encode() not in response.data


def test_https_setup_csrf_rejects_cross_origin_referer(client, app):
    token = _https_setup_csrf(client, app)
    response = client.post(
        "/setup/form-check",
        base_url="https://myplatoon.vercel.app",
        headers={"Referer": "https://example.net/other"},
        data={"csrf_token": token},
    )
    assert response.status_code == 400
    assert b"HTTPS_REFERRER_MISMATCH" in response.data
    assert token.encode() not in response.data


def test_https_bootstrap_csrf_passes_with_same_origin_referer(client, app):
    """After HTTPS CSRF passes, the separate setup token is still required."""
    token = _https_setup_csrf(client, app)
    app.config["SETUP_TOKEN"] = "valid-only-for-this-test-" + "z" * 35
    response = client.post(
        "/setup",
        base_url="https://myplatoon.vercel.app",
        headers={"Referer": "https://myplatoon.vercel.app/setup"},
        data={
            "csrf_token": token,
            "setup_token": "incorrect-setup-token",
            "name": "Test Admin",
            "email": "admin-https@example.com",
            "password": "correct-but-unused-admin-password",
            "backup_confirm": "yes",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/setup")
