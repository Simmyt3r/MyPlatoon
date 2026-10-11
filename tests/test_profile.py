from tests.conftest import login


def test_dashboard_requires_login(client):
    resp = client.get("/profile/dashboard", follow_redirects=True)
    assert resp.request.path == "/auth/login"


def test_dashboard_shows_completion(client, member_user):
    login(client, "member@example.com")
    resp = client.get("/profile/dashboard")
    assert resp.status_code == 200


def test_edit_profile_updates_fields(client, member_user, db):
    login(client, "member@example.com")
    resp = client.post("/profile/edit", data={
        "nickname": "MJ",
        "gender": "male",
        "state_of_origin": "Oyo",
        "lga": "Ibadan North",
        "phone_number": "08012345678",
        "whatsapp_number": "08012345678",
        "current_location": "Ibadan",
        "address": "1 Test Street",
        "profession": "Data Analyst",
        "course_of_study": "Statistics",
        "institution": "University of Ibadan",
        "graduation_year": "2024",
        "certifications": "",
        "biography": "A short bio about myself for testing purposes here.",
        "skills": "Python, SQL, Excel",
        "website": "", "facebook": "", "instagram": "", "tiktok": "", "twitter_x": "",
    }, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Profile
    profile = Profile.query.filter_by(user_id=member_user.id).first()
    assert profile.profession == "Data Analyst"
    assert profile.state_of_origin == "Oyo"
    assert len(profile.skills) == 3


def test_profile_completion_calculation(client, member_user, db):
    profile = member_user.profile
    # full_name is always present (collected at registration), so the
    # baseline completion is 10%, not 0%.
    assert profile.completion_percent() == 10

    profile.photo_url = "https://example.com/photo.jpg"
    profile.profession = "Engineer"
    profile.state_of_origin = "Lagos"
    profile.lga = "Ikeja"
    profile.phone_number = "08000000000"
    db.session.commit()
    # photo(10) + full_name(10) + profession(10) + state_lga(10) + contact(10) = 50
    assert profile.completion_percent() == 50


def test_submit_for_approval_requires_completion_threshold(client, member_user):
    login(client, "member@example.com")
    resp = client.post("/profile/submit", data={}, follow_redirects=True)
    assert b"complete more of your profile" in resp.data.lower()

    from app.models import Profile
    profile = Profile.query.filter_by(user_id=member_user.id).first()
    assert profile.status == "draft"


def test_submit_for_approval_succeeds_when_complete_enough(client, member_user, db):
    profile = member_user.profile
    profile.photo_url = "x"
    profile.profession = "Engineer"
    profile.state_of_origin = "Lagos"
    profile.lga = "Ikeja"
    profile.biography = "A sufficiently long biography for completion scoring purposes."
    profile.phone_number = "08000000000"
    db.session.commit()

    login(client, "member@example.com")
    resp = client.post("/profile/submit", data={}, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Profile
    refreshed = Profile.query.filter_by(user_id=member_user.id).first()
    assert refreshed.status == "pending"


def test_privacy_settings_update(client, member_user, db):
    login(client, "member@example.com")
    resp = client.post("/profile/privacy", data={
        "profile_visibility": "public",
        "phone_visibility": "private",
        "whatsapp_visibility": "platoon",
        "address_visibility": "private",
    }, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Profile
    profile = Profile.query.filter_by(user_id=member_user.id).first()
    assert profile.profile_visibility == "public"
    assert profile.phone_visibility == "private"


def test_private_profile_not_publicly_viewable(client, approved_member, db):
    approved_member.profile.profile_visibility = "private"
    db.session.commit()
    resp = client.get(f"/directory/member/{approved_member.profile.slug}")
    assert resp.status_code == 404


def test_public_approved_profile_is_viewable(client, approved_member):
    resp = client.get(f"/directory/member/{approved_member.profile.slug}")
    assert resp.status_code == 200
    assert b"Approved Member" in resp.data


def test_pending_profile_not_publicly_listed(client, member_user, db):
    member_user.profile.status = "pending"
    member_user.profile.profile_visibility = "public"
    db.session.commit()
    resp = client.get(f"/directory/member/{member_user.profile.slug}")
    assert resp.status_code == 404
