"""Dating persona matching: compatibility scoring + ranked match generation.

Matching is fully automatic -- no manual swiping. Whenever a persona is
created/edited (or a member taps "Refresh My Matches"), we recompute its
ranked candidate list against every eligible, gender-compatible active
persona. A DatingMatch row is upserted per unique pair with a symmetric
score, and each side's rank of the other. The celebratory notification
only fires the first time a pair becomes MUTUAL (each ranks the other in
their own top N) -- see app/models/dating.py for why.
"""
from datetime import datetime
from sqlalchemy import or_, and_

from app.extensions import db
from app.models import DatingPersona, DatingMatch, DatingBlock, Profile, User
from app.services.notification_service import notify

TOP_N = 10


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def compute_compatibility(persona_a: DatingPersona, persona_b: DatingPersona) -> float:
    """Transparent shared-interest similarity, not a predictive love score.

    No random offsets, state of origin or demographic inferences.
    The value is a discovery ranking only, not a measure of consent,
    attraction, personal suitability or relationship success.
    """
    profile_a, profile_b = persona_a.profile, persona_b.profile

    interests_a = {i.casefold() for i in persona_a.interest_list()}
    interests_b = {i.casefold() for i in persona_b.interest_list()}
    skills_a = {s.name.casefold() for s in profile_a.skills}
    skills_b = {s.name.casefold() for s in profile_b.skills}

    interests_score = 80 * _jaccard(interests_a, interests_b)
    skills_score = 20 * _jaccard(skills_a, skills_b)

    return round(min(100.0, max(0.0, interests_score + skills_score)), 1)


def _blocked_ids(persona_id):
    """Include blocks initiated by either party."""
    rows = DatingBlock.query.filter(or_(
        DatingBlock.blocker_id == persona_id,
        DatingBlock.blocked_id == persona_id,
    )).all()
    return {
        row.blocked_id if row.blocker_id == persona_id else row.blocker_id
        for row in rows
    }


def is_blocked(persona_a_id, persona_b_id):
    return DatingBlock.query.filter(or_(
        and_(DatingBlock.blocker_id == persona_a_id,
             DatingBlock.blocked_id == persona_b_id),
        and_(DatingBlock.blocker_id == persona_b_id,
             DatingBlock.blocked_id == persona_a_id),
    )).first() is not None


def _eligible_candidates(persona: DatingPersona):
    blocked = _blocked_ids(persona.id)
    query = (DatingPersona.query
             .filter(DatingPersona.id != persona.id)
             .filter(DatingPersona.status == "active")
             .filter(DatingPersona.is_reported.is_(False))
             .filter(DatingPersona.age_confirmed_at.isnot(None))
             .filter(DatingPersona.gender == persona.interested_in)
             .filter(DatingPersona.interested_in == persona.gender)
             .join(Profile, DatingPersona.profile_id == Profile.id)
             .join(User, Profile.user_id == User.id)
             .filter(Profile.status == "approved", User.is_active_account.is_(True),
                     User.is_suspended.is_(False)))
    if blocked:
        query = query.filter(~DatingPersona.id.in_(blocked))
    return query.all()


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
    if not persona.is_active_and_visible():
        return []
    # Clear stale candidate ranks: a previous match should not remain a
    # "top pick" after preferences change or a new candidate outranks it.
    ranked_pairs = DatingMatch.query.filter(or_(
        DatingMatch.persona_low_id == persona.id,
        DatingMatch.persona_high_id == persona.id,
    )).all()
    for pair in ranked_pairs:
        if pair.persona_low_id == persona.id:
            pair.low_ranks_high = None
        else:
            pair.high_ranks_low = None

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

    notify(low_user, f"You have a new mutual match suggestion with {high_name}. Explore it at your own pace.",
           category="success")
    notify(high_user, f"You have a new mutual match suggestion with {low_name}. Explore it at your own pace.",
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
    if not persona.is_active_and_visible():
        return []
    blocked = _blocked_ids(persona.id)
    return [
        (m, other) for m, other in pairs
        if other and other.id not in blocked
        and other.is_active_and_visible()
        and persona.is_compatible_with(other)
    ]


def mutual_matches_for_persona(persona: DatingPersona):
    rows = (DatingMatch.query
            .filter(db.or_(DatingMatch.persona_low_id == persona.id,
                           DatingMatch.persona_high_id == persona.id))
            .filter(DatingMatch.status == "matched")
            .order_by(DatingMatch.matched_at.desc())
            .all())
    pairs = [(m, m.other_persona(persona.id)) for m in rows]
    if not persona.is_active_and_visible():
        return []
    blocked = _blocked_ids(persona.id)
    return [
        (m, other) for m, other in pairs
        if other and other.id not in blocked
        and other.is_active_and_visible()
        and persona.is_compatible_with(other)
    ]


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



def block_persona(blocker: DatingPersona, target: DatingPersona):
    """Hide both ways without affecting others; the blocked user is not notified."""
    if blocker.id == target.id:
        raise ValueError("A dating persona cannot block itself.")
    existing = DatingBlock.query.filter_by(
        blocker_id=blocker.id, blocked_id=target.id).first()
    if existing:
        return existing
    row = DatingBlock(blocker_id=blocker.id, blocked_id=target.id)
    db.session.add(row)
    db.session.commit()
    return row


def delete_dating_persona(persona: DatingPersona):
    """Delete this persona and any match/block rows, without deleting the member."""
    DatingMatch.query.filter(or_(
        DatingMatch.persona_low_id == persona.id,
        DatingMatch.persona_high_id == persona.id,
    )).delete(synchronize_session=False)
    DatingBlock.query.filter(or_(
        DatingBlock.blocker_id == persona.id,
        DatingBlock.blocked_id == persona.id,
    )).delete(synchronize_session=False)
    db.session.delete(persona)
    db.session.commit()
