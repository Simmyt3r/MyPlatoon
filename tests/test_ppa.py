"""PPA lookup and GIS privacy/regression tests (SQLite local, Aiven PostgreSQL in production)."""
from tests.conftest import login
from app.models import PPA, Platoon


def _reporter(db, user):
    user.profile.status = "approved"
    user.profile.service_stage = "serving"
    user.profile.platoon = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    db.session.commit()
    return user


def _data(**overrides):
    data = dict(
        name="General Hospital Wadata",
        state="Benue", lga="Makurdi", town="Wadata",
        sector="health", address="Hospital reception",
        accommodation="unknown", allowance="no",
        latitude="7.733333", longitude="8.555555",
        experience_notes="Worked with the health outreach team.",
    )
    data.update(overrides)
    return data


def test_lookup_is_public_and_has_map(client):
    r = client.get("/ppas/")
    assert r.status_code == 200
    assert b"Find a PPA" in r.data
    assert b"ppa-map" in r.data
    assert client.get("/ppas/geojson").json == {
        "type": "FeatureCollection", "features": [], "truncated": False
    }


def test_pcm_cannot_submit_or_see_admin_review(client, member_user):
    login(client, member_user.email)
    assert client.get("/ppas/new").status_code == 302
    assert client.get("/ppas/review").status_code == 403
    assert client.post("/ppas/999/review", data={"decision": "verified"}).status_code == 403


def test_verified_member_can_submit_and_remains_unpublished(client, member_user, db):
    _reporter(db, member_user)
    login(client, member_user.email)
    result = client.post("/ppas/new", data=_data(), follow_redirects=True)
    assert result.status_code == 200
    entry = PPA.query.one()
    assert entry.name == "General Hospital Wadata"
    assert entry.status == "pending"
    assert entry.submitted_by_id == member_user.id
    assert client.get("/ppas/geojson").json["features"] == []
    assert client.get("/ppas/" + str(entry.id)).status_code == 200


def test_public_cannot_view_unreviewed_ppa(client, member_user, db):
    _reporter(db, member_user)
    login(client, member_user.email)
    client.post("/ppas/new", data=_data())
    id_ = PPA.query.one().id
    client.get("/auth/logout")
    assert client.get("/ppas/" + str(id_)).status_code == 404


def test_invalid_or_half_gis_coordinates_rejected(client, member_user, db):
    _reporter(db, member_user)
    login(client, member_user.email)
    client.post("/ppas/new", data=_data(latitude="10", longitude=""))
    assert PPA.query.count() == 0
    client.post("/ppas/new", data=_data(latitude="1000", longitude="8"))
    assert PPA.query.count() == 0
    assert client.get("/ppas/geojson?lat=100&lng=1").status_code == 400


def test_duplicate_ppa_name_state_lga_is_blocked(client, member_user, db):
    _reporter(db, member_user)
    login(client, member_user.email)
    client.post("/ppas/new", data=_data())
    r = client.post("/ppas/new", data=_data(name="  GENERAL   hospital wadata  "))
    assert r.status_code == 200
    assert b"already listed" in r.data
    assert PPA.query.count() == 1


def test_admin_review_exposes_pins_and_nearby_filters(
    client, member_user, admin_user, db
):
    _reporter(db, member_user)
    login(client, member_user.email)
    client.post("/ppas/new", data=_data())
    entry_id = PPA.query.one().id
    client.get("/auth/logout")
    login(client, admin_user.email)
    review = client.post("/ppas/" + str(entry_id) + "/review",
                         data={"decision": "verified"}, follow_redirects=True)
    assert review.status_code == 200
    assert PPA.query.one().verified_by_id == admin_user.id
    collection = client.get("/ppas/geojson").json
    assert len(collection["features"]) == 1
    feature = collection["features"][0]
    assert feature["geometry"]["coordinates"] == [8.555555, 7.733333]
    assert "submitted_by_id" not in feature["properties"]
    assert len(client.get("/ppas/geojson?lat=7.733333&lng=8.555555&radius=5").json["features"]) == 1
    assert len(client.get("/ppas/geojson?lat=10&lng=10&radius=5").json["features"]) == 0
    assert client.get("/ppas/?state=Benue&sector=health").status_code == 200


def test_edit_resets_public_listing_for_review(client, member_user, admin_user, db):
    _reporter(db, member_user)
    ppa = PPA(name="A PPA", name_key="a ppa", state="Benue", lga="Makurdi",
              sector="health", submitted_by_id=member_user.id, status="verified")
    db.session.add(ppa)
    db.session.commit()
    login(client, member_user.email)
    r = client.post("/ppas/" + str(ppa.id) + "/edit", data=_data(name="A PPA"))
    assert r.status_code == 302
    assert PPA.query.get(ppa.id).status == "pending"
    assert client.get("/ppas/geojson").json["features"] == []


def test_admin_rejection_requires_reason(client, admin_user, db):
    ppa = PPA(name="Test Clinic", name_key="test clinic", state="Benue", lga="Makurdi",
              sector="health", status="pending")
    db.session.add(ppa)
    db.session.commit()
    login(client, admin_user.email)
    r = client.post("/ppas/" + str(ppa.id) + "/review", data={"decision": "rejected"})
    assert r.status_code == 302
    assert ppa.status == "pending"
    client.post("/ppas/" + str(ppa.id) + "/review",
                data={"decision": "rejected", "reason": "Insufficient details"})
    assert ppa.status == "rejected"
    assert ppa.rejection_reason == "Insufficient details"
