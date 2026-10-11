from tests.conftest import login


def test_non_admin_cannot_access_admin_dashboard(client, member_user):
    login(client, "member@example.com")
    resp = client.get("/admin/")
    assert resp.status_code == 403


def test_guest_cannot_access_admin_dashboard(client):
    # Flask-Login's @login_required fires before the admin check, so an
    # unauthenticated visitor is redirected to log in rather than shown a 403.
    resp = client.get("/admin/", follow_redirects=True)
    assert resp.request.path == "/auth/login"


def test_admin_can_access_dashboard(client, admin_user):
    login(client, "admin@example.com")
    resp = client.get("/admin/")
    assert resp.status_code == 200


def test_admin_can_approve_profile(client, admin_user, member_user, db):
    member_user.profile.status = "pending"
    db.session.commit()

    login(client, "admin@example.com")
    resp = client.post(f"/admin/members/{member_user.profile.id}/approve", follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Profile
    profile = Profile.query.get(member_user.profile.id)
    assert profile.status == "approved"
    assert profile.reviewed_by_id == admin_user.id


def test_admin_can_reject_profile_with_reason(client, admin_user, member_user, db):
    member_user.profile.status = "pending"
    db.session.commit()

    login(client, "admin@example.com")
    resp = client.post(f"/admin/members/{member_user.profile.id}/reject", data={
        "reason": "Profile photo is missing.",
    }, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Profile
    profile = Profile.query.get(member_user.profile.id)
    assert profile.status == "rejected"
    assert profile.rejection_reason == "Profile photo is missing."


def test_admin_can_suspend_and_reinstate(client, admin_user, member_user, db):
    login(client, "admin@example.com")
    client.post(f"/admin/members/{member_user.profile.id}/suspend", follow_redirects=True)

    from app.models import User, Profile
    user = User.query.get(member_user.id)
    assert user.is_suspended is True
    assert Profile.query.get(member_user.profile.id).status == "suspended"

    client.post(f"/admin/members/{member_user.profile.id}/reinstate", follow_redirects=True)
    user_again = User.query.get(member_user.id)
    assert user_again.is_suspended is False


def test_non_admin_cannot_approve_profile(client, member_user, db):
    from tests.conftest import _create_user
    other = _create_user(db, "victim@example.com", full_name="Victim")
    other.profile.status = "pending"
    db.session.commit()

    login(client, "member@example.com")
    resp = client.post(f"/admin/members/{other.profile.id}/approve")
    assert resp.status_code == 403

    from app.models import Profile
    assert Profile.query.get(other.profile.id).status == "pending"


def test_category_management(client, admin_user, db):
    login(client, "admin@example.com")
    resp = client.post("/admin/categories", data={"name": "Robotics"}, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import BusinessCategory
    assert BusinessCategory.query.filter_by(name="Robotics").first() is not None
