from tests.conftest import login


def test_admin_account_created_via_seeding_gets_a_profile():
    from app import create_app, _seed_initial_admin
    from app.extensions import db as _db

    app = create_app("testing")
    app.config["ADMIN_INIT_EMAIL"] = "profile-check-admin@example.com"
    app.config["ADMIN_INIT_PASSWORD"] = "StrongPass123"
    with app.app_context():
        _db.create_all()
        _seed_initial_admin(app)

        from app.models import User
        admin = User.query.filter_by(email="profile-check-admin@example.com").first()
        assert admin.profile is not None
        assert admin.profile.status == "approved"
        _db.drop_all()


def test_cli_create_admin_creates_a_profile(app, db):
    from click.testing import CliRunner
    runner = CliRunner()
    with app.app_context():
        result = runner.invoke(app.cli, [
            "create-admin", "--email", "clitest@example.com",
            "--name", "CLI Admin", "--password", "StrongPass123",
        ])
        assert result.exit_code == 0, result.output

        from app.models import User
        admin = User.query.filter_by(email="clitest@example.com").first()
        assert admin is not None
        assert admin.profile is not None


def test_profile_less_user_self_heals_on_login(client, db):
    from app.models import User
    broken = User(full_name="Broken Admin", email="broken-admin@example.com", role="admin")
    broken.set_password("Password123")
    db.session.add(broken)
    db.session.commit()
    assert broken.profile is None

    resp = login(client, "broken-admin@example.com")
    assert resp.status_code == 200

    healed = User.query.filter_by(email="broken-admin@example.com").first()
    assert healed.profile is not None


def test_dashboard_does_not_crash_for_profile_less_user(client, db):
    from app.models import User
    broken = User(full_name="Broken User", email="broken2@example.com", role="member")
    broken.set_password("Password123")
    db.session.add(broken)
    db.session.commit()

    login(client, "broken2@example.com")
    resp = client.get("/profile/dashboard")
    assert resp.status_code == 200
    resp2 = client.get("/business/mine")
    assert resp2.status_code == 200
