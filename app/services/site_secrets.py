"""Read/write a tiny allowlisted set of encrypted third-party credentials.

The database never contains plaintext API keys. Key derivation requires the
stable, independently provisioned Vercel SECRET_KEY; changing that signing key
requires re-entering these integration secrets.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app
from sqlalchemy import inspect

from app.extensions import db
from app.models.site_secret import SiteSecret

ALLOWED_KEYS = frozenset({
    "CLOUDINARY_CLOUD_NAME", "CLOUDINARY_API_KEY", "CLOUDINARY_API_SECRET",
})


def _cipher():
    secret = current_app.config.get("SECRET_KEY")
    if not isinstance(secret, (str, bytes)) or len(secret) < 32:
        raise RuntimeError("A strong SECRET_KEY is required for encrypted integration settings.")
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    # Domain separation: encryption never directly uses the Flask signing key.
    key = hashlib.sha256(b"MyPlatoon:site-secrets:v1:" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def _available():
    return "site_secrets" in inspect(db.engine).get_table_names()


def saved_keys():
    if not _available():
        return set()
    return {item.key for item in db.session.query(SiteSecret.key).all()}


def save_cloudinary(values, actor):
    """Commit only nonempty allowlisted values; blank input keeps existing keys."""
    cipher = _cipher()
    for key, value in values.items():
        if key not in ALLOWED_KEYS:
            raise ValueError("Unsupported integration key.")
        if not value:
            continue
        if len(value) > 1024:
            raise ValueError("Integration value is too long.")
        row = db.session.get(SiteSecret, key)
        if row is None:
            row = SiteSecret(key=key)
            db.session.add(row)
        row.ciphertext = cipher.encrypt(value.encode("utf-8")).decode("ascii")
        row.updated_by_id = actor.id
    db.session.commit()


def cloudinary_credentials():
    """Return configured Cloudinary values (env values are the fallback)."""
    values = {k: current_app.config.get(k) for k in ALLOWED_KEYS}
    if not _available():
        return values
    cipher = _cipher()
    for row in SiteSecret.query.filter(SiteSecret.key.in_(ALLOWED_KEYS)).all():
        try:
            values[row.key] = cipher.decrypt(row.ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken:
            current_app.logger.error("Cannot decrypt stored integration setting: %s", row.key)
            # Fail closed; do not substitute a possibly different env credential.
            values[row.key] = None
    return values
