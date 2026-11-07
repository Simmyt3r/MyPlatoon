"""Graceful dependency failures must not turn into insecure fallbacks."""
from sqlalchemy.exc import OperationalError
from redis.exceptions import ConnectionError as RedisConnectionError


def test_database_outage_returns_plain_503_without_sensitive_details(app, client):
    @app.get("/_test_database_outage")
    def database_outage():
        raise OperationalError(
            "SELECT secret FROM private_data",
            {},
            RuntimeError("postgresql://user:SECRET@host.example:5432/db"),
        )

    response = client.get("/_test_database_outage")
    assert response.status_code == 503
    assert response.headers["Retry-After"] == "60"
    assert response.headers["Cache-Control"] == "no-store"
    assert b"temporarily unavailable" in response.data.lower()
    assert b"SECRET" not in response.data
    assert b"private_data" not in response.data
    assert b"Traceback" not in response.data
    assert b'href="/"' in response.data


def test_database_outage_returns_json_on_api_request(app, client):
    @app.get("/_test_api_outage")
    def api_outage():
        raise OperationalError(
            "SELECT 1", {},
            RuntimeError("SECRET_DATABASE_CONNECTION"),
        )

    response = client.get(
        "/_test_api_outage", headers={"Accept": "application/json"},
    )
    assert response.status_code == 503
    assert response.json["error"] == "service_unavailable"
    assert "SECRET" not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store"


def test_redis_unavailable_returns_503_not_unguarded_success(app, client):
    @app.post("/_test_redis_outage")
    def redis_outage():
        raise RedisConnectionError("rediss://operator:PRIVATE@host:6380")

    response = client.post("/_test_redis_outage")
    assert response.status_code == 503
    assert b"PRIVATE" not in response.data
    assert response.headers["Retry-After"] == "60"


def test_public_landing_remains_independent_of_database(client, monkeypatch):
    from app.extensions import db

    def fail(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, RuntimeError("offline"))

    monkeypatch.setattr(db.session, "execute", fail)
    response = client.get("/")
    assert response.status_code == 200
    assert b"MyPlatoon" in response.data
