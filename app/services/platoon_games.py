"""NYSC-style inter-platoon events and two-week elected leadership.

These are community competitions inspired by orientation camp, not official
NYSC results. All results need admin review before they affect standings.
"""
from collections import Counter
from datetime import date, datetime, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo

from sqlalchemy import and_
from app.extensions import db
from app.models import Platoon, Profile, User
from app.models.platoon_games import (
    PlatoonLeaderCandidate, PlatoonLeaderVote, PlatoonGameResult,
)

NIGERIA_TZ = ZoneInfo("Africa/Lagos")
# From the requested Nov 15 inaugural round: every three months thereafter.
GAME_MONTHS = (2, 5, 8, 11)
GAMES = (
    ("football", "Football", "Inter-platoon football match / tournament"),
    ("volleyball", "Volleyball", "Team volleyball tournament"),
    ("table-tennis", "Table Tennis", "Inter-platoon singles/doubles"),
    ("cooking", "Cooking", "Camp kitchen and recipe challenge"),
    ("sanitation", "Sanitation", "Cleanest platoon / sanitation challenge"),
    ("drill", "Parade & Drill", "March-past, precision and camp drill"),
    ("tug-of-war", "Tug of War", "Team strength and coordination"),
    ("drama", "Drama", "Short camp theatre challenge"),
    ("cultural-dance", "Cultural Dance", "Traditional dance and culture"),
    ("athletics", "Athletics / Relay", "Track, field and relay challenge"),
)
GAME_MAP = {game[0]: game for game in GAMES}
TERM_ANCHOR = date(2026, 1, 1)
TERM_DAYS = 14
BALLOT_DAYS = 7


def local_today():
    return datetime.now(NIGERIA_TZ).date()


def leadership_term(on=None):
    day = on or local_today()
    start = TERM_ANCHOR + timedelta(
        days=((day - TERM_ANCHOR).days // TERM_DAYS) * TERM_DAYS
    )
    return start, start + timedelta(days=TERM_DAYS - 1)


def next_election(on=None):
    """Ballot for the next 14-day term, only during its preceding 7 days."""
    day = on or local_today()
    start, end = leadership_term(day)
    target = end + timedelta(days=1)
    ballot_start = target - timedelta(days=BALLOT_DAYS)
    return target, ballot_start, target - timedelta(days=1), ballot_start <= day < target


def quarter_start(value):
    """Accept only quarterly season dates and never unconstrained form dates."""
    if isinstance(value, date) and not isinstance(value, datetime):
        day = value
    else:
        try:
            day = date.fromisoformat(value)
        except (TypeError, ValueError):
            return None
    return day if day.year >= 2026 and day.month in GAME_MONTHS and day.day == 15 else None


def quarter_end(start):
    return date(start.year, start.month, min(30, monthrange(start.year, start.month)[1]))


def upcoming_period(on=None):
    day = on or local_today()
    options = [date(y, m, 15) for y in (day.year, day.year + 1)
               for m in GAME_MONTHS]
    for start in options:
        if day <= quarter_end(start):
            return start
    return date(day.year + 1, 2, 15)


def period_is_live(start, on=None):
    day = on or local_today()
    return start <= day <= quarter_end(start)


def cohort_match(left, right):
    return (left.state, left.service_year, left.batch, left.stream) == (
        right.state, right.service_year, right.batch, right.stream
    )


def member_is_eligible(user, platoon_id):
    return bool(
        user and user.is_authenticated and user.role == "member" and user.is_active
        and user.profile and user.profile.status == "approved"
        and user.profile.service_stage == "serving"
        and user.profile.platoon_id == platoon_id
    )


def cohort_members(platoon_id):
    return (User.query.join(Profile, Profile.user_id == User.id)
            .filter(Profile.platoon_id == platoon_id,
                    Profile.status == "approved",
                    Profile.service_stage == "serving",
                    User.role == "member",
                    User.is_active_account.is_(True),
                    User.is_suspended.is_(False)).all())


def election_candidates(platoon_id, target):
    """Show only candidates who are still members of the right platoon."""
    eligible = {user.id for user in cohort_members(platoon_id)}
    return [
        candidate for candidate in PlatoonLeaderCandidate.query.filter_by(
            platoon_id=platoon_id, term_start=target,
        ).order_by(PlatoonLeaderCandidate.nominated_at,
                   PlatoonLeaderCandidate.id).all()
        if candidate.user_id in eligible
    ]


def election_standings(platoon_id, target):
    candidates = election_candidates(platoon_id, target)
    voters = {user.id for user in cohort_members(platoon_id)}
    candidate_ids = {candidate.id for candidate in candidates}
    votes = PlatoonLeaderVote.query.filter_by(
        platoon_id=platoon_id, term_start=target,
    ).all()
    counts = Counter(
        vote.candidate_id for vote in votes
        if vote.voter_id in voters and vote.candidate_id in candidate_ids
    )
    return [(candidate, counts[candidate.id]) for candidate in candidates]


def elected_leader(platoon_id, on=None):
    """Find a winner only once the ballot has closed; badge expires in 14 days.

    Ties resolve by earliest candidate registration (then candidate ID).
    Candidate and voter eligibility are rechecked against their CURRENT
    platoon, so transfers and moderation do not count former members.
    """
    start, end = leadership_term(on)
    rows = election_standings(platoon_id, start)
    if not rows:
        return None
    winner, votes = sorted(
        rows, key=lambda item: (
            -item[1], item[0].nominated_at, item[0].id
        )
    )[0]
    return (winner, votes, start, end) if votes else None


def cohort_platoons(platoon):
    return Platoon.query.filter_by(
        state=platoon.state, service_year=platoon.service_year,
        batch=platoon.batch, stream=platoon.stream,
    ).order_by(Platoon.number).all()


def verified_scoreboard(platoon, period):
    """Only administrator-verified placement results contribute points."""
    cohorts = cohort_platoons(platoon)
    ids = {p.id for p in cohorts}
    entries = PlatoonGameResult.query.filter_by(
        period_start=period, status="verified",
    ).filter(PlatoonGameResult.platoon_id.in_(ids)).all() if ids else []
    rows = {p.id: {"platoon": p, "points": 0, "events": 0,
                   "results": {}} for p in cohorts}
    for entry in entries:
        row = rows[entry.platoon_id]
        row["points"] += 11 - entry.placement
        row["events"] += 1
        row["results"][entry.game_key] = entry
    return sorted(rows.values(), key=lambda row: (
        -row["points"], -row["events"], row["platoon"].number
    ))


def placement_taken(entry):
    """Reject conflicting verified positions in the same cohort and event."""
    other = PlatoonGameResult.query.filter_by(
        period_start=entry.period_start, game_key=entry.game_key,
        placement=entry.placement, status="verified",
    ).filter(PlatoonGameResult.id != entry.id).all()
    return any(cohort_match(x.platoon, entry.platoon) for x in other)
