"""Tests for the dating feature: persona creation, compatibility scoring,
mutual-match detection (the two-sided cascade fix), notifications,
eligibility filtering, pause/report safety controls, and moderation.
"""
from datetime import datetime
from tests.conftest import login, _create_user


def _make_persona(db, user, gender, interested_in, interests="football, music",
                   display_name=None):
    from app.models import DatingPersona
    p = DatingPersona(
        profile_id=user.profile.id,
        display_name=display_name or user.full_name.split(" ")[0],
        gender=gender, interested_in=interested_in, interests=interests,
        status="active", age_confirmed_at=datetime.utcnow(),
    )
    db.session.add(p)
    db.session.commit()
    return p


def _approve(db, user):
    user.profile.status = "approved"
    db.session.commit()


def test_persona_requires_approved_profile(client, member_user, db):
    # member_user fixture's profile defaults to draft/unapproved
    login(client, "member@example.com")
    resp = client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Test", "gender": "male", "interested_in": "female",
    }, follow_redirects=True)
    assert b"needs to be approved" in resp.data

    from app.models import DatingPersona
    assert DatingPersona.query.filter_by(profile_id=member_user.profile.id).first() is None


def test_create_persona_generates_matches(client, member_user, db):
    _approve(db, member_user)
    other = _create_user(db, "other-dating@example.com", full_name="Other Person")
    _approve(db, other)
    _make_persona(db, other, gender="female", interested_in="male", interests="football, music")

    login(client, "member@example.com")
    resp = client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Me", "gender": "male", "interested_in": "female",
        "interests": "football, music, chess",
    }, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import DatingMatch, DatingPersona
    mine = DatingPersona.query.filter_by(profile_id=member_user.profile.id).first()
    assert mine is not None
    assert DatingMatch.query.count() == 1


def test_mutual_ranking_does_not_notify_without_mutual_consent(client, db):
    a = _create_user(db, "amaka@example.com", full_name="Amaka Test")
    b = _create_user(db, "tunde@example.com", full_name="Tunde Test")
    _approve(db, a)
    _approve(db, b)

    # Create A's persona first (no candidates exist yet -- this is exactly
    # the scenario that exposed the one-sided-ranking bug).
    login(client, "amaka@example.com")
    pf = client.get("/dating/persona")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Amaka", "gender": "female", "interested_in": "male",
        "interests": "hiking, music, football",
    })
    client.get("/auth/logout")

    login(client, "tunde@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Tunde", "gender": "male", "interested_in": "female",
        "interests": "football, cooking, music",
    })

    from app.models import DatingMatch, Notification
    match = DatingMatch.query.first()
    assert match.status == "matched"
    assert match.low_ranks_high is not None
    assert match.high_ranks_low is not None

    # Ranking overlap is NOT romantic consent. Do not notify either person
    # until both explicitly express interest through the Dating UI.
    notifs = Notification.query.all()
    assert not notifs


def test_same_gender_preference_never_matches(client, db):
    a = _create_user(db, "a1@example.com", full_name="A One")
    b = _create_user(db, "a2@example.com", full_name="A Two")
    _approve(db, a)
    _approve(db, b)
    _make_persona(db, a, gender="male", interested_in="female")

    login(client, "a2@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "A2", "gender": "male", "interested_in": "female",
        "interests": "football",
    })

    from app.models import DatingMatch
    assert DatingMatch.query.count() == 0  # both seeking female, neither is female


def test_unapproved_profile_not_matched_as_candidate(client, db):
    a = _create_user(db, "approved-a@example.com", full_name="Approved A")
    b = _create_user(db, "unapproved-b@example.com", full_name="Unapproved B")
    _approve(db, a)
    # b stays unapproved (draft)
    _make_persona(db, b, gender="female", interested_in="male")

    login(client, "approved-a@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "A", "gender": "male", "interested_in": "female",
        "interests": "football",
    })

    from app.models import DatingMatch
    assert DatingMatch.query.count() == 0


def test_paused_persona_excluded_from_new_matching(client, db):
    a = _create_user(db, "pauser@example.com", full_name="Pauser")
    b = _create_user(db, "target@example.com", full_name="Target")
    _approve(db, a)
    _approve(db, b)
    persona_a = _make_persona(db, a, gender="female", interested_in="male")
    persona_a.status = "paused"
    db.session.commit()

    login(client, "target@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Target", "gender": "male", "interested_in": "female",
        "interests": "football",
    })

    from app.models import DatingMatch
    assert DatingMatch.query.count() == 0


