from tests.conftest import login


def test_ensure_scheme_util():
    from app.utils.urls import ensure_scheme
    assert ensure_scheme("example.com") == "https://example.com"
    assert ensure_scheme("https://example.com") == "https://example.com"
    assert ensure_scheme("") == ""
    assert ensure_scheme(None) is None


def test_ensure_scheme_filter_applied_to_bare_website(client, approved_member, db):
    approved_member.profile.website = "example.com"  # simulates legacy data, no scheme
    db.session.commit()
    resp = client.get(f"/directory/member/{approved_member.profile.slug}")
    assert b'href="https://example.com"' in resp.data


def test_website_normalized_on_save(client, member_user, db):
    login(client, "member@example.com")
    client.post("/profile/edit", data={
        "state_of_origin": "", "lga": "", "phone_number": "", "whatsapp_number": "",
        "current_location": "", "address": "", "profession": "", "course_of_study": "",
        "institution": "", "graduation_year": "", "certifications": "", "biography": "",
        "skills": "", "website": "example.com", "facebook": "facebook.com/test",
        "instagram": "", "tiktok": "", "twitter_x": "",
    }, follow_redirects=True)

    from app.models import Profile
    profile = Profile.query.filter_by(user_id=member_user.id).first()
    assert profile.website == "https://example.com"
    assert profile.facebook == "https://facebook.com/test"


def test_short_profile_url_redirects_to_canonical(client, approved_member):
    resp = client.get(f"/profile/{approved_member.profile.slug}", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith(f"/directory/member/{approved_member.profile.slug}")

    resp2 = client.get(f"/profile/{approved_member.profile.slug}", follow_redirects=True)
    assert resp2.status_code == 200
    assert b"Approved Member" in resp2.data


def test_qr_uses_short_profile_url(app, approved_member):
    with app.test_request_context():
        from app.services.qr_service import profile_public_url
        url = profile_public_url(approved_member.profile.slug)
        assert f"/profile/{approved_member.profile.slug}" in url
        assert "/directory/member/" not in url


def test_branding_is_config_driven_not_hardcoded(client):
    resp = client.get("/")
    assert resp.status_code == 200
    from flask import current_app
    assert current_app.config["APP_NAME"].encode() in resp.data


def test_upload_without_cloudinary_configured_raises_clear_error(app):
    with app.test_request_context():
        import io
        from werkzeug.datastructures import FileStorage
        from app.services.cloudinary_service import upload_image, ImageUploadError
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (10, 10)).save(buf, format="PNG")
        buf.seek(0)
        fake_file = FileStorage(stream=buf, filename="photo.png", content_type="image/png")

        try:
            upload_image(fake_file, folder="test")
            assert False, "expected ImageUploadError when Cloudinary is unconfigured"
        except ImageUploadError as exc:
            assert "administrator" in str(exc).lower()


def test_profile_edit_saves_other_fields_even_if_photo_upload_fails(client, member_user, db):
    import io
    login(client, "member@example.com")
    # A .png extension containing garbage bytes fails Pillow's real-content
    # check inside upload_image (not just missing Cloudinary config), so
    # this exercises the "photo failed, rest of the form still saves" path.
    resp = client.post("/profile/edit", data={
        "state_of_origin": "Lagos", "lga": "", "phone_number": "", "whatsapp_number": "",
        "current_location": "", "address": "", "profession": "Engineer",
        "course_of_study": "", "institution": "", "graduation_year": "",
        "certifications": "", "biography": "", "skills": "",
        "website": "", "facebook": "", "instagram": "", "tiktok": "", "twitter_x": "",
        "photo": (io.BytesIO(b"not a real image"), "photo.png"),
    }, content_type="multipart/form-data", follow_redirects=True)
    assert resp.status_code == 200

    from app.models import Profile
    profile = Profile.query.filter_by(user_id=member_user.id).first()
    assert profile.profession == "Engineer"
    assert profile.state_of_origin == "Lagos"
