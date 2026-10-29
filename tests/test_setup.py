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
