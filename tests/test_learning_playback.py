"""Server-limited playback enforcement for Silabs Academy."""
from datetime import datetime, timedelta

from app.models.learning import LearningCertificate, LearningProgress, LearningWatch
from tests.conftest import _create_user, login
from tests.test_learning_academy import create_course


def _setup(client, db, admin_user, member_user, monkeypatch):
    course = create_course(db, admin_user, lessons=1)
    lesson = course.lessons[0]
    login(client, member_user.email)
    start = datetime(2026, 10, 31, 12, 0, 0)
    now = [start]
    monkeypatch.setattr("app.services.learning_service.clock_now", lambda: now[0])
    response = client.get(f"/learn/courses/{course.slug}/lessons/{lesson.id}")
    assert response.status_code == 200
    watch = LearningWatch.query.filter_by(
        user_id=member_user.id, lesson_id=lesson.id,
    ).one()
    api = f"/learn/courses/{course.slug}/lessons/{lesson.id}/watch"
    complete = f"/learn/courses/{course.slug}/lessons/{lesson.id}/complete"
    return course, lesson, watch, now, api, complete


def _ping(client, api, watch, position, playing=True, visible=True):
    return client.post(api, json={
        "session": watch.session_id, "position": position,
        "playing": playing, "visible": visible,
    })


def test_completion_endpoint_rejects_direct_post_before_90s(
    client, db, admin_user, member_user, monkeypatch,
):
    _, _, watch, now, api, complete = _setup(
        client, db, admin_user, member_user, monkeypatch,
    )
    response = client.post(complete, follow_redirects=True)
    assert response.status_code == 200
    assert b"Watch at least 1 minute 30 seconds" in response.data
    assert LearningProgress.query.count() == 0
    assert LearningCertificate.query.count() == 0
    assert watch.watched_seconds == 0


def test_seeking_idle_time_and_rapid_requests_earn_no_credit(
    client, db, admin_user, member_user, monkeypatch,
):
    _, _, watch, now, api, complete = _setup(
        client, db, admin_user, member_user, monkeypatch,
    )
    assert _ping(client, api, watch, 0).json["seconds"] == 0
    for i in range(25):
        assert _ping(client, api, watch, i + 1).json["seconds"] == 0
    assert client.post(complete).status_code == 302
    assert LearningProgress.query.count() == 0

    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 250).json["seconds"] == 0
    now[0] += timedelta(seconds=600)
    assert _ping(client, api, watch, 255).json["seconds"] == 0
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 260).json["seconds"] == 5
    assert LearningCertificate.query.count() == 0


def test_paused_hidden_buffering_and_resume_only_credit_playing(
    client, db, admin_user, member_user, monkeypatch,
):
    _, _, watch, now, api, _ = _setup(
        client, db, admin_user, member_user, monkeypatch,
    )
    assert _ping(client, api, watch, 0).json["seconds"] == 0
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 5).json["seconds"] == 5
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 10, playing=False).json["seconds"] == 5
    now[0] += timedelta(seconds=50)
    assert _ping(client, api, watch, 10).json["seconds"] == 5
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 15).json["seconds"] == 10
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 20, visible=False).json["seconds"] == 10
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 25).json["seconds"] == 10
    now[0] += timedelta(seconds=5)
    assert _ping(client, api, watch, 30).json["seconds"] == 15


def test_reloading_rotates_session_but_preserves_earned_time(
    client, db, admin_user, member_user, monkeypatch,
):
    course, lesson, watch, now, api, _ = _setup(
        client, db, admin_user, member_user, monkeypatch,
    )
    old_session = watch.session_id
    _ping(client, api, watch, 0)
    now[0] += timedelta(seconds=5)
    _ping(client, api, watch, 5)
    assert watch.watched_seconds == 5.0
    assert client.get(
        f"/learn/courses/{course.slug}/lessons/{lesson.id}",
    ).status_code == 200
    db.session.refresh(watch)
    assert watch.session_id != old_session
    assert watch.watched_seconds == 5.0
    assert client.post(api, json={
        "session": old_session, "position": 10.0,
        "playing": True, "visible": True,
    }).status_code == 409
    assert watch.watched_seconds == 5.0


def test_other_user_or_invalid_data_cannot_forge_video_time(
    client, db, admin_user, member_user, monkeypatch,
):
    _, _, watch, now, api, _ = _setup(
        client, db, admin_user, member_user, monkeypatch,
    )
    for sample in (None, "90", -20, 1000000, float("inf")):
        result = _ping(client, api, watch, sample)
        assert result.status_code == 409
    assert watch.watched_seconds == 0

    other = _create_user(db, "different-student@example.com")
    client.post("/auth/logout")
    login(client, other.email)
    assert _ping(client, api, watch, 5).status_code == 409
    assert watch.watched_seconds == 0


def test_watch_endpoint_requires_valid_https_csrf_header(
    client, db, app, admin_user, member_user, monkeypatch,
):
    import re

    course, lesson, watch, now, api, _ = _setup(
        client, db, admin_user, member_user, monkeypatch,
    )
    app.config["WTF_CSRF_ENABLED"] = True
    page = client.get(f"/learn/courses/{course.slug}/lessons/{lesson.id}")
    match = re.search(rb'name="csrf_token" value="([^"]+)"', page.data)
    assert match is not None
    watch = LearningWatch.query.filter_by(lesson_id=lesson.id).one()
    body = {
        "session": watch.session_id, "position": 0,
        "playing": True, "visible": True,
    }
    assert client.post(api, json=body).status_code == 400
    accepted = client.post(
        api, json=body,
        headers={"X-CSRFToken": match.group(1).decode()},
    )
    assert accepted.status_code == 200
    assert accepted.json["seconds"] == 0
