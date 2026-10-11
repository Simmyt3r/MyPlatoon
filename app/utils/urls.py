"""Normalizes user-submitted URLs so they always resolve as absolute links.

A member typing "example.com" or "www.example.com" into a website/social
link field (very common -- most people don't think to type "https://")
would otherwise render as `<a href="example.com">`, which browsers treat
as a RELATIVE path off the current page rather than an external site --
clicking it silently 404s instead of opening the intended site.
"""
import re

_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def ensure_scheme(url):
    """Prefix bare domains/paths with https:// if no scheme is present.

    Safe to call on already-well-formed URLs (no-op) or on empty/None
    values (returned unchanged) -- use this both when saving new data and
    when rendering existing data, so already-stored bad values self-heal
    without a backfill migration.
    """
    if not url:
        return url
    url = url.strip()
    if not url:
        return url
    if _SCHEME_RE.match(url):
        return url
    return f"https://{url}"
