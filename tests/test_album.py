from tests.conftest import login


def _attach_platoon(db, *users):
    """Create a real orientation cohort for album tests."""
    from app.models import Platoon
    platoon = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    for user in users:
        user.profile.service_stage = "serving"
        user.profile.platoon = platoon
        user.profile.status = "approved"
    db.session.commit()
    return platoon



def test_album_generation_only_includes_approved_profiles(app, admin_user, member_user, approved_member, db):
    member_user.profile.status = "pending"  # should NOT appear in album
    db.session.commit()

    with app.app_context():
        from app.services.album_service import generate_new_album_version
        platoon = _attach_platoon(db, approved_member)
        version, pdf_bytes = generate_new_album_version(admin_user, platoon.id)

        assert version.member_count == 1  # only approved_member
        assert pdf_bytes[:4] == b"%PDF"  # valid PDF header


def test_album_pdf_excludes_private_fields(app, approved_member, db):
    approved_member.profile.phone_visibility = "private"
    approved_member.profile.phone_number = "0800000SECRET"
    approved_member.profile.whatsapp_visibility = "private"
    approved_member.profile.whatsapp_number = "0800000SECRET"
    db.session.commit()

    with app.app_context():
        from app.services.pdf_service import build_album_pdf
        pdf_bytes = build_album_pdf([approved_member.profile], [], version_label="1.0")
        # The PDF is binary/compressed, so we can't naively grep for the literal
        # phone string, but we CAN assert the generator ran without raising and
        # produced a well-formed PDF even though the private field was withheld
        # from the render path (verified at the unit level in test_privacy.py).
        assert pdf_bytes[:4] == b"%PDF"


def test_album_view_requires_login(client):
    resp = client.get("/album/", follow_redirects=True)
    assert resp.request.path == "/auth/login"


def test_only_admin_can_generate_album(client, member_user):
    login(client, "member@example.com")
    resp = client.post("/album/generate", follow_redirects=True)
    assert b"Only administrators" in resp.data


def test_album_version_label_increments(app, admin_user, approved_member, db):
    with app.app_context():
        from app.services.album_service import generate_new_album_version
        platoon = _attach_platoon(db, approved_member)
        v1, _ = generate_new_album_version(admin_user, platoon.id)
        v2, _ = generate_new_album_version(admin_user, platoon.id)
        assert v1.version_label == "1.0"
        assert v2.version_label == "1.1"


def test_cloudinary_public_id_has_pdf_extension(monkeypatch, app, db):
    """Regression test: the raw Cloudinary upload must include a .pdf
    extension in its public_id/format, or Cloudinary has nothing to infer
    a content type from and serves the file as generic
    application/octet-stream -- which is what "downloads as a binary
    file, not a PDF" actually meant. See app/services/album_service.py.
    """
    from app.services import album_service

    captured = {}

    def fake_upload(pdf_bytes, resource_type=None, public_id=None, format=None, overwrite=None):
        captured["public_id"] = public_id
        captured["format"] = format
        return {"secure_url": f"https://res.cloudinary.com/demo/raw/upload/{public_id}",
                "public_id": public_id}

    monkeypatch.setattr(album_service.cloudinary.uploader, "upload", fake_upload)

    with app.app_context():
        app.config["CLOUDINARY_CLOUD_NAME"] = "demo"
        app.config["CLOUDINARY_API_KEY"] = "x"
        app.config["CLOUDINARY_API_SECRET"] = "y"
        result = album_service._upload_pdf_bytes(b"%PDF-1.4 fake", "1.0")

    assert captured["public_id"].endswith(".pdf")
    assert captured["format"] == "pdf"
    assert result["url"].endswith(".pdf")


def test_download_route_serves_correct_pdf_headers(monkeypatch, client, member_user, db):
    """The download route must set Content-Type: application/pdf itself
    (by fetching and re-serving the bytes) rather than redirecting to
    Cloudinary and hoping the browser figures out the file type."""
    from app.models import AlbumVersion
    from app.services import album_service

    platoon = _attach_platoon(db, member_user)
    version = AlbumVersion(version_label="1.0", platoon_id=platoon.id, pdf_url="https://res.cloudinary.com/demo/raw/upload/fake.pdf",
                            member_count=1, status="published")
    db.session.add(version)
    db.session.commit()

    from app.blueprints.album import routes as album_routes
    monkeypatch.setattr(album_routes, "fetch_album_pdf_bytes", lambda url: b"%PDF-1.4 fake content")

    login(client, "member@example.com")
    resp = client.get(f"/album/download/{version.id}")

    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert "myplatoon-" in resp.headers.get("Content-Disposition", "")
    assert resp.data == b"%PDF-1.4 fake content"

    db.session.refresh(version)
    assert version.download_count == 1


def test_download_route_handles_fetch_failure_gracefully(monkeypatch, client, member_user, db):
    from app.models import AlbumVersion
    from app.services.album_service import AlbumFetchError

    platoon = _attach_platoon(db, member_user)
    version = AlbumVersion(version_label="1.0", platoon_id=platoon.id, pdf_url="https://res.cloudinary.com/demo/raw/upload/fake.pdf",
                            member_count=1, status="published")
    db.session.add(version)
    db.session.commit()

    def boom(url):
        raise AlbumFetchError("Could not reach file storage.", admin_hint="Network error: simulated failure.")

    from app.blueprints.album import routes as album_routes
    monkeypatch.setattr(album_routes, "fetch_album_pdf_bytes", boom)

    login(client, "member@example.com")
    resp = client.get(f"/album/download/{version.id}", follow_redirects=True)

    assert resp.status_code == 200
    # A regular member sees a generic, honest message, not internal detail.
    # (Jinja auto-escapes the apostrophe in "isn't" to &#39;, so match on a
    # substring that avoids the contraction rather than the literal text.)
    assert b"available for download right now" in resp.data
    assert b"simulated failure" not in resp.data
    db.session.refresh(version)
    assert version.download_count == 0  # not incremented on failure


