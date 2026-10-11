from tests.conftest import login


def _get_category_id(db, name="Technology"):
    from app.models import BusinessCategory
    return BusinessCategory.query.filter_by(name=name).first().id


def test_create_business(client, member_user, db):
    login(client, "member@example.com")
    category_id = _get_category_id(db)

    resp = client.post("/business/new", data={
        "name": "Test Tech Co",
        "category_id": str(category_id),
        "description": "We build things.",
        "address": "", "phone": "", "whatsapp": "", "email": "",
        "website": "", "facebook": "", "instagram": "", "tiktok": "", "twitter_x": "",
    }, follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Business
    biz = Business.query.filter_by(name="Test Tech Co").first()
    assert biz is not None
    assert biz.profile_id == member_user.profile.id


def test_update_business(client, member_user, db):
    login(client, "member@example.com")
    category_id = _get_category_id(db)
    client.post("/business/new", data={
        "name": "Old Name", "category_id": str(category_id), "description": "",
        "address": "", "phone": "", "whatsapp": "", "email": "",
        "website": "", "facebook": "", "instagram": "", "tiktok": "", "twitter_x": "",
    }, follow_redirects=True)

    from app.models import Business
    biz = Business.query.filter_by(name="Old Name").first()

    resp = client.post(f"/business/{biz.id}/edit", data={
        "name": "New Name", "category_id": str(category_id), "description": "Updated",
        "address": "", "phone": "", "whatsapp": "", "email": "",
        "website": "", "facebook": "", "instagram": "", "tiktok": "", "twitter_x": "",
    }, follow_redirects=True)
    assert resp.status_code == 200

    db.session.refresh(biz)
    assert biz.name == "New Name"
    assert biz.description == "Updated"


def test_cannot_edit_others_business(client, member_user, admin_user, db):
    category_id = _get_category_id(db)
    login(client, "member@example.com")
    client.post("/business/new", data={
        "name": "Owned By Member", "category_id": str(category_id), "description": "",
        "address": "", "phone": "", "whatsapp": "", "email": "",
        "website": "", "facebook": "", "instagram": "", "tiktok": "", "twitter_x": "",
    }, follow_redirects=True)
    client.get("/auth/logout")

    from app.models import Business
    biz = Business.query.filter_by(name="Owned By Member").first()

    from tests.conftest import _create_user
    other = _create_user(db, "other@example.com", full_name="Other Member")
    login(client, "other@example.com")
    resp = client.get(f"/business/{biz.id}/edit")
    assert resp.status_code == 403


def test_business_directory_search_by_category(client, approved_member, db):
    category_id = _get_category_id(db, "Health")
    from app.models import Business
    db.session.add(Business(profile_id=approved_member.profile.id, name="Health Hub",
                             category_id=category_id, is_active=True))
    db.session.commit()

    resp = client.get(f"/directory/businesses?category={category_id}")
    assert resp.status_code == 200
    assert b"Health Hub" in resp.data


def test_business_directory_search_by_query(client, approved_member, db):
    category_id = _get_category_id(db)
    from app.models import Business
    db.session.add(Business(profile_id=approved_member.profile.id, name="Unique Widget Co",
                             category_id=category_id, is_active=True))
    db.session.commit()

    resp = client.get("/directory/businesses?q=Unique")
    assert b"Unique Widget Co" in resp.data

    resp2 = client.get("/directory/businesses?q=NoMatchHere")
    assert b"Unique Widget Co" not in resp2.data
