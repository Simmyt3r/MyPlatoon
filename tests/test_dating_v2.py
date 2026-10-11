"""Privacy, age confirmation and block controls for MyPlatoon Dating v2."""
from datetime import datetime

from tests.conftest import login, _create_user
from app.models import DatingPersona, DatingMatch, DatingBlock, User
from app.services.dating_service import (
    browse_matches_for_persona, generate_matches_for_persona,
    is_blocked, compute_compatibility,
)


def _approved(db, email, name):
    user = _create_user(db, email, full_name=name)
    user.profile.status = "approved"
    db.session.commit()
    return user


def _persona(db, user, gender="male", looking_for="female",
             interests="music, coding", active=True, confirmed=True):
    obj = DatingPersona(
        profile_id=user.profile.id,
        display_name="Private Alias " + str(user.id),
        gender=gender, interested_in=looking_for, interests=interests,
        status="active" if active else "paused",
        age_confirmed_at=datetime.utcnow() if confirmed else None,
    )
    db.session.add(obj)
    db.session.commit()
    return obj


def test_dating_requires_18_plus_confirmation(client, member_user, db):
    member_user.profile.status = "approved"
    db.session.commit()
    login(client, member_user.email)
    response = client.post("/dating/persona", data={
        "gender": "male", "interested_in": "female",
        "display_name": "Example", "interests": "film, music",
    })
    assert response.status_code == 200
    assert b"confirm that you are 18 or older" in response.data
    assert DatingPersona.query.count() == 0
    response = client.post("/dating/persona", data={
        "gender": "male", "interested_in": "female",
        "display_name": "Example", "interests": "film, music",
        "age_confirm": "y",
    })
    assert response.status_code == 302
    assert DatingPersona.query.one().age_confirmed_at is not None


def test_legacy_persona_must_confirm_adult_status(client, db):
    user = _approved(db, "old@example.com", "Old Member")
    old = _persona(db, user, confirmed=False)
    login(client, user.email)
    response = client.get("/dating/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dating/persona")
    response = client.post("/dating/persona", data={
        "gender": "male", "interested_in": "female", "age_confirm": "y"
    })
    assert response.status_code == 302
    assert old.age_confirmed_at is not None


def test_paused_and_unconfirmed_members_not_in_suggestions(app, db):
    a = _approved(db, "active@example.com", "Active Member")
    b = _approved(db, "unconfirmed@example.com", "Unconfirmed")
    c = _approved(db, "paused@example.com", "Paused Member")
    pa = _persona(db, a, gender="male", looking_for="female")
    _persona(db, b, gender="female", looking_for="male", confirmed=False)
    _persona(db, c, gender="female", looking_for="male", active=False)
    assert generate_matches_for_persona(pa) == []
    assert browse_matches_for_persona(pa) == []


def test_block_hides_people_in_both_directions(client, db):
    a = _approved(db, "block-a@example.com", "Block A")
    b = _approved(db, "block-b@example.com", "Block B")
    pa = _persona(db, a, gender="male")
    pb = _persona(db, b, gender="female", looking_for="male")
    generate_matches_for_persona(pa)
    assert len(browse_matches_for_persona(pa)) == 1
    assert len(browse_matches_for_persona(pb)) == 1

    login(client, a.email)
    response = client.post(f"/dating/block/{pb.id}", follow_redirects=True)
    assert response.status_code == 200
    assert DatingBlock.query.count() == 1
    assert is_blocked(pa.id, pb.id)
    assert browse_matches_for_persona(pa) == []
    assert browse_matches_for_persona(pb) == []
    assert client.get(f"/dating/person/{pb.id}").status_code == 404

    # Blocking is idempotent and does not disclose the blocked person's details.
    client.post(f"/dating/block/{pb.id}")
    assert DatingBlock.query.count() == 1
    unblocked = client.post(f"/dating/unblock/{pb.id}")
    assert unblocked.status_code == 302
    assert not is_blocked(pa.id, pb.id)


def test_card_links_to_persona_without_personal_contact(client, db):
    a = _approved(db, "private-view-a@example.com", "Alice Contact")
    b = _approved(db, "private-view-b@example.com", "Bob Contact")
    a.profile.phone_number = "08000001111"
    b.profile.phone_number = "08000002222"
    b.profile.photo_url = "https://example.com/private-photo.jpg"
    pa = _persona(db, a, gender="male")
    pb = _persona(db, b, gender="female", looking_for="male")
    generate_matches_for_persona(pa)

    login(client, a.email)
    browse = client.get("/dating/browse").get_data(as_text=True)
    assert f'/dating/person/{pb.id}' in browse
    assert b.profile.slug not in browse
    assert "https://example.com/private-photo.jpg" not in browse
    preview = client.get(f"/dating/person/{pb.id}").get_data(as_text=True)
    assert "08000002222" not in preview
    assert "https://example.com/private-photo.jpg" not in preview
    assert b.profile.slug not in preview


def test_persona_delete_removes_only_dating_data(client, db):
    a = _approved(db, "delete-a@example.com", "Delete A")
    b = _approved(db, "delete-b@example.com", "Delete B")
    pa = _persona(db, a, gender="male")
    pb = _persona(db, b, gender="female", looking_for="male")
    generate_matches_for_persona(pa)
    db.session.add(DatingBlock(blocker_id=pa.id, blocked_id=pb.id))
    db.session.commit()
    login(client, a.email)
    response = client.post("/dating/delete")
    assert response.status_code == 302
    assert DatingPersona.query.filter_by(profile_id=a.profile.id).first() is None
    assert DatingMatch.query.count() == 0
    assert DatingBlock.query.count() == 0
    assert User.query.filter_by(email=a.email).first() is not None


def test_any_and_nonbinary_preferences_are_mutual(db):
    a = _approved(db, "any-a@example.com", "Any Person")
    b = _approved(db, "nb-b@example.com", "Nonbinary Member")
    pa = _persona(db, a, gender="male", looking_for="any")
    pb = _persona(db, b, gender="nonbinary", looking_for="male")
    assert pa.is_compatible_with(pb)
    assert pb.is_compatible_with(pa)
    assert compute_compatibility(pa, pb) == compute_compatibility(pb, pa)


def test_shared_interests_not_random_state_origin(db):
    a = _approved(db, "score-a@example.com", "Score A")
    b = _approved(db, "score-b@example.com", "Score B")
    pa = _persona(db, a, gender="male", interests="music")
    pb = _persona(db, b, gender="female", looking_for="male", interests="music")
    score_before = compute_compatibility(pa, pb)
    a.profile.state_of_origin = "Lagos"
    b.profile.state_of_origin = "Borno"
    db.session.commit()
    assert compute_compatibility(pa, pb) == score_before
