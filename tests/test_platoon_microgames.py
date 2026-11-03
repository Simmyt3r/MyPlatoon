"""Digital microgames: automatic counters, caps, quizzes and cohort isolation."""
from datetime import date, timedelta

from app.extensions import db
from app.models import Platoon
from app.models.platoon_microgames import PlatoonGameActivity
from app.models.learning import LearningCourse, LearningLesson, LearningWatch, LearningCertificate
from app.services import platoon_microgames as micro
from tests.conftest import _create_user, login


def camp(db):
    a = Platoon.find_or_create("Benue", 2026, "B", "II", 1)
    b = Platoon.find_or_create("Benue", 2026, "B", "II", 2)
    other = Platoon.find_or_create("Lagos", 2026, "B", "II", 1)
    db.session.commit()
    return a, b, other


def serving(db, email, platoon, *, stage="serving"):
    user = _create_user(db, email)
    user.profile.platoon_id = platoon.id
    user.profile.service_stage = stage
    user.profile.status = "approved"
    db.session.commit()
    return user


def freeze(monkeypatch, today):
    monkeypatch.setattr(micro, "local_today", lambda: today)
    monkeypatch.setattr("app.blueprints.platoons.games.local_today", lambda: today)


def play(client, key, data=None):
    return client.post("/platoons/games/play/" + key, data=data or {})


def test_ten_real_microgames_and_leaderboard_not_manual_results(client, db, monkeypatch):
    a, b, outsider = camp(db)
    freeze(monkeypatch, date(2026, 11, 16))
    res = client.get(f"/platoons/games?platoon_id={a.id}")
    assert res.status_code == 200
    assert len(micro.MICRO_GAMES) == 10
    assert b"GOAL Rush" in res.data
    assert b"NYSC Camp Quiz" in res.data
    assert b"Academy Graduate" in res.data
    assert b"Submit for review" not in res.data
    assert b"Platoon 1" in res.data
    assert b"Platoon 2" in res.data
    assert b"Lagos" not in res.data
    assert PlatoonGameActivity.query.count() == 0


def test_daily_login_counts_once_and_checkin_handles_persistent_session(
    client, db, monkeypatch,
):
    a, _, _ = camp(db)
    user = serving(db, "roll-call@example.com", a)
    freeze(monkeypatch, date(2026, 11, 16))
    login(client, user.email)
    assert PlatoonGameActivity.query.filter_by(game_key="daily-login").count() == 1
    assert play(client, "daily-login").status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="daily-login").count() == 1
    assert client.get(f"/platoons/games?platoon_id={a.id}").status_code == 200

    freeze(monkeypatch, date(2026, 11, 17))
    assert play(client, "daily-login").status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="daily-login").count() == 2
    assert micro.digital_standings(a, date(2026, 11, 15))[0]["actions"] == 2


def test_goal_taps_count_unique_people_not_repeat_clicks(client, db, monkeypatch):
    a, _, _ = camp(db)
    first = serving(db, "goal1@example.com", a)
    second = serving(db, "goal2@example.com", a)
    freeze(monkeypatch, date(2026, 11, 16))
    login(client, first.email)
    for _ in range(8):
        assert play(client, "goal-rush").status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="goal-rush").count() == 1
    client.post("/auth/logout")
    login(client, second.email)
    assert play(client, "goal-rush").status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="goal-rush").count() == 2
    assert micro.digital_standings(a, date(2026, 11, 15))[0]["results"]["goal-rush"]["count"] == 2
    freeze(monkeypatch, date(2026, 11, 17))
    assert play(client, "goal-rush").status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="goal-rush").count() == 3


def test_quiz_requires_correct_answer_and_limits_daily_credit(client, db, monkeypatch):
    a, _, _ = camp(db)
    person = serving(db, "quiz1@example.com", a)
    day = date(2026, 11, 16)
    freeze(monkeypatch, day)
    login(client, person.email)
    for key in ("camp-quiz", "tech-quiz", "number-sprint"):
        question = micro.challenge_question(key, day)
        assert question is not None and len(question[1]) == 3
        incorrect = next(x for x in "ABC" if x != question[2])
        res = play(client, key, {"answer": incorrect})
        assert res.status_code == 302
        assert PlatoonGameActivity.query.filter_by(game_key=key).count() == 0
        assert play(client, key, {"answer": question[2]}).status_code == 302
        assert play(client, key, {"answer": question[2]}).status_code == 302
        assert PlatoonGameActivity.query.filter_by(game_key=key).count() == 1
        assert play(client, key, {"answer": "D"}).status_code == 400


def test_profile_photo_and_ready_are_once_per_round(client, db, monkeypatch):
    a, _, _ = camp(db)
    person = serving(db, "profile-game@example.com", a)
    freeze(monkeypatch, date(2026, 11, 16))
    login(client, person.email)
    assert play(client, "profile-ready").status_code == 302
    assert play(client, "photo-finish").status_code == 302
    assert PlatoonGameActivity.query.filter(
        PlatoonGameActivity.game_key.in_(("profile-ready", "photo-finish")),
    ).count() == 0
    person.profile.profession = "Engineer"
    person.profile.biography = "A professional working on software and technology."
    person.profile.state_of_origin = "Benue"
    person.profile.lga = "Makurdi"
    person.profile.photo_url = "https://res.cloudinary.com/demo/image/upload/test.jpg"
    db.session.commit()
    assert person.profile.completion_percent() >= 50
    for key in ("profile-ready", "photo-finish"):
        for _ in range(3):
            assert play(client, key).status_code == 302
        assert PlatoonGameActivity.query.filter_by(game_key=key).count() == 1
    freeze(monkeypatch, date(2026, 11, 17))
    assert play(client, "photo-finish").status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="photo-finish").count() == 1


