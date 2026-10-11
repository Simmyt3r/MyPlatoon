import io

from tests.conftest import login


def test_cannot_edit_others_profile_via_direct_post(client, member_user, db):
    from tests.conftest import _create_user
    other = _create_user(db, "target@example.com", full_name="Target")
    db.session.commit()

    login(client, "member@example.com")
    client.post("/profile/edit", data={"profession": "Hacked"}, follow_redirects=True)

    from app.models import Profile
    target_profile = Profile.query.filter_by(user_id=other.id).first()
    assert target_profile.profession != "Hacked"


def test_private_profile_returns_404_not_403(client, approved_member, db):
    approved_member.profile.profile_visibility = "private"
    db.session.commit()
    resp = client.get(f"/directory/member/{approved_member.profile.slug}")
    assert resp.status_code == 404


def test_platoon_only_profile_hidden_from_guests(client, approved_member, db):
    approved_member.profile.profile_visibility = "platoon"
    db.session.commit()
    resp = client.get(f"/directory/member/{approved_member.profile.slug}")
    assert resp.status_code == 404


def test_platoon_only_profile_visible_to_other_approved_members(client, approved_member, member_user, db):
    approved_member.profile.profile_visibility = "platoon"
    member_user.profile.status = "approved"
    db.session.commit()

    login(client, "member@example.com")
    resp = client.get(f"/directory/member/{approved_member.profile.slug}")
    assert resp.status_code == 200


def test_admin_routes_reject_unauthenticated(client):
    for path in ["/admin/", "/admin/members", "/admin/categories", "/admin/announcements",
                 "/admin/audit-logs"]:
        resp = client.get(path)
        assert resp.status_code in (302, 401, 403)


def test_csrf_protection_enabled_outside_testing_config():
    # WTF_CSRF_ENABLED is deliberately turned off only in the testing config
    # (so form-post tests don't need to juggle tokens); every real deployment
    # config keeps CSRF protection on.
    from app.config import DevelopmentConfig, ProductionConfig, TestingConfig
    assert DevelopmentConfig.WTF_CSRF_ENABLED is True
    assert ProductionConfig.WTF_CSRF_ENABLED is True
    assert TestingConfig.WTF_CSRF_ENABLED is False  # explicit, intentional test-only exception


def test_csrf_field_renders_when_csrf_enabled(member_user, db):
    # Spin up a second app instance with CSRF turned on (mirroring
    # production/development) and confirm the token field is present.
    from app import create_app
    csrf_app = create_app("development")
    csrf_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    csrf_app.config["SERVER_NAME"] = "localhost"
    with csrf_app.test_request_context():
        from app.forms.profile_forms import ProfileForm
        form = ProfileForm()
        rendered = form.hidden_tag()
        assert "csrf_token" in rendered


def test_image_upload_rejects_non_image_file(app):
    with app.test_request_context():
        from app.services.cloudinary_service import upload_image, ImageUploadError
        from werkzeug.datastructures import FileStorage

        fake_file = FileStorage(stream=io.BytesIO(b"not an image, just text"),
                                 filename="malicious.jpg", content_type="image/jpeg")
        try:
            upload_image(fake_file, folder="platoon5/test")
            assert False, "Expected ImageUploadError for non-image content"
        except ImageUploadError:
            pass


def test_image_upload_rejects_disallowed_extension(app):
    with app.test_request_context():
        from app.services.cloudinary_service import upload_image, ImageUploadError
        from werkzeug.datastructures import FileStorage

        fake_file = FileStorage(stream=io.BytesIO(b"#!/bin/sh\necho pwned"),
                                 filename="script.sh", content_type="application/x-sh")
        try:
            upload_image(fake_file, folder="platoon5/test")
            assert False, "Expected ImageUploadError for disallowed extension"
        except ImageUploadError:
            pass


def test_password_never_stored_in_plaintext(db, member_user):
    assert "Password123" not in member_user.password_hash
    assert member_user.password_hash.startswith(("scrypt:", "pbkdf2:"))
