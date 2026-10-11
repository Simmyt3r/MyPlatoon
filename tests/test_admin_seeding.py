"""Tests for automatic admin account seeding.

Note: BaseConfig reads ADMIN_INIT_EMAIL/ADMIN_INIT_PASSWORD from os.environ
at class-definition time (module import), which happens once per process --
that's correct for real deployments (env vars are set before the process
starts) but means mutating os.environ mid-test-session won't retroactively
change already-imported config classes. So these tests set app.config
directly and call the seeding function itself, rather than going through
env vars + create_app(), to test the actual behavior without fighting
Python's import caching.
"""
from app import create_app, _seed_initial_admin
from app.extensions import db as _db


def test_no_admin_created_when_config_unset():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        from app.models import User
        assert User.query.filter_by(role="admin").count() == 0
        _db.drop_all()


def test_admin_created_when_config_set():
    app = create_app("testing")
    app.config["ADMIN_INIT_EMAIL"] = "seeded-admin@example.com"
    app.config["ADMIN_INIT_PASSWORD"] = "StrongPass123"
    with app.app_context():
        _db.create_all()
        _seed_initial_admin(app)

        from app.models import User
        admin = User.query.filter_by(email="seeded-admin@example.com").first()
        assert admin is not None
        assert admin.role == "admin"
        assert admin.check_password("StrongPass123")
        _db.drop_all()


def test_admin_seeding_is_idempotent():
    app = create_app("testing")
    app.config["ADMIN_INIT_EMAIL"] = "seeded-admin2@example.com"
    app.config["ADMIN_INIT_PASSWORD"] = "StrongPass123"
    with app.app_context():
        _db.create_all()
        _seed_initial_admin(app)
        _seed_initial_admin(app)  # run again -- must not duplicate or error

        from app.models import User
        assert User.query.filter_by(email="seeded-admin2@example.com").count() == 1
        _db.drop_all()


def test_weak_admin_password_is_rejected():
    app = create_app("testing")
    app.config["ADMIN_INIT_EMAIL"] = "weak-admin@example.com"
    app.config["ADMIN_INIT_PASSWORD"] = "short"
    with app.app_context():
        _db.create_all()
        _seed_initial_admin(app)

        from app.models import User
        assert User.query.filter_by(email="weak-admin@example.com").first() is None
        _db.drop_all()


def test_does_not_overwrite_existing_account_with_same_email():
    app = create_app("testing")
    app.config["ADMIN_INIT_EMAIL"] = "existing@example.com"
    app.config["ADMIN_INIT_PASSWORD"] = "StrongPass123"
    with app.app_context():
        _db.create_all()
        from app.models import User
        existing = User(full_name="Already Here", email="existing@example.com", role="member")
        existing.set_password("OriginalPass123")
        _db.session.add(existing)
        _db.session.commit()

        _seed_initial_admin(app)

        user = User.query.filter_by(email="existing@example.com").first()
        assert user.role == "member"  # not silently promoted/overwritten
        assert user.check_password("OriginalPass123")
        _db.drop_all()
