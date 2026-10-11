"""Dating persona matching: compatibility scoring + ranked match generation.

Matching is fully automatic -- no manual swiping. Whenever a persona is
created/edited (or a member taps "Refresh My Matches"), we recompute its
ranked candidate list against every eligible, gender-compatible active
persona. A DatingMatch row is upserted per unique pair with a symmetric
score, and each side's rank of the other. The celebratory notification
only fires the first time a pair becomes MUTUAL (each ranks the other in
their own top N) -- see app/models/dating.py for why.
"""
import hashlib
from datetime import datetime

from app.extensions import db
from app.models import DatingPersona, DatingMatch, Profile
from app.services.notification_service import notify

TOP_N = 10


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _spark(persona_a_id: int, persona_b_id: int) -> float:
    """A small, stable (not truly random) +/- offset per pair, so the score
    isn't purely mechanical without flickering between recomputations."""
    key = f"{min(persona_a_id, persona_b_id)}:{max(persona_a_id, persona_b_id)}"
    digest = hashlib.sha256(key.encode()).hexdigest()
    # Map the first 4 hex chars to a stable value in [-10, 10]
    value = int(digest[:4], 16) / 0xFFFF  # 0..1
    return (value - 0.5) * 20


def compute_compatibility(persona_a: DatingPersona, persona_b: DatingPersona) -> float:
    """Symmetric 0-100 compatibility score between two personas."""
    profile_a, profile_b = persona_a.profile, persona_b.profile

    skills_a = {s.name.lower() for s in profile_a.skills}
    skills_b = {s.name.lower() for s in profile_b.skills}
    skills_score = _jaccard(skills_a, skills_b) * 40

    interests_a = {i.lower() for i in persona_a.interest_list()}
    interests_b = {i.lower() for i in persona_b.interest_list()}
    interests_score = _jaccard(interests_a, interests_b) * 30

    state_bonus = 0.0
    if profile_a.state_of_origin and profile_b.state_of_origin:
        if profile_a.state_of_origin.strip().lower() == profile_b.state_of_origin.strip().lower():
            state_bonus = 15.0

    profession_bonus = 0.0
    if profile_a.profession and profile_b.profession:
        if profile_a.profession.strip().lower() == profile_b.profession.strip().lower():
            profession_bonus = 5.0

    spark = _spark(persona_a.id, persona_b.id)

    raw = skills_score + interests_score + state_bonus + profession_bonus + spark
    return round(max(20.0, min(100.0, raw)), 1)


def _eligible_candidates(persona: DatingPersona):
    return (DatingPersona.query
            .filter(DatingPersona.id != persona.id)
            .filter(DatingPersona.status == "active")
            .filter(DatingPersona.is_reported.is_(False))
            .filter(DatingPersona.gender == persona.interested_in)
            .filter(DatingPersona.interested_in == persona.gender)
            .join(Profile, DatingPersona.profile_id == Profile.id)
            .filter(Profile.status == "approved")
            .all())


def _get_or_create_match(persona_a: DatingPersona, persona_b: DatingPersona) -> DatingMatch:
    low_id, high_id = sorted([persona_a.id, persona_b.id])
    match = DatingMatch.query.filter_by(persona_low_id=low_id, persona_high_id=high_id).first()
    if match is None:
        match = DatingMatch(persona_low_id=low_id, persona_high_id=high_id, score=0.0)
        db.session.add(match)
    return match


