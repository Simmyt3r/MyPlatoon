"""Quarterly interplatoon events and election eligibility regression tests."""
from datetime import date, timedelta
from html import escape

from app.extensions import db
from app.models import Platoon
from app.models.platoon_games import (
    PlatoonLeaderCandidate, PlatoonLeaderVote, PlatoonGameResult,
)
from app.services import platoon_games as svc
from tests.conftest import _create_user, login


def member(db, email, platoon, stage="serving", status="approved"):
    user = _create_user(db, email)
    user.profile.platoon_id = platoon.id
    user.profile.service_stage = stage
    user.profile.status = status
    db.session.commit()
    return user


def fake_date(monkeypatch, day):
    monkeypatch.setattr("app.services.platoon_games.local_today", lambda: day)
    monkeypatch.setattr("app.blueprints.platoons.games.local_today", lambda: day)


def camp(db):
    own = Platoon.find_or_create("Benue", 2026, "B", "II", 1)
    other = Platoon.find_or_create("Benue", 2026, "B", "II", 2)
    outsider = Platoon.find_or_create("Lagos", 2026, "B", "II", 1)
    db.session.commit()
    return own, other, outsider


def test_quarterly_calendar_november_to_february_leap_year():
    assert len(svc.GAMES) == 10
    assert len(svc.GAME_MAP) == 10
    assert svc.upcoming_period(date(2026, 11, 2)) == date(2026, 11, 15)
    assert svc.quarter_end(date(2026, 11, 15)) == date(2026, 11, 30)
    assert svc.upcoming_period(date(2026, 11, 30)) == date(2026, 11, 15)
    assert svc.upcoming_period(date(2026, 12, 1)) == date(2027, 2, 15)
    assert svc.quarter_end(date(2027, 2, 15)) == date(2027, 2, 28)
    assert svc.quarter_end(date(2028, 2, 15)) == date(2028, 2, 29)
    assert svc.period_is_live(date(2026, 11, 15), date(2026, 11, 14)) is False
    assert svc.period_is_live(date(2026, 11, 15), date(2026, 11, 15)) is True
    assert svc.period_is_live(date(2026, 11, 15), date(2026, 11, 30)) is True
    assert svc.period_is_live(date(2026, 11, 15), date(2026, 12, 1)) is False
    assert svc.quarter_start("2026-11-15") == date(2026, 11, 15)
    assert svc.quarter_start("2026-11-14") is None
    assert svc.quarter_start("2026-12-15") is None


def test_leadership_election_is_14_days_and_preceded_by_week_of_voting():
    start, end = svc.leadership_term(date(2026, 11, 2))
    target, opens, closes, permitted = svc.next_election(date(2026, 11, 2))
    assert (end - start).days == 13
    assert (target - opens).days == 7
    assert (closes - opens).days == 6
    assert permitted is True
    assert svc.leadership_term(target)[0] == target
    assert svc.leadership_term(target + timedelta(days=14))[0] == target + timedelta(days=14)


def test_election_one_vote_only_own_platoon_and_badge_expires(
    client, db, monkeypatch,
):
    own, other, _ = camp(db)
    candidate = member(db, "leader@example.com", own)
    voter = member(db, "voter@example.com", own)
    outside = member(db, "outside@example.com", other)
    fake_date(monkeypatch, date(2026, 11, 2))

    public = client.get(f"/platoons/{own.id}/leaders")
    assert public.status_code == 200
    assert b"Next term election" in public.data
    login(client, candidate.email)
    assert client.post(f"/platoons/{own.id}/leaders/nominate").status_code == 302
    assert PlatoonLeaderCandidate.query.count() == 1
    assert client.post(f"/platoons/{own.id}/leaders/nominate").status_code == 302
    assert PlatoonLeaderCandidate.query.count() == 1
    nominated = PlatoonLeaderCandidate.query.one()
    client.post("/auth/logout")

    login(client, outside.email)
    assert client.post(f"/platoons/{own.id}/leaders/vote",
                       data={"candidate_id": nominated.id}).status_code == 403
    client.post("/auth/logout")

    login(client, voter.email)
    vote_route = f"/platoons/{own.id}/leaders/vote"
    assert client.post(vote_route, data={"candidate_id": nominated.id}).status_code == 302
    assert client.post(vote_route, data={"candidate_id": nominated.id}).status_code == 302
    assert PlatoonLeaderVote.query.count() == 1
    client.post("/auth/logout")

    fake_date(monkeypatch, date(2026, 11, 5))
    winner = svc.elected_leader(own.id)
    assert winner is not None and winner[0].user_id == candidate.id
    assert (winner[3] - winner[2]).days == 13
    assert b"Platoon Leader" in client.get(f"/platoons/{own.id}/leaders").data
    assert client.post(vote_route, data={"candidate_id": nominated.id}).status_code in (302, 401)

    login(client, candidate.email)
    assert b"Platoon Leader" in client.get("/profile/dashboard").data
    assert b"Platoon Leader" in client.get(
        f"/directory/member/{candidate.profile.slug}").data
    client.post("/auth/logout")
    fake_date(monkeypatch, date(2026, 11, 19))
    assert svc.elected_leader(own.id) is None
    login(client, candidate.email)
    assert b"Platoon Leader</span>" not in client.get("/profile/dashboard").data


