"""Automatic scoring for lightweight, on-platform interplatoon challenges.

A contribution is accepted only during a live quarterly competition,
from an eligible serving member, and once per user/game/calendar day
(or once per round for lifetime-style tasks).
"""
from collections import defaultdict
from datetime import date, timedelta
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.platoon_microgames import PlatoonGameActivity
from app.services.platoon_games import (
    local_today, period_is_live, upcoming_period, cohort_platoons,
    member_is_eligible,
)

MICRO_GAMES = (
    ("daily-login", "Daily Roll Call", "Sign in each day to count once for your platoon.", "automatic", "daily"),
    ("goal-rush", "GOAL Rush", "Tap GOAL while the competition is live — one cheer per day.", "tap", "daily"),
    ("course-complete", "Academy Graduate", "Earn a new Silabs Academy course certificate.", "automatic", "daily"),
    ("lesson-sprint", "Lesson Sprint", "Finish a video lesson after the required 90 seconds.", "automatic", "daily"),
    ("profile-ready", "Profile Ready", "Complete at least 50% of your MyPlatoon profile.", "verify", "round"),
    ("photo-finish", "Photo Finish", "Upload a profile photograph to complete this task.", "verify", "round"),
    ("camp-quiz", "NYSC Camp Quiz", "Answer today's NYSC knowledge question correctly.", "quiz", "daily"),
    ("tech-quiz", "Tech Trivia", "Answer today's technology question correctly.", "quiz", "daily"),
    ("number-sprint", "Number Sprint", "Solve today's short arithmetic challenge.", "quiz", "daily"),
    ("team-cheer", "Team Cheer", "Send one positive cheer to your platoon each day.", "tap", "daily"),
)
MICRO_GAME_MAP = {game[0]: game for game in MICRO_GAMES}

# Simple rotating daily questions. Answers are checked only on the server.
QUESTIONS = {
    "camp-quiz": (
        ("What does NYSC stand for?", ("National Youth Service Corps", "National Young Students Council", "Nigerian Youth Sports Club"), "A"),
        ("Which document identifies a corps member?", ("Driver permit", "NYSC ID card", "School admission slip"), "B"),
        ("What is the name of the NYSC camp morning physical routine?", ("Carnival", "Matriculation", "Morning drills"), "C"),
        ("What is a platoon?", ("An orientation-camp grouping", "A bank account", "A classroom subject"), "A"),
    ),
    "tech-quiz": (
        ("What does HTTPS help protect?", ("Screen brightness", "Information in transit", "Phone storage"), "B"),
        ("Which is a stronger password?", ("12345678", "password", "A long unique passphrase"), "C"),
        ("What should you do before sharing a suspicious link?", ("Check its destination", "Forward it immediately", "Disable security"), "A"),
        ("Which is a common way to protect an account?", ("Reuse passwords", "Enable two-factor authentication", "Share login codes"), "B"),
    ),
    "number-sprint": (),
}


def active_round(on=None):
    today = on or local_today()
    start = upcoming_period(today)
    return start if period_is_live(start, today) else None


def challenge_question(game_key, on=None):
    day = on or local_today()
    if game_key == "number-sprint":
        a = 8 + ((day.toordinal() * 3) % 24)
        b = 3 + ((day.toordinal() * 7) % 17)
        result = a + b
        # Rotate the correct position to avoid a fixed answer choice.
        slot = day.toordinal() % 3
        choices = [result - 2, result + 3, result + 5]
        choices[slot] = result
        return (f"What is {a} + {b}?", tuple(str(x) for x in choices), "ABC"[slot])
    bank = QUESTIONS.get(game_key)
    if not bank:
        return None
    return bank[day.toordinal() % len(bank)]


def earned(user, game_key, on=None):
    """Record one eligible contribution, using a DB uniqueness guarantee."""
    today = on or local_today()
    period = active_round(today)
    game = MICRO_GAME_MAP.get(game_key)
    if not period or not game or not getattr(user, "is_authenticated", False):
        return False
    profile = user.profile
    if not profile or not profile.platoon_id or not member_is_eligible(user, profile.platoon_id):
        return False
    scored_day = today if game[4] == "daily" else period
    if PlatoonGameActivity.query.filter_by(
        period_start=period, game_key=game_key, user_id=user.id,
        score_day=scored_day,
    ).first():
        return False
    db.session.add(PlatoonGameActivity(
        period_start=period, game_key=game_key, user_id=user.id,
        platoon_id=profile.platoon_id, score_day=scored_day,
    ))
    try:
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        return False


def has_earned(user_id, game_key, period, on=None):
    day = on or local_today()
    game = MICRO_GAME_MAP.get(game_key)
    if not game:
        return False
    return PlatoonGameActivity.query.filter_by(
        period_start=period, game_key=game_key, user_id=user_id,
        score_day=day if game[4] == "daily" else period,
    ).first() is not None


def automatic_activity(user, game_key):
    """Hook from successful login, lesson completion, or course issuance."""
    return earned(user, game_key)


def digital_standings(platoon, period):
    """Per-event participant counts, with 10..1 points by event ranking.

    Zero activity earns zero. Equal positive totals share a rank and
    corresponding points; historic manual placements do not affect scoring.
    """
    peers = cohort_platoons(platoon)
    ids = {p.id for p in peers}
    totals = {p.id: defaultdict(int) for p in peers}
    if ids:
        rows = PlatoonGameActivity.query.filter_by(
            period_start=period,
        ).filter(PlatoonGameActivity.platoon_id.in_(ids)).all()
        for activity in rows:
            if activity.game_key in MICRO_GAME_MAP:
                totals[activity.platoon_id][activity.game_key] += 1
    scores = {p.id: {"platoon": p, "points": 0, "actions": 0,
                     "results": {}} for p in peers}
    for key, *_ in MICRO_GAMES:
        positive = sorted({totals[pid][key] for pid in ids if totals[pid][key] > 0},
                          reverse=True)
        for pid in ids:
            count = totals[pid][key]
            # "Dense ranking": tied participation counts earn same points.
            rank = positive.index(count) + 1 if count else 0
            pts = max(0, 11 - rank) if rank else 0
            scores[pid]["results"][key] = {"count": count, "points": pts}
            scores[pid]["points"] += pts
            scores[pid]["actions"] += count
    return sorted(scores.values(), key=lambda x: (
        -x["points"], -x["actions"], x["platoon"].number,
    ))
