from tests.conftest import login


def test_register_creates_user_and_profile(client, db):
    resp = client.post("/auth/register", data={
        "full_name": "New Corper",
        "email": "newcorper@example.com",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
    }, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import User
    user = User.query.filter_by(email="newcorper@example.com").first()
    assert user is not None
    assert user.profile is not None
    assert user.check_password("StrongPass1")
    assert user.password_hash != "StrongPass1"  # never stored in plaintext
    assert user.is_active is True
    assert user.profile.status == "approved"
    assert user.profile.reviewed_by_id is None  # no administrator required

    # A new member can sign in and see their dashboard immediately.
    login_response = login(client, "newcorper@example.com", password="StrongPass1")
    assert login_response.status_code == 200
    assert login_response.request.path == "/profile/dashboard"


def test_register_duplicate_email_rejected(client, member_user):
    resp = client.post("/auth/register", data={
        "full_name": "Duplicate",
        "email": "member@example.com",
        "password": "StrongPass1",
        "confirm_password": "StrongPass1",
    })
    assert b"already exists" in resp.data
    from app.models import User
    assert User.query.filter_by(email="member@example.com").count() == 1


def test_register_password_mismatch_rejected(client):
    resp = client.post("/auth/register", data={
        "full_name": "Mismatch",
        "email": "mismatch@example.com",
        "password": "StrongPass1",
        "confirm_password": "Different1",
    })
    assert resp.status_code == 200
    from app.models import User
    assert User.query.filter_by(email="mismatch@example.com").first() is None


def test_register_weak_password_rejected(client):
    resp = client.post("/auth/register", data={
        "full_name": "Weak Pass",
        "email": "weak@example.com",
        "password": "onlyletters",
        "confirm_password": "onlyletters",
    })
    from app.models import User
    assert User.query.filter_by(email="weak@example.com").first() is None


def test_login_success(client, member_user):
    resp = login(client, "member@example.com")
    assert resp.status_code == 200
    assert b"Dashboard" in resp.data or b"WELCOME" in resp.data.upper() or resp.request.path == "/profile/dashboard"


def test_login_invalid_password(client, member_user):
    resp = login(client, "member@example.com", password="WrongPass1")
    assert b"Invalid email or password" in resp.data


def test_login_nonexistent_user(client):
    resp = login(client, "ghost@example.com", password="whatever1")
    assert b"Invalid email or password" in resp.data


def test_logout_requires_post_and_login(client, member_user):
    # A cross-site GET or a clicked link must never terminate a session.
    assert client.get("/auth/logout").status_code == 405
    resp = client.post("/auth/logout", follow_redirects=True)
    assert resp.request.path == "/auth/login"

    login(client, "member@example.com")
    dashboard = client.get("/profile/dashboard")
    assert b'action="/auth/logout"' in dashboard.data
    assert b'name="csrf_token"' in dashboard.data

    resp = client.post("/auth/logout", follow_redirects=True)
    assert resp.status_code == 200
    assert client.get("/profile/dashboard").status_code == 302


def test_suspended_account_cannot_login(client, member_user, db):
    member_user.is_suspended = True
    db.session.commit()
    resp = login(client, "member@example.com")
    assert b"suspended" in resp.data.lower()


def test_legacy_pending_and_draft_members_activate_on_login(client, db):
    from tests.conftest import _create_user
    for email, initial_status in (
        ("waiting@example.com", "pending"),
        ("unfinished@example.com", "draft"),
    ):
        user = _create_user(db, email)
        user.profile.status = initial_status
        db.session.commit()
        response = login(client, email)
        assert response.status_code == 200
        db.session.refresh(user.profile)
        assert user.profile.status == "approved"
        client.post("/auth/logout")


def test_login_does_not_reverse_rejection_or_suspension(client, db):
    from tests.conftest import _create_user
    rejected = _create_user(db, "rejected@example.com")
    rejected.profile.status = "rejected"
    rejected.profile.rejection_reason = "Moderation decision"
    suspended = _create_user(db, "suspended@example.com")
    suspended.profile.status = "suspended"
    suspended.is_suspended = True
    db.session.commit()

    result = login(client, rejected.email)
    assert result.status_code == 200
    assert rejected.profile.status == "rejected"
    client.post("/auth/logout")

    response = login(client, suspended.email)
    assert b"suspended" in response.data.lower()
    assert suspended.profile.status == "suspended"
    assert suspended.is_suspended is True