def test_rejected_pcm_suspended_and_reassigned_members_cannot_win_or_vote(
    client, db, monkeypatch,
):
    own, other, _ = camp(db)
    candidate = member(db, "candidate@example.com", own)
    pcmer = member(db, "pcm@example.com", own, stage="pcm")
    rejected = member(db, "rejected@example.com", own, status="rejected")
    fake_date(monkeypatch, date(2026, 11, 2))
    for person in (pcmer, rejected):
        login(client, person.email)
        assert client.post(f"/platoons/{own.id}/leaders/nominate").status_code == 403
        client.post("/auth/logout")
    login(client, candidate.email)
    client.post(f"/platoons/{own.id}/leaders/nominate")
    n = PlatoonLeaderCandidate.query.one()
    client.post(f"/platoons/{own.id}/leaders/vote",
                data={"candidate_id": n.id})
    client.post("/auth/logout")
    fake_date(monkeypatch, date(2026, 11, 5))
    assert svc.elected_leader(own.id) is not None
    candidate.is_suspended = True
    db.session.commit()
    assert svc.elected_leader(own.id) is None
    candidate.is_suspended = False
    candidate.profile.platoon_id = other.id
    db.session.commit()
    assert svc.elected_leader(own.id) is None


def test_games_have_ten_cards_and_cohort_scoped_verified_scores(
    client, db, admin_user, monkeypatch,
):
    own, rival, outsider = camp(db)
    leader = member(db, "event-leader@example.com", own)
    voter = member(db, "event-voter@example.com", own)
    fake_date(monkeypatch, date(2026, 11, 2))
    login(client, leader.email)
    client.post(f"/platoons/{own.id}/leaders/nominate")
    nomination = PlatoonLeaderCandidate.query.one()
    client.post("/auth/logout")
    login(client, voter.email)
    client.post(f"/platoons/{own.id}/leaders/vote",
                data={"candidate_id": nomination.id})
    client.post("/auth/logout")

    fake_date(monkeypatch, date(2026, 11, 16))
    login(client, leader.email)
    page = client.get(f"/platoons/games?platoon_id={own.id}")
    assert page.status_code == 200
    for _, title, _ in svc.GAMES:
        assert escape(title).encode() in page.data
    assert b"Submit for review" in page.data
    route = f"/platoons/games/{own.id}/submit"
    result = client.post(route, data={
        "period": "2026-11-15", "game": "football",
        "placement": "1", "details": "Won the final.",
    })
    assert result.status_code == 302
    entry = PlatoonGameResult.query.one()
    assert entry.status == "pending"
    assert svc.verified_scoreboard(own, date(2026, 11, 15))[0]["points"] == 0
    client.post("/auth/logout")

    login(client, admin_user.email)
    assert client.post(f"/platoons/games/results/{entry.id}/review",
                       data={"decision": "verified"}).status_code == 302
    assert entry.status == "verified"
    assert svc.verified_scoreboard(own, date(2026, 11, 15))[0]["points"] == 10
    # An unrelated state and cohort cannot be mixed into this scoreboard.
    db.session.add(PlatoonGameResult(
        period_start=date(2026, 11, 15), platoon_id=outsider.id,
        game_key="football", placement=1, details="Other state",
        status="verified", submitted_by_id=admin_user.id,
    ))
    db.session.commit()
    assert sum(row["points"] for row in
               svc.verified_scoreboard(own, date(2026, 11, 15))) == 10
    assert client.get(f"/platoons/games?platoon_id={own.id}").status_code == 200


def test_cannot_forge_game_placements_or_approve_duplicate_ranks(
    client, db, admin_user, monkeypatch,
):
    first, second, _ = camp(db)
    regular = member(db, "regular@example.com", first)
    fake_date(monkeypatch, date(2026, 11, 16))
    login(client, regular.email)
    assert client.post(f"/platoons/games/{first.id}/submit", data={
        "period": "2026-11-15", "game": "football", "placement": "1",
    }).status_code == 403
    client.post("/auth/logout")
    login(client, admin_user.email)
    for platoon in (first, second):
        assert client.post(f"/platoons/games/{platoon.id}/submit", data={
            "period": "2026-11-15", "game": "football", "placement": "1",
        }).status_code == 302
    entries = PlatoonGameResult.query.order_by(PlatoonGameResult.id).all()
    client.post(f"/platoons/games/results/{entries[0].id}/review",
                data={"decision": "verified"})
    rejected = client.post(
        f"/platoons/games/results/{entries[1].id}/review",
        data={"decision": "verified"}, follow_redirects=True,
    )
    assert rejected.status_code == 200
    assert b"already holds that verified placement" in rejected.data
    assert entries[1].status == "pending"
    client.post("/auth/logout")
    login(client, regular.email)
    assert client.post(
        f"/platoons/games/results/{entries[1].id}/review",
        data={"decision": "verified"},
    ).status_code == 403


def test_results_window_and_elections_closed_outside_appointed_dates(
    client, db, admin_user, monkeypatch,
):
    first, _, _ = camp(db)
    fake_date(monkeypatch, date(2026, 11, 2))
    login(client, admin_user.email)
    assert client.post(f"/platoons/games/{first.id}/submit", data={
        "period": "2026-11-15", "game": "football", "placement": "1",
    }).status_code == 403
    assert client.post(f"/platoons/games/{first.id}/submit", data={
        "period": "2026-11-15", "game": "unknown", "placement": "1",
    }).status_code == 400
    fake_date(monkeypatch, date(2026, 11, 30))
    assert client.post(f"/platoons/games/{first.id}/submit", data={
        "period": "2026-11-15", "game": "football", "placement": "1",
    }).status_code == 302
    fake_date(monkeypatch, date(2026, 12, 1))
    assert client.post(f"/platoons/games/{first.id}/submit", data={
        "period": "2026-11-15", "game": "volleyball", "placement": "1",
    }).status_code == 403
