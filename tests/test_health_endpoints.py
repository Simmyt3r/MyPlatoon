"""Health endpoints distinguish process liveness from dependency readiness."""
from sqlalchemy.exc import OperationalError

from app.blueprints.main import health


def test_liveness_has_no_db_or_redis_dependency(client, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("liveness may not query dependencies")
    monkeypatch.setattr(health, "_probe_database", forbidden)
    monkeypatch.setattr(health, "_probe_redis", forbidden)
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json == {"status": "alive"}
    assert res.headers["Cache-Control"] == "no-store"


def test_readiness_reports_database_failure_without_secrets(client, monkeypatch):
    monkeypatch.setattr(health, "_probe_database", lambda: False)
    res = client.get("/health/ready")
    assert res.status_code == 503
    assert res.json["database"] == "unavailable"
    assert res.json["status"] == "degraded"
    assert res.headers["Retry-After"] == "60"
    assert "password" not in res.get_data(as_text=True).lower()


def test_readiness_succeeds_with_dev_database(client, monkeypatch):
    monkeypatch.setattr(health, "_probe_database", lambda: True)
    res = client.get("/health/ready")
    assert res.status_code == 200
    assert res.json == {
        "status": "ready", "database": "ok", "schema": "ok",
        "rate_limits": "not_required",
    }


def test_production_readiness_flags_absent_shared_limiter(app, client, monkeypatch):
    monkeypatch.setattr(health, "_probe_database", lambda: True)
    monkeypatch.setattr(health, "_probe_schema", lambda: True)
    app.config.update(
        IS_PRODUCTION=True,
        REQUIRE_SHARED_RATELIMIT=False,
        RATELIMIT_STORAGE_URI="memory://",
    )
    res = client.get("/health/ready")
    assert res.status_code == 503
    assert res.json["database"] == "ok"
    assert res.json["rate_limits"] == "not_ready"


def test_production_readiness_pings_shared_redis(app, client, monkeypatch):
    monkeypatch.setattr(health, "_probe_database", lambda: True)
    app.config.update(
        IS_PRODUCTION=True,
        REQUIRE_SHARED_RATELIMIT=True,
        RATELIMIT_STORAGE_URI="rediss://user:SECRET@redis.example.com:6380/0",
    )
    called = []
    monkeypatch.setattr(
        health, "_probe_redis", lambda uri: called.append(uri) or True,
    )
    res = client.get("/health/ready")
    assert res.status_code == 200
    assert called == [app.config["RATELIMIT_STORAGE_URI"]]
    assert "SECRET" not in res.get_data(as_text=True)
    monkeypatch.setattr(health, "_probe_redis", lambda uri: False)
    res = client.get("/health/ready")
    assert res.status_code == 503
    assert res.json["rate_limits"] == "unavailable"


def test_health_database_probe_sanitizes_driver_failure(app, monkeypatch):
    class BadEngine:
        def connect(self):
            raise OperationalError(
                "SELECT 1", {},
                RuntimeError("postgresql://user:SECRET@host/database"),
            )
    from app.extensions import db
    with app.app_context():
        # Exercise the implementation through an injectable db.engine property
        # without opening an actual network connection.
        monkeypatch.setattr(type(db), "engine", property(lambda self: BadEngine()))
        assert health._probe_database() is False


def test_production_not_ready_when_schema_outdated(app, client, monkeypatch):
    monkeypatch.setattr(health, "_probe_database", lambda: True)
    monkeypatch.setattr(health, "_probe_schema", lambda: False)
    monkeypatch.setattr(health, "_probe_redis", lambda uri: True)
    app.config.update(
        IS_PRODUCTION=True,
        REQUIRE_SHARED_RATELIMIT=True,
        RATELIMIT_STORAGE_URI="rediss://user:SECRET@redis.example.com:6380/0",
    )
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json["database"] == "ok"
    assert response.json["schema"] == "not_ready"
    assert response.json["rate_limits"] == "ok"
    assert "SECRET" not in response.get_data(as_text=True)


def test_schema_probe_handles_unversioned_database_safely(app):
    # The normal testing fixture creates tables without Alembic stamping.
    # Readiness must never stamp or migrate such a database automatically.
    with app.app_context():
        assert health._probe_schema() is False
