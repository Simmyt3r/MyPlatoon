from tests.conftest import login


def _make_announcement(db, admin_user, title="Test Announcement"):
    from app.models import Announcement
    ann = Announcement(title=title, body="Body text", created_by_id=admin_user.id)
    db.session.add(ann)
    db.session.commit()
    return ann


def test_react_to_announcement_adds_reaction(client, member_user, admin_user, db):
    ann = _make_announcement(db, admin_user)
    login(client, "member@example.com")

    resp = client.post(f"/feed/announcement/{ann.id}/react", data={"reaction_type": "love"},
                        headers={"X-Requested-With": "fetch"})
    data = resp.get_json()
    assert data["state"] == "added"
    assert data["your_reaction"] == "love"
    assert data["total"] == 1


def test_react_again_with_same_type_toggles_off(client, member_user, admin_user, db):
    ann = _make_announcement(db, admin_user)
    login(client, "member@example.com")

    client.post(f"/feed/announcement/{ann.id}/react", data={"reaction_type": "like"},
                headers={"X-Requested-With": "fetch"})
    resp = client.post(f"/feed/announcement/{ann.id}/react", data={"reaction_type": "like"},
                        headers={"X-Requested-With": "fetch"})
    data = resp.get_json()
    assert data["state"] == "removed"
    assert data["your_reaction"] is None
    assert data["total"] == 0


def test_changing_reaction_type_updates_not_duplicates(client, member_user, admin_user, db):
    ann = _make_announcement(db, admin_user)
    login(client, "member@example.com")

    client.post(f"/feed/announcement/{ann.id}/react", data={"reaction_type": "like"},
                headers={"X-Requested-With": "fetch"})
    resp = client.post(f"/feed/announcement/{ann.id}/react", data={"reaction_type": "celebrate"},
                        headers={"X-Requested-With": "fetch"})
    data = resp.get_json()
    assert data["state"] == "updated"
    assert data["your_reaction"] == "celebrate"
    assert data["total"] == 1  # not 2 -- same user, one reaction row


def test_react_requires_login(client, admin_user, db):
    ann = _make_announcement(db, admin_user)
    resp = client.post(f"/feed/announcement/{ann.id}/react", data={"reaction_type": "like"})
    assert resp.status_code in (302, 401)


def test_comment_on_announcement(client, member_user, admin_user, db):
    ann = _make_announcement(db, admin_user)
    login(client, "member@example.com")

    resp = client.post(f"/feed/announcement/{ann.id}/comment", data={"body": "Nice one!"},
                        headers={"X-Requested-With": "fetch"})
    data = resp.get_json()
    assert data["ok"] is True
    assert data["comment"]["body"] == "Nice one!"
    assert data["comment_count"] == 1

    from app.models import Announcement
    fresh = Announcement.query.get(ann.id)
    assert len(fresh.comments) == 1
    assert fresh.comments[0].user_id == member_user.id


def test_empty_comment_is_rejected(client, member_user, admin_user, db):
    ann = _make_announcement(db, admin_user)
    login(client, "member@example.com")

    resp = client.post(f"/feed/announcement/{ann.id}/comment", data={"body": "   "},
                        headers={"X-Requested-With": "fetch"})
    from app.models import Announcement
    fresh = Announcement.query.get(ann.id)
    assert len(fresh.comments) == 0


def test_comment_requires_login(client, admin_user, db):
    ann = _make_announcement(db, admin_user)
    resp = client.post(f"/feed/announcement/{ann.id}/comment", data={"body": "hi"})
    assert resp.status_code in (302, 401)


def test_search_finds_matching_member(client, approved_member):
    resp = client.get("/search?q=Approved")
    assert resp.status_code == 200
    assert b"Approved Member" in resp.data


def test_search_finds_matching_business(client, approved_member, db):
    from app.models import Business, BusinessCategory
    cat = BusinessCategory.query.first()
    db.session.add(Business(profile_id=approved_member.profile.id, name="Zephyr Tech",
                             category_id=cat.id, is_active=True))
    db.session.commit()

    resp = client.get("/search?q=Zephyr")
    assert b"Zephyr Tech" in resp.data


def test_search_empty_query_shows_prompt(client):
    resp = client.get("/search")
    assert resp.status_code == 200


def test_community_feed_renders_with_announcements_and_reactions(client, member_user, admin_user, db):
    ann = _make_announcement(db, admin_user, title="Welcome!")
    login(client, "member@example.com")
    resp = client.get("/feed")
    assert resp.status_code == 200
    assert b"Welcome!" in resp.data
    assert b"Community feed" in resp.data
    # Marketing and community posts are intentionally separate.
    assert b"Welcome!" not in client.get("/").data


def test_categories_auto_seeded_on_app_creation(app, db):
    from app.models import BusinessCategory
    with app.app_context():
        assert BusinessCategory.query.count() == 17
