"""Unit tests for the secret-safe read-only Redis readiness probe."""
import pytest

from scripts.check_shared_ratelimit import probe


class FakeRedis:
    def __init__(self, result=True):
        self.result = result
        self.closed = False

    def ping(self):
        return self.result

    def close(self):
        self.closed = True


def test_probe_requires_strict_enforcement():
    ready, reason = probe("rediss://localhost:6379/0", False)
    assert not ready
    assert "disabled" in reason


@pytest.mark.parametrize("url", [
    None, "", "memory://", "http://localhost:8080", "rediss://",
    "not a valid url",
])
def test_probe_rejects_missing_or_nonredis_urls(url):
    ready, reason = probe(url, True)
    assert not ready
    assert "Redis" in reason or "URI" in reason


def test_probe_pings_and_closes_redis_with_bounded_timeouts():
    connection = FakeRedis()
    calls = []

    def factory(url, **kwargs):
        calls.append((url, kwargs))
        return connection

    ready, _ = probe("rediss://localhost:6379/0", True, factory)
    assert ready
    assert connection.closed
    assert calls == [(
        "rediss://localhost:6379/0",
        {"socket_connect_timeout": 3, "socket_timeout": 3},
    )]


def test_probe_rejects_failed_ping_and_closes():
    connection = FakeRedis(False)
    ready, _ = probe("redis://localhost:6379/0", True,
                     lambda url, **kwargs: connection)
    assert not ready
    assert connection.closed


def test_probe_sanitizes_provider_errors_with_credentials():
    secret = "PRIVATE_REDIS_PASSWORD"
    uri = "rediss://operator:" + secret + "@redis.example.com:6380/0"

    def factory(url, **kwargs):
        raise RuntimeError("connection failed to " + uri)

    ready, message = probe(uri, True, factory)
    assert not ready
    assert secret not in message
    assert "redis.example.com" not in message
