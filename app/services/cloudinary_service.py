"""Secure image upload handling.

Images are never persisted to the local/Vercel filesystem. Every upload
is validated (extension + real MIME sniff + size), optionally
re-encoded via Pillow to strip metadata and normalize format, then sent
to Cloudinary. Only the resulting URL + public_id are ever stored in
PostgreSQL.
"""
import io
import uuid

import cloudinary
import cloudinary.uploader
from flask import current_app
from PIL import Image

_configured = False


class ImageUploadError(Exception):
    pass


def _ensure_configured():
    global _configured
    if _configured:
        return
    cloudinary.config(
        cloud_name=current_app.config.get("CLOUDINARY_CLOUD_NAME"),
        api_key=current_app.config.get("CLOUDINARY_API_KEY"),
        api_secret=current_app.config.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    _configured = True


def _validate(file_storage):
    filename = (file_storage.filename or "").rsplit(".", 1)
    ext = filename[-1].lower() if len(filename) == 2 else ""
    allowed_ext = current_app.config["ALLOWED_IMAGE_EXTENSIONS"]
    if ext not in allowed_ext:
        raise ImageUploadError(f"Unsupported file extension: .{ext or '?'}")

    if file_storage.mimetype not in current_app.config["ALLOWED_IMAGE_MIMETYPES"]:
        raise ImageUploadError("Unsupported image MIME type.")

    file_storage.stream.seek(0, io.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(0)
    if size > current_app.config["MAX_CONTENT_LENGTH"]:
        raise ImageUploadError("Image exceeds the maximum allowed size.")
    if size == 0:
        raise ImageUploadError("Empty file upload.")

    # Sniff real image content with Pillow (never trust the extension alone)
    try:
        img = Image.open(file_storage.stream)
        img.verify()
    except Exception:
        raise ImageUploadError("File is not a valid image.")
    file_storage.stream.seek(0)
    return img


def _reencode(file_storage, max_dimension=1600):
    """Re-encode to strip EXIF/metadata and cap dimensions, return bytes+format."""
    file_storage.stream.seek(0)
    img = Image.open(file_storage.stream)
    img = img.convert("RGB") if img.mode not in ("RGB", "RGBA") else img

    w, h = img.size
    if max(w, h) > max_dimension:
        ratio = max_dimension / float(max(w, h))
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    buffer = io.BytesIO()
    save_format = "JPEG" if img.mode == "RGB" else "PNG"
    img.save(buffer, format=save_format, quality=85, optimize=True)
    buffer.seek(0)
    return buffer, save_format.lower()


def upload_image(file_storage, folder: str) -> dict:
    """Validate, sanitize, and upload an image. Returns {url, public_id}.

    `folder` should be something like "platoon5/profiles" or
    "platoon5/businesses" to keep the Cloudinary account organized.

    Raises ImageUploadError (never a raw exception) for every failure mode,
    including Cloudinary being unconfigured or the upload call itself
    failing (bad credentials, network issue, quota, etc.) -- callers
    already handle ImageUploadError by flashing the message and re-showing
    the form, so every failure here is visible to the person uploading
    rather than silently discarding what they picked.
    """
    _validate(file_storage)
    buffer, fmt = _reencode(file_storage)

    if not current_app.config.get("CLOUDINARY_CLOUD_NAME"):
        current_app.logger.warning(
            "CLOUDINARY_CLOUD_NAME not set -- image upload rejected. "
            "Configure CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET to enable photo uploads."
        )
        raise ImageUploadError(
            "Image uploads aren't configured yet on this site. Your other changes were "
            "saved, but the photo wasn't. Contact the site administrator."
        )

    _ensure_configured()
    safe_public_id = f"{folder}/{uuid.uuid4().hex}"

    try:
        result = cloudinary.uploader.upload(
            buffer,
            public_id=safe_public_id,
            overwrite=True,
            format=fmt,
            resource_type="image",
        )
    except Exception as exc:
        current_app.logger.error("Cloudinary upload failed: %s", exc)
        raise ImageUploadError(
            "The image upload failed (a network or storage-service issue on our end, "
            "not something wrong with your file). Your other changes were saved -- "
            "please try uploading the photo again."
        )

    return {"url": result.get("secure_url"), "public_id": result.get("public_id")}


def delete_image(public_id: str) -> None:
    if not public_id:
        return
    _ensure_configured()
    try:
        cloudinary.uploader.destroy(public_id)
    except Exception as exc:  # pragma: no cover - network dependent
        current_app.logger.warning("Cloudinary delete failed for %s: %s", public_id, exc)