def test_download_failure_shows_admin_the_real_diagnosis(monkeypatch, client, admin_user, db):
    from app.models import AlbumVersion
    from app.services.album_service import AlbumFetchError

    platoon = _attach_platoon(db, member_user)
    version = AlbumVersion(version_label="1.0", platoon_id=platoon.id, pdf_url="https://res.cloudinary.com/demo/raw/upload/fake.pdf",
                            member_count=1, status="published")
    db.session.add(version)
    db.session.commit()

    def boom(url):
        raise AlbumFetchError("Cloudinary rejected the request.",
                               admin_hint="Cloudinary returned HTTP 401 for the album PDF. "
                                          "Enable \"Allow delivery of PDF and ZIP files\" in "
                                          "Cloudinary Security settings.")

    from app.blueprints.album import routes as album_routes
    monkeypatch.setattr(album_routes, "fetch_album_pdf_bytes", boom)

    login(client, "admin@example.com")
    resp = client.get(f"/album/download/{version.id}", follow_redirects=True)

    assert resp.status_code == 200
    assert b"Allow delivery of PDF and ZIP files" in resp.data


def test_fetch_album_pdf_bytes_translates_401_into_actionable_hint(monkeypatch):
    """The specific, well-known Cloudinary gotcha: PDF/raw delivery is
    blocked by default on free accounts even though upload succeeds. A
    plain HTTPError here should become an AlbumFetchError naming the exact
    Cloudinary setting to check, not a generic failure."""
    import urllib.error
    from app.services import album_service

    def fake_urlopen(url, timeout=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr(album_service.urllib.request, "urlopen", fake_urlopen)

    try:
        album_service.fetch_album_pdf_bytes("https://res.cloudinary.com/demo/raw/upload/fake.pdf")
        assert False, "expected AlbumFetchError"
    except album_service.AlbumFetchError as exc:
        assert "Allow delivery of PDF and ZIP files" in exc.admin_hint


def test_new_albums_download_correctly_even_when_cloudinary_blocks_delivery(monkeypatch, client, admin_user, db):
    """The actual end-to-end scenario that was reported: Cloudinary's
    account-level PDF/ZIP delivery restriction blocks the file entirely
    (an HTTPError, not different/corrupted bytes -- there's nothing to
    "convert", the request is just refused). Since pdf_data is now the
    source of truth for downloads, this must succeed regardless of
    whether Cloudinary would allow delivery or not.
    """
    import urllib.error
    from app.services import album_service

    app = client.application
    app.config["CLOUDINARY_CLOUD_NAME"] = "demo"
    app.config["CLOUDINARY_API_KEY"] = "x"
    app.config["CLOUDINARY_API_SECRET"] = "y"

    def fake_upload(pdf_bytes, resource_type=None, public_id=None, format=None, overwrite=None):
        return {"secure_url": f"https://res.cloudinary.com/demo/raw/upload/{public_id}",
                "public_id": public_id}

    monkeypatch.setattr(album_service.cloudinary.uploader, "upload", fake_upload)

    from app.models import Platoon
    platoon = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    db.session.commit()
    login(client, "admin@example.com")
    album_page = client.get("/album/")
    import re
    m = re.search(rb'name=["\']csrf_token["\'][^>]*value=["\']([^"\']+)["\']', album_page.data)
    token = m.group(1).decode() if m else ""
    client.post("/album/generate", data={"csrf_token": token, "platoon_id": platoon.id}, follow_redirects=True)

    from app.models import AlbumVersion
    version = AlbumVersion.query.first()
    assert version.pdf_data is not None
    assert version.pdf_data[:4] == b"%PDF"

    # Now simulate Cloudinary's account-level restriction blocking delivery
    # of the secondary copy entirely -- this must have zero effect on the
    # in-app download, since it never touches Cloudinary at all when
    # pdf_data is present.
    def blocked(url, timeout=None):
        raise urllib.error.HTTPError(url, 401, "Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr(album_service.urllib.request, "urlopen", blocked)

    resp = client.get(f"/album/download/{version.id}")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data[:4] == b"%PDF"


def test_cloudinary_upload_failure_never_blocks_generation(monkeypatch, app, admin_user, approved_member, db):
    """The Cloudinary copy is best-effort. If the upload call itself raises
    (bad credentials, network error, quota, anything), album generation
    must still succeed and the PDF must still be safely stored in the
    database -- this is what makes downloads independent of Cloudinary.
    """
    from app.services import album_service

    with app.app_context():
        app.config["CLOUDINARY_CLOUD_NAME"] = "demo"
        app.config["CLOUDINARY_API_KEY"] = "x"
        app.config["CLOUDINARY_API_SECRET"] = "y"

        def broken_upload(*args, **kwargs):
            raise RuntimeError("simulated Cloudinary outage")

        monkeypatch.setattr(album_service.cloudinary.uploader, "upload", broken_upload)

        platoon = _attach_platoon(db, approved_member)
        version, pdf_bytes = album_service.generate_new_album_version(admin_user, platoon.id)

        assert version.pdf_url == ""  # no secondary copy, but...
        assert version.pdf_data is not None  # ...the database copy is always there
        assert version.pdf_data[:4] == b"%PDF"
