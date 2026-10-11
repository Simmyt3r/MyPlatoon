"""Nationwide NYSC communities, proper PCM state and cohort privacy."""
from tests.conftest import login
from app.models import User, Profile, Platoon


def _cohort(db, state="Benue", year=2026, batch="B", stream="II", number=5):
    return Platoon.find_or_create(state, year, batch, stream, number)


def _approved(db, email, state="Benue", number=5):
    user = User(full_name="Test " + email, email=email, role="member")
    user.set_password("Password123")
    db.session.add(user)
    db.session.flush()
    db.session.add(Profile(
        user_id=user.id, status="approved", profile_visibility="platoon",
        service_stage="serving", platoon=_cohort(db, state=state, number=number),
        phone_number="09011112222", phone_visibility="platoon"
    ))
    db.session.commit()
    return user


def test_platoon_guide_explains_pcm_and_assignment(client):
    r = client.get("/platoons/guide")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Prospective Corps Member" in html
    assert "Awaiting camp assignment" in html
    assert "orientation camp" in html.lower()
    assert "not an official NYSC" in html


def test_pcm_registration_never_invents_a_platoon(client, db):
    response = client.post("/auth/register", data={
        "full_name": "New PCM", "email": "newpcm@example.com",
        "password": "StrongPass1", "confirm_password": "StrongPass1",
        "service_stage": "pcm",
    }, follow_redirects=True)
    assert response.status_code == 200
    user = User.query.filter_by(email="newpcm@example.com").one()
    assert user.profile.service_stage == "pcm"
    assert user.profile.platoon_id is None
    assert user.profile.platoon_label == "Awaiting camp assignment"


def test_serving_registration_requires_complete_platoon(client, db):
    response = client.post("/auth/register", data={
        "full_name": "Incomplete Member", "email": "incomplete@example.com",
        "password": "StrongPass1", "confirm_password": "StrongPass1",
        "service_stage": "serving", "nysc_state": "Benue",
    })
    assert response.status_code == 200
    assert User.query.filter_by(email="incomplete@example.com").first() is None
    assert b"Enter the year" in response.data


def test_valid_national_alumnus_registration(client, db):
    response = client.post("/auth/register", data={
        "full_name": "An Alumnus", "email": "alum@example.com",
        "password": "StrongPass1", "confirm_password": "StrongPass1",
        "service_stage": "alumni", "nysc_state": "Plateau",
        "service_year": "2023", "nysc_batch": "C",
        "nysc_stream": "I", "platoon_number": "7",
    }, follow_redirects=True)
    assert response.status_code == 200
    p = User.query.filter_by(email="alum@example.com").one().profile
    assert p.service_stage == "alumni"
    assert p.platoon.state == "Plateau"
    assert p.platoon.service_year == 2023
    assert p.platoon.number == 7


def test_same_number_other_state_is_not_same_platoon(client, db):
    benue = _approved(db, "benue@example.com", state="Benue")
    plateau = _approved(db, "plateau@example.com", state="Plateau")
    assert benue.profile.platoon_id != plateau.profile.platoon_id

    login(client, "plateau@example.com")
    assert client.get("/directory/member/" + benue.profile.slug).status_code == 404
    html = client.get("/directory/members").get_data(as_text=True)
    assert "benue@example.com" not in html
    assert benue.full_name not in html
    assert plateau.full_name in html


def test_same_cohort_can_view_approved_platoon_profile(client, db):
    first = _approved(db, "first@example.com")
    other = _approved(db, "other@example.com")
    assert first.profile.platoon_id == other.profile.platoon_id

    login(client, "other@example.com")
    page = client.get("/directory/member/" + first.profile.slug)
    assert page.status_code == 200
    assert b"09011112222" in page.data


def test_pcm_has_no_access_to_platoon_only_profiles(client, db, member_user):
    target = _approved(db, "privatecamp@example.com")
    login(client, member_user.email)
    assert member_user.profile.platoon_id is None
    assert client.get("/directory/member/" + target.profile.slug).status_code == 404


def test_album_only_contains_exact_cohort(client, db):
    first = _approved(db, "albumbenue@example.com", state="Benue")
    other = _approved(db, "albumplateau@example.com", state="Plateau")
    from app.services.album_service import generate_new_album_version
    version, pdf = generate_new_album_version(first, first.profile.platoon_id)
    assert version.member_count == 1
    assert pdf.startswith(b"%PDF")
    assert version.platoon_id == first.profile.platoon_id

    login(client, other.email)
    assert client.get("/album/download/" + str(version.id)).status_code == 403
    assert client.get("/album/").status_code == 200


def test_legacy_national_album_remains_admin_only(client, db, member_user):
    from app.models import AlbumVersion
    version = AlbumVersion(
        version_label="0.1", pdf_url="", pdf_data=b"%PDF-1.4",
        member_count=3, status="published"
    )
    db.session.add(version)
    db.session.commit()
    login(client, member_user.email)
    assert client.get("/album/download/" + str(version.id)).status_code == 403
