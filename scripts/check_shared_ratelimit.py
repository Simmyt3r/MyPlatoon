"""Read-only production Redis rate-limit readiness check.

Usage (with Vercel production environment exported):
    python scripts/check_shared_ratelimit.py

Never prints connection URLs, credentials, stack traces, or Redis error text.
Exit 0 only when strict enforcement is configured and Redis responds to PING.
This check does not change configuration or user/database data.
"""
import os
import sys
from urllib.parse import urlsplit


def probe(uri, strict, redis_factory=None):
    """Return (ready, sanitized_reason) without disclosing secrets."""
    if not strict:
        return False, "Strict shared rate-limit enforcement is disabled."
    if not uri:
        return False, "Shared Redis storage URI is missing."
    try:
        parsed = urlsplit(uri)
    except ValueError:
        return False, "Shared Redis storage URI is invalid."
    if parsed.scheme not in ("redis", "rediss") or not parsed.hostname:
        return False, "Shared Redis storage URI must use redis:// or rediss://."
    try:
        if redis_factory is None:
            from redis import Redis
            redis_factory = Redis.from_url
        client = redis_factory(
            uri, socket_connect_timeout=3, socket_timeout=3,
        )
        try:
            if not client.ping():
                return False, "Redis did not respond successfully."
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                close()
    except Exception:
        # A provider error often embeds the hostname or credential in its
        # message. No raw exception text should be displayed.
        return False, "Shared Redis connectivity check failed."
    return True, "Strict shared Redis rate limiting is configured and reachable."


def main():
    ready, message = probe(
        os.environ.get("RATELIMIT_STORAGE_URI"),
        os.environ.get("REQUIRE_SHARED_RATELIMIT", "").lower() == "true",
    )
    print(("PASS: " if ready else "FAIL: ") + message)
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