def generate_matches_for_persona(persona: DatingPersona, top_n: int = TOP_N, _cascade: bool = True):
    """Recompute `persona`'s ranked candidate list and upsert DatingMatch rows.

    `_cascade=True` (the default, used whenever this is called after someone
    creates/edits their persona) also refreshes each of this persona's top-N
    candidates' own ranking of *this* persona, one level deep. Without this,
    a mutual match could only ever be detected when the SECOND of a pair
    happened to (re)save their persona -- the first person's ranking would
    already be stale/absent for a candidate who didn't exist yet when they
    last computed matches. The reciprocal calls pass `_cascade=False` so
    this never recurses beyond one level.

    Returns the list of (DatingMatch, other_persona, score) for this
    persona's new top N, best first.
    """
    candidates = _eligible_candidates(persona)
    scored = [(c, compute_compatibility(persona, c)) for c in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    top = scored[:top_n]

    newly_matched = []
    results = []

    for rank, (other, score) in enumerate(top, start=1):
        match = _get_or_create_match(persona, other)
        match.score = score
        match.updated_at = datetime.utcnow()

        if persona.id == match.persona_low_id:
            match.low_ranks_high = rank
        else:
            match.high_ranks_low = rank

        if match.is_mutual_top and match.status == "candidate" and not match.matched_notified:
            match.status = "matched"
            match.matched_at = datetime.utcnow()
            match.matched_notified = True
            newly_matched.append(match)

        results.append((match, other, score))

    db.session.commit()

    for match in newly_matched:
        _notify_mutual_match(match)

    if _cascade:
        for other, _score in top:
            generate_matches_for_persona(other, top_n=top_n, _cascade=False)

    # Known simplification: a candidate that falls out of this persona's
    # top-N on a later recompute (e.g. after editing interests) keeps its
    # stale rank on the DatingMatch row until that row is next touched, so
    # it may briefly still appear in browse_matches_for_persona. Matched
    # (mutual) pairs are unaffected -- they're sticky by design (see
    # module docstring) and never pruned here.

    return results


def _notify_mutual_match(match: DatingMatch):
    low_user = match.persona_low.profile.user
    high_user = match.persona_high.profile.user
    low_name = match.persona_low.display_name or low_user.full_name.split(" ")[0]
    high_name = match.persona_high.display_name or high_user.full_name.split(" ")[0]
    pct = int(round(match.score))

    notify(low_user, f"\U0001F389 It's a match! You and {high_name} are {pct}% compatible. Say hello!",
           category="success")
    notify(high_user, f"\U0001F389 It's a match! You and {low_name} are {pct}% compatible. Say hello!",
           category="success")


def browse_matches_for_persona(persona: DatingPersona):
    """This persona's own ranked candidate list (mutual or not) for the
    'Your Top Matches' browsing view, best first."""
    rows = (DatingMatch.query
            .filter(db.or_(
                db.and_(DatingMatch.persona_low_id == persona.id, DatingMatch.low_ranks_high.isnot(None)),
                db.and_(DatingMatch.persona_high_id == persona.id, DatingMatch.high_ranks_low.isnot(None)),
            ))
            .all())

    def rank_of(m):
        return m.low_ranks_high if persona.id == m.persona_low_id else m.high_ranks_low

    rows.sort(key=rank_of)
    pairs = [(m, m.other_persona(persona.id)) for m in rows]
    # A candidate may have paused or been reported since this row was last
    # touched -- don't surface them even though the stale rank row remains.
    return [(m, other) for m, other in pairs if other.is_active_and_visible()]


def mutual_matches_for_persona(persona: DatingPersona):
    rows = (DatingMatch.query
            .filter(db.or_(DatingMatch.persona_low_id == persona.id,
                           DatingMatch.persona_high_id == persona.id))
            .filter(DatingMatch.status == "matched")
            .order_by(DatingMatch.matched_at.desc())
            .all())
    pairs = [(m, m.other_persona(persona.id)) for m in rows]
    return [(m, other) for m, other in pairs if other.is_active_and_visible()]


def report_persona(persona: DatingPersona, reason: str):
    """Flag a persona for admin review. It stops appearing as a candidate
    to anyone immediately (see _eligible_candidates / the visibility
    filters in browse_matches_for_persona and mutual_matches_for_persona),
    but existing DatingMatch rows are left alone -- an admin decides
    whether to act further from the moderation queue.
    """
    persona.is_reported = True
    persona.report_reason = (reason or "").strip()[:500] or "No reason given."
    db.session.commit()