def test_only_eligible_serving_members_during_live_round(client, db, monkeypatch):
    a, b, _ = camp(db)
    member = serving(db, "future@example.com", a)
    freeze(monkeypatch, date(2026, 11, 14))
    login(client, member.email)
    assert play(client, "goal-rush").status_code == 403
    assert PlatoonGameActivity.query.count() == 0
    freeze(monkeypatch, date(2026, 11, 16))
    member.profile.service_stage = "pcm"
    db.session.commit()
    assert play(client, "goal-rush").status_code == 403
    member.profile.service_stage = "serving"
    member.is_suspended = True
    db.session.commit()
    # Flask-Login may redirect a newly suspended session to sign-in.
    assert play(client, "goal-rush").status_code in (302, 403)
    assert PlatoonGameActivity.query.filter_by(game_key="goal-rush").count() == 0
    member.is_suspended = False
    member.profile.status = "rejected"
    db.session.commit()
    assert play(client, "goal-rush").status_code == 403
    member.profile.status = "approved"
    db.session.commit()
    assert play(client, "goal-rush").status_code == 302
    freeze(monkeypatch, date(2026, 12, 1))
    assert play(client, "goal-rush").status_code == 403
    assert PlatoonGameActivity.query.filter_by(game_key="goal-rush").count() == 1


def test_scoring_separates_cohorts_and_manual_placements(client, db, monkeypatch):
    first, second, other = camp(db)
    members = [
        serving(db, "score1@example.com", first),
        serving(db, "score2@example.com", first),
        serving(db, "score3@example.com", second),
        serving(db, "outsidegame@example.com", other),
    ]
    freeze(monkeypatch, date(2026, 11, 16))
    for member in members:
        login(client, member.email)
        play(client, "goal-rush")
        client.post("/auth/logout")
    board = micro.digital_standings(first, date(2026, 11, 15))
    assert len(board) == 2
    assert board[0]["platoon"].id == first.id
    assert board[0]["results"]["goal-rush"]["count"] == 2
    assert board[1]["results"]["goal-rush"]["count"] == 1
    assert board[0]["results"]["goal-rush"]["points"] == 10
    assert board[1]["results"]["goal-rush"]["points"] == 9
    assert sum(x["results"]["goal-rush"]["count"] for x in board) == 3


def test_reassignment_does_not_duplicate_credit(client, db, monkeypatch):
    first, second, _ = camp(db)
    person = serving(db, "reassign-game@example.com", first)
    freeze(monkeypatch, date(2026, 11, 16))
    login(client, person.email)
    play(client, "goal-rush")
    person.profile.platoon_id = second.id
    db.session.commit()
    play(client, "goal-rush")
    assert PlatoonGameActivity.query.filter_by(game_key="goal-rush").count() == 1
    rows = micro.digital_standings(first, date(2026, 11, 15))
    assert rows[0]["results"]["goal-rush"]["count"] == 1


def test_lesson_and_new_certificate_automatically_count_once(
    client, db, admin_user, monkeypatch,
):
    a, _, _ = camp(db)
    person = serving(db, "academy-game@example.com", a)
    freeze(monkeypatch, date(2026, 11, 16))
    course = LearningCourse(
        slug="platoon-academy", title="Academy for Teams",
        summary="Knowledge course", description="A short lesson.",
        level="Beginner", published=True, created_by_id=admin_user.id,
    )
    db.session.add(course)
    db.session.flush()
    lesson = LearningLesson(
        course_id=course.id, position=1, title="First lesson",
        description="Watch this", youtube_id="dQw4w9WgXcQ",
    )
    db.session.add(lesson)
    db.session.flush()
    db.session.add(LearningWatch(
        user_id=person.id, lesson_id=lesson.id,
        watched_seconds=90.0, session_id="test-session-123",
    ))
    db.session.commit()
    login(client, person.email)
    endpoint = f"/learn/courses/{course.slug}/lessons/{lesson.id}/complete"
    assert client.post(endpoint).status_code == 302
    assert LearningCertificate.query.filter_by(user_id=person.id).count() == 1
    assert PlatoonGameActivity.query.filter_by(game_key="lesson-sprint").count() == 1
    assert PlatoonGameActivity.query.filter_by(game_key="course-complete").count() == 1
    assert client.post(endpoint).status_code == 302
    assert PlatoonGameActivity.query.filter_by(game_key="lesson-sprint").count() == 1
    assert PlatoonGameActivity.query.filter_by(game_key="course-complete").count() == 1


def test_same_score_in_one_event_ties_and_zero_gets_zero(db, monkeypatch):
    a, b, _ = camp(db)
    freeze(monkeypatch, date(2026, 11, 16))
    for idx, platoon in enumerate((a, b)):
        user = serving(db, f"tie{idx}@example.com", platoon)
        assert micro.earned(user, "team-cheer") is True
    rows = micro.digital_standings(a, date(2026, 11, 15))
    assert len(rows) == 2
    assert all(x["results"]["team-cheer"]["points"] == 10 for x in rows)
    assert all(x["results"]["number-sprint"]["points"] == 0 for x in rows)


def test_unsupported_game_and_employer_cannot_submit(client, db, monkeypatch):
    a, _, _ = camp(db)
    freeze(monkeypatch, date(2026, 11, 16))
    employer = _create_user(db, "schoolnotplayer@example.com", role="employer")
    login(client, employer.email)
    assert play(client, "goal-rush").status_code == 403
    assert play(client, "fake-game").status_code == 404
    assert play(client, "course-complete").status_code == 403
    assert PlatoonGameActivity.query.count() == 0