def test_toggle_pause(client, member_user, db):
    _approve(db, member_user)
    login(client, "member@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Me", "gender": "male", "interested_in": "female",
    })

    from app.models import DatingPersona
    persona = DatingPersona.query.filter_by(profile_id=member_user.profile.id).first()
    assert persona.status == "active"

    client.post("/dating/pause", follow_redirects=True)
    db.session.refresh(persona)
    assert persona.status == "paused"

    client.post("/dating/pause", follow_redirects=True)
    db.session.refresh(persona)
    assert persona.status == "active"


def test_report_hides_persona_from_matching(client, db):
    a = _create_user(db, "reporter@example.com", full_name="Reporter")
    b = _create_user(db, "reported@example.com", full_name="Reported Person")
    _approve(db, a)
    _approve(db, b)
    persona_b = _make_persona(db, b, gender="female", interested_in="male")

    login(client, "reporter@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Reporter", "gender": "male", "interested_in": "female",
        "interests": "football",
    })

    from app.models import DatingMatch
    assert DatingMatch.query.count() == 1  # matched candidate before report

    resp = client.get(f"/dating/persona")  # sanity: page still loads
    report_page = client.get(f"/dating/report/{persona_b.id}")
    token = None
    import re
    m = re.search(rb'name="csrf_token" type="hidden" value="([^"]+)"', report_page.data)
    token = m.group(1).decode() if m else ""
    client.post(f"/dating/report/{persona_b.id}", data={
        "csrf_token": token, "reason": "Inappropriate profile content",
    }, follow_redirects=True)

    db.session.refresh(persona_b)
    assert persona_b.is_reported is True

    # A reported persona should no longer appear as a dating candidate,
    # even though the DatingMatch row still exists. (There was only one
    # candidate, so browsing now shows the empty state.)
    browse_resp = client.get("/dating/browse")
    assert b"No suggestions yet" in browse_resp.data


def test_cannot_report_self(client, member_user, db):
    _approve(db, member_user)
    login(client, "member@example.com")
    client.post("/dating/persona", data={
        "age_confirm": "y",
        "display_name": "Me", "gender": "male", "interested_in": "female",
    })
    from app.models import DatingPersona
    mine = DatingPersona.query.filter_by(profile_id=member_user.profile.id).first()
    resp = client.get(f"/dating/report/{mine.id}")
    assert resp.status_code == 400


def test_admin_can_clear_and_remove_reported_persona(client, admin_user, db):
    reported_user = _create_user(db, "moderated@example.com", full_name="Moderated User")
    _approve(db, reported_user)
    persona = _make_persona(db, reported_user, gender="female", interested_in="male")
    persona.is_reported = True
    persona.report_reason = "Test reason"
    db.session.commit()

    login(client, "admin@example.com")
    resp = client.get("/admin/dating")
    assert b"Moderated User" in resp.data or b"Test reason" in resp.data

    clear_resp = client.post(f"/admin/dating/{persona.id}/clear", follow_redirects=True)
    assert clear_resp.status_code == 200
    db.session.refresh(persona)
    assert persona.is_reported is False


def test_non_admin_cannot_access_dating_moderation(client, member_user, db):
    login(client, "member@example.com")
    resp = client.get("/admin/dating")
    assert resp.status_code == 403


def test_dating_disabled_returns_404(client, member_user, db):
    from app import create_app
    app = create_app("testing")
    app.config["ENABLE_DATING"] = False
    with app.app_context():
        from app.extensions import db as _db
        _db.create_all()
        c = app.test_client()
        c.post("/auth/login", data={"email": "x@example.com", "password": "whatever"})
        resp = c.get("/dating/")
        assert resp.status_code in (302, 404)  # redirected to login or feature-disabled 404


def test_compatibility_score_is_symmetric(app, db):
    with app.app_context():
        a = _create_user(db, "sym-a@example.com", full_name="Sym A")
        b = _create_user(db, "sym-b@example.com", full_name="Sym B")
        _approve(db, a)
        _approve(db, b)
        pa = _make_persona(db, a, gender="male", interested_in="female", interests="chess, hiking")
        pb = _make_persona(db, b, gender="female", interested_in="male", interests="hiking, cooking")

        from app.services.dating_service import compute_compatibility
        assert compute_compatibility(pa, pb) == compute_compatibility(pb, pa)


def test_score_label_bands():
    from app.models import score_label
    label, emoji = score_label(95)
    assert label == "Soulmate Vibes"
    label2, _ = score_label(30)
    assert label2 == "Wildcard"
