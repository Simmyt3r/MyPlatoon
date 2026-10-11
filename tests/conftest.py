import pytest

from app import create_app
from app.extensions import db as _db
from app.models import User, Profile


@pytest.fixture()
def app():
    # create_app() already creates tables and seeds default business
    # categories on startup (see app/__init__.py::_ensure_database_schema) --
    # no need to duplicate that here.
    application = create_app("testing")
    with application.app_context():
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db


def _create_user(db, email, password="Password123", role="member", full_name="Test User"):
    user = User(full_name=full_name, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    profile = Profile(user_id=user.id)
    db.session.add(profile)
    db.session.commit()
    return user


@pytest.fixture()
def member_user(db):
    return _create_user(db, "member@example.com", full_name="Member One")


@pytest.fixture()
def admin_user(db):
    return _create_user(db, "admin@example.com", role="admin", full_name="Admin User")


@pytest.fixture()
def approved_member(db):
    user = _create_user(db, "approved@example.com", full_name="Approved Member")
    user.profile.status = "approved"
    user.profile.profession = "Engineer"
    user.profile.state_of_origin = "Lagos"
    user.profile.profile_visibility = "public"
    db.session.commit()
    return user


def login(client, email, password="Password123"):
    return client.post("/auth/login", data={
        "email": email, "password": password,
    }, follow_redirects=True)
