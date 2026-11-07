"""Lightweight health endpoints with no account, template or setup dependencies.

Liveness means Flask can handle a request. Readiness means DB responds and
the configured production rate-limiter is safely usable. Neither probes
mutate user data or disclose service URLs or exception messages.
"""
from flask import Blueprint, current_app, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db, limiter

bp = Blueprint("health", __name__)


def _probe_database():
    try:
        with db.engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        current_app.logger.warning("Health database check failed (%s)", type(exc).__name__)
        return False
    except Exception as exc:
        current_app.logger.warning("Health database check unavailable (%s)", type(exc).__name__)
        return False


def _probe_redis(uri):
    client = None
    try:
        from redis import Redis
        client = Redis.from_url(
            uri, socket_connect_timeout=2, socket_timeout=2,
        )
        return bool(client.ping())
    except Exception as exc:
        # Redis provider exceptions may contain passwords and hostnames.
        current_app.logger.warning("Health Redis check failed (%s)", type(exc).__name__)
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _response(body, status=200):
    response = jsonify(body)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    if status == 503:
        response.headers["Retry-After"] = "60"
    return response


@bp.get("/health/live")
@limiter.exempt
def live():
    """No DB, Redis, authentication, user session or Jinja dependency."""
    return _response({"status": "alive"})


@bp.get("/health/ready")
@limiter.exempt
def ready():
    """Fail readiness safely when required services are not healthy."""
    db_ok = _probe_database()
    config = current_app.config
    strict = bool(config.get("REQUIRE_SHARED_RATELIMIT"))
    uri = str(config.get("RATELIMIT_STORAGE_URI") or "")
    configured = uri.startswith(("redis://", "rediss://"))
    production = bool(config.get("IS_PRODUCTION", False))

    if strict and configured:
        redis_ok = _probe_redis(uri)
        rate_limits = "ok" if redis_ok else "unavailable"
    elif production:
        # Existing deployments can remain up during a staged Redis rollout,
        # but monitoring must not mislabel them as security-ready.
        rate_limits = "not_ready"
    else:
        rate_limits = "not_required"

    ready = db_ok and (rate_limits in ("ok", "not_required"))
    return _response({
        "status": "ready" if ready else "degraded",
        "database": "ok" if db_ok else "unavailable",
        "rate_limits": rate_limits,
    }, 200 if ready else 503)
