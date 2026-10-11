"""QR code generation for member public profile URLs."""
import base64
import io

import qrcode
from flask import current_app, has_request_context, url_for


def profile_public_url(slug: str) -> str:
    """Build the absolute public profile URL for a member.

    Uses the short /profile/<slug> redirect (see main blueprint) rather
    than the canonical /directory/member/<slug> path -- shorter data means
    a less dense, more reliably scannable QR code on a printed page.

    Album/PDF generation can run outside of an HTTP request (e.g. a future
    CLI or scheduled job), where Flask's `url_for` requires SERVER_NAME to
    be configured and would otherwise raise. We prefer `url_for` when a
    request context is active (it stays correct if routes ever move), and
    fall back to a direct path join otherwise so QR/PDF generation never
    breaks regardless of how it's invoked.
    """
    base = current_app.config["APP_BASE_URL"].rstrip("/")
    if has_request_context():
        return f"{base}{url_for('main.public_profile', slug=slug)}"
    return f"{base}/profile/{slug}"


def generate_qr_png_bytes(data: str) -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def generate_qr_data_uri(data: str) -> str:
    png_bytes = generate_qr_png_bytes(data)
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{encoded}"

