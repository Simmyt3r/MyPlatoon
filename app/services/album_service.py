"""Orchestrates album PDF generation, storage, and versioning.

A new PDF is only generated when an admin explicitly requests it (see
Section 15 of the spec: "Do not regenerate a massive PDF
unnecessarily"). The database (AlbumVersion.pdf_data) is the source of
truth for downloads -- Cloudinary upload is attempted as a best-effort
secondary copy (e.g. for sharing a link outside the app) but never
blocks generation or breaks downloads if it fails or is restricted. See
DEPLOYMENT.md for why relying on Cloudinary alone for PDF delivery is
fragile: some accounts block public delivery of PDF/raw files by
default regardless of how the file was uploaded.
"""
import urllib.error
import urllib.request

import cloudinary
import cloudinary.uploader
from flask import current_app

from app.extensions import db
from app.models import AlbumVersion, Profile, Business, Platoon
from app.services.pdf_service import build_album_pdf


class AlbumFetchError(Exception):
    """Raised when a previously-uploaded album PDF can't be retrieved from
    Cloudinary (only relevant for pre-existing rows with no pdf_data --
    see generate_new_album_version).

    `admin_hint` is a precise, technical explanation safe to show to an
    admin (who can act on it); the generic member-facing message stays in
    the route, since a regular member can't do anything about a storage
    misconfiguration and shouldn't see the internals.
    """
    def __init__(self, message, admin_hint=None):
        super().__init__(message)
        self.admin_hint = admin_hint or message


def _next_version_label() -> str:
    latest = AlbumVersion.query.order_by(AlbumVersion.id.desc()).first()
    if not latest:
        return "1.0"
    try:
        major, minor = latest.version_label.split(".")
        return f"{major}.{int(minor) + 1}"
    except (ValueError, AttributeError):
        return f"{latest.id + 1}.0"


def _upload_pdf_bytes(pdf_bytes: bytes, version_label: str) -> dict:
    """Best-effort secondary copy on Cloudinary. Never raises -- any
    failure (missing credentials, bad credentials, network error, quota,
    the PDF/ZIP delivery restriction, etc.) just means no secondary copy
    exists; the database copy (pdf_data) is what downloads actually use,
    so this is never allowed to block album generation.
    """
    if not current_app.config.get("CLOUDINARY_CLOUD_NAME"):
        current_app.logger.info(
            "CLOUDINARY_CLOUD_NAME not set — skipping the optional Cloudinary "
            "backup copy of this album. Downloads are unaffected (served from "
            "the database)."
        )
        return {"url": None, "public_id": None}

    try:
        cloudinary.config(
            cloud_name=current_app.config["CLOUDINARY_CLOUD_NAME"],
            api_key=current_app.config["CLOUDINARY_API_KEY"],
            api_secret=current_app.config["CLOUDINARY_API_SECRET"],
            secure=True,
        )
        # The .pdf suffix on the public_id (plus format=) is what tells
        # Cloudinary this raw resource is a PDF -- without it, Cloudinary
        # has no extension to infer a content type from.
        public_id = f"platoon5/albums/album_v{version_label.replace('.', '_')}.pdf"
        result = cloudinary.uploader.upload(
            pdf_bytes, resource_type="raw", public_id=public_id, format="pdf", overwrite=True,
        )
        return {"url": result.get("secure_url"), "public_id": result.get("public_id")}
    except Exception as exc:  # pragma: no cover - network/credentials dependent
        current_app.logger.warning(
            "Cloudinary backup upload failed for album v%s (downloads are unaffected, "
            "served from the database): %s", version_label, exc
        )
        return {"url": None, "public_id": None}


def fetch_album_pdf_bytes(pdf_url: str) -> bytes:
    """Fetch a previously-uploaded album PDF's raw bytes from Cloudinary.

    Only used as a fallback for album versions generated before pdf_data
    existed (see download() in app/blueprints/album/routes.py) -- new
    versions are served directly from the database and never call this.

    Raises AlbumFetchError with a specific, actionable admin_hint instead
    of letting the raw urllib exception bubble up as an opaque failure --
    a 401/403 here almost always means one specific, well-documented
    Cloudinary account setting, not a transient/network problem, so the
    route can tell an admin exactly what to check rather than "try again".
    """
    try:
        with urllib.request.urlopen(pdf_url, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise AlbumFetchError(
                "Cloudinary rejected the request for this file.",
                admin_hint=(
                    f"Cloudinary returned HTTP {exc.code} for the album PDF. This is an "
                    "old album version stored only on Cloudinary (generated before this "
                    "app started keeping a database copy) -- generate a new album version "
                    "to get one that downloads reliably regardless of Cloudinary settings. "
                    "If you want this old version specifically: Cloudinary -> Settings -> "
                    "Security -> \"PDF and ZIP files delivery\" -> check \"Allow delivery of "
                    "PDF and ZIP files\" -> Save -> accept the terms of service prompt."
                ),
            ) from exc
        raise AlbumFetchError(
            "Cloudinary returned an error for this file.",
            admin_hint=f"Cloudinary returned HTTP {exc.code} ({exc.reason}) for the album PDF.",
        ) from exc
    except urllib.error.URLError as exc:
        raise AlbumFetchError(
            "Could not reach file storage.",
            admin_hint=f"Network error fetching the album PDF from Cloudinary: {exc.reason}.",
        ) from exc
    except TimeoutError as exc:
        raise AlbumFetchError(
            "The request to file storage timed out.",
            admin_hint="Fetching the album PDF from Cloudinary timed out after 30s -- "
                       "the file may be unusually large, or Cloudinary/network is slow "
                       "right now. Usually resolves on retry.",
        ) from exc


def generate_new_album_version(generated_by) -> AlbumVersion:
    approved_profiles = (
        Profile.query.filter_by(status="approved")
        .order_by(Profile.state_of_origin.asc(), Profile.id.asc())
        .all()
    )
    active_businesses = (
        Business.query.filter_by(is_active=True)
        .join(Profile, Business.profile_id == Profile.id)
        .filter(Profile.status == "approved")
        .all()
    )

    version_label = _next_version_label()
    pdf_bytes = build_album_pdf(approved_profiles, active_businesses, version_label)
    upload_result = _upload_pdf_bytes(pdf_bytes, version_label)

    version = AlbumVersion(
        version_label=version_label,
        pdf_url=upload_result["url"] or "",
        pdf_public_id=upload_result["public_id"],
        pdf_data=pdf_bytes,
        member_count=len(approved_profiles),
        generated_by_id=generated_by.id if generated_by else None,
        status="published",
    )
    db.session.add(version)
    db.session.commit()
    return version, pdf_bytes


def latest_published_album():
    return (
        AlbumVersion.query.filter_by(status="published")
        .order_by(AlbumVersion.generated_at.desc())
        .first()
    )
