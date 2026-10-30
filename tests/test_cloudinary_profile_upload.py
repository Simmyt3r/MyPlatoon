"""Regression tests for Cloudinary-backed profile photos.

Cloudinary network calls are mocked, but Flask's multipart form, encrypted
admin settings, Pillow re-encoding, SQLAlchemy persistence and replacement
cleanup all run normally.
"""
import io

from PIL import Image
from werkzeug.datastructures import FileStorage

from tests.conftest import login


def _image_bytes(mode="RGB", image_format="JPEG", size=(32, 24)):
    buffer = io.BytesIO()
    image = Image.new(mode, size, (22, 122, 48))
    image.save(buffer, format=image_format)
    return buffer.getvalue()


def _save_admin_cloudinary(app, admin_user):
    from app.services.site_secrets import save_cloudinary, cloudinary_credentials

    app.config["SECRET_KEY"] = "unit-test-key-should-be-at-least-32-characters"
    # No Vercel environment fallback; all three secrets are from /setup's
    # encrypted database storage.
    for key in ("CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET"):
        app.config[key] = None
    values = {
        "CLOUDINARY_CLOUD_NAME": "unit-test-cloud",
        "CLOUDINARY_API_KEY": "unit-test-api-key",
        "CLOUDINARY_API_SECRET": "unit-test-api-secret",
    }
    save_cloudinary(values, admin_user)
    assert cloudinary_credentials() == values


def test_named_stream_from_image_reencoding_has_real_filename(app):
    from app.services.cloudinary_service import _reencode

    with app.app_context():
        jpeg_data = FileStorage(
            stream=io.BytesIO(_image_bytes("RGB", "JPEG")),
            filename="user.jpeg", content_type="image/jpeg",
        )
        stream, fmt = _reencode(jpeg_data)
        assert fmt == "jpg"
        assert stream.name.endswith(".jpg")
        assert Image.open(stream).format == "JPEG"

        png_data = FileStorage(
            stream=io.BytesIO(_image_bytes("RGBA", "PNG")),
            filename="user.png", content_type="image/png",
        )
        stream, fmt = _reencode(png_data)
        assert fmt == "png"
        assert stream.name.endswith(".png")
        assert Image.open(stream).format == "PNG"


def test_profile_photo_upload_uses_encrypted_admin_settings_and_persists(
    client, app, member_user, admin_user, db, monkeypatch,
):
    import cloudinary
    import cloudinary.uploader

    _save_admin_cloudinary(app, admin_user)
    settings_used = {}
    uploads = []

    def fake_config(**kwargs):
        settings_used.update(kwargs)

    def fake_upload(file, **kwargs):
        assert isinstance(file, io.BytesIO)
        assert file.name.endswith(".jpg")
        assert file.read(3) == b"\xff\xd8\xff"
        file.seek(0)
        assert Image.open(file).size == (32, 24)
        uploads.append(kwargs)
        return {
            "secure_url": "https://res.cloudinary.com/unit-test/image/upload/v1/profile.jpg",
            "public_id": "myplatoon/profiles/test-photo-id",
        }

    monkeypatch.setattr(cloudinary, "config", fake_config)
    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)

    login(client, member_user.email)
    response = client.post(
        "/profile/edit",
        data={
            "service_stage": "pcm",
            "profession": "Software Engineer",
            "photo": (io.BytesIO(_image_bytes()), "selfie.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Profile updated successfully" in response.data
    db.session.refresh(member_user.profile)
    assert member_user.profile.profession == "Software Engineer"
    assert member_user.profile.photo_url.endswith("/profile.jpg")
    assert member_user.profile.photo_public_id == "myplatoon/profiles/test-photo-id"
    assert len(uploads) == 1
    assert uploads[0]["format"] == "jpg"
    assert uploads[0]["resource_type"] == "image"
    assert settings_used == {
        "cloud_name": "unit-test-cloud",
        "api_key": "unit-test-api-key",
        "api_secret": "unit-test-api-secret",
        "secure": True,
    }
    assert member_user.profile.photo_url.encode() in client.get("/profile/edit").data


def test_replacing_profile_photo_survives_cloudinary_delete_failure(
    client, app, member_user, admin_user, db, monkeypatch,
):
    import cloudinary.uploader

    _save_admin_cloudinary(app, admin_user)
    member_user.profile.photo_url = "https://res.cloudinary.com/old/image/upload/old.jpg"
    member_user.profile.photo_public_id = "myplatoon/profiles/old-photo"
    db.session.commit()

    monkeypatch.setattr(cloudinary.uploader, "upload", lambda *args, **kw: {
        "secure_url": "https://res.cloudinary.com/unit-test/image/upload/new.jpg",
        "public_id": "myplatoon/profiles/new-photo",
    })
    observed = []

    def failed_cleanup(public_id):
        observed.append((
            public_id,
            member_user.profile.photo_public_id,
        ))
        raise RuntimeError("storage cleanup unavailable")

    monkeypatch.setattr(cloudinary.uploader, "destroy", failed_cleanup)
    login(client, member_user.email)
    response = client.post(
        "/profile/edit",
        data={"service_stage": "pcm",
              "photo": (io.BytesIO(_image_bytes()), "new-photo.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Profile updated successfully" in response.data
    db.session.refresh(member_user.profile)
    assert member_user.profile.photo_public_id == "myplatoon/profiles/new-photo"
    assert observed == [("myplatoon/profiles/old-photo", "myplatoon/profiles/new-photo")]


def test_invalid_cloudinary_upload_result_keeps_old_photo_and_saves_other_fields(
    client, app, member_user, admin_user, db, monkeypatch,
):
    import cloudinary.uploader

    _save_admin_cloudinary(app, admin_user)
    member_user.profile.photo_url = "https://res.cloudinary.com/old/image/upload/old.jpg"
    member_user.profile.photo_public_id = "myplatoon/profiles/old-photo"
    db.session.commit()

    monkeypatch.setattr(cloudinary.uploader, "upload", lambda *a, **kw: {
        "secure_url": None, "public_id": None,
    })
    login(client, member_user.email)
    response = client.post(
        "/profile/edit",
        data={"service_stage": "pcm", "profession": "Designer",
              "photo": (io.BytesIO(_image_bytes()), "new.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Cloudinary did not return a usable photo URL" in response.data
    db.session.refresh(member_user.profile)
    assert member_user.profile.photo_url.endswith("/old.jpg")
    assert member_user.profile.photo_public_id == "myplatoon/profiles/old-photo"
    assert member_user.profile.profession == "Designer"


def test_cloudinary_configuration_error_is_user_friendly_and_never_leaks_secret(
    client, app, member_user, monkeypatch,
):
    from app.services import site_secrets

    marker = "private-credential-never-echo"
    def broken_settings():
        raise RuntimeError(marker)
    monkeypatch.setattr(site_secrets, "cloudinary_credentials", broken_settings)
    login(client, member_user.email)
    response = client.post(
        "/profile/edit",
        data={"service_stage": "pcm",
              "photo": (io.BytesIO(_image_bytes()), "new.jpg")},
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Cloudinary configuration could not be read" in response.data
    assert marker.encode() not in response.data
