"""Dating persona matching: compatibility scoring + ranked match generation.

Candidate discovery is automatically ranked by shared interests and skills.
A DatingMatch row stores suggestion ranks, but *rankings are not consent*.
Only explicit, reciprocated DatingInterest actions notify the participants
and create a mutual connection. Gender preferences must be mutually compatible.
"""
from datetime import datetime
from sqlalchemy import or_, and_

from app.extensions import db
from app.models import DatingPersona, DatingMatch, DatingBlock, DatingInterest, Profile, User
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
    gender_filter = (DatingPersona.gender.in_(("male", "female", "nonbinary"))
                     if persona.interested_in == "any" else
                     DatingPersona.gender == persona.interested_in)
    query = (DatingPersona.query
             .filter(DatingPersona.id != persona.id)
             .filter(DatingPersona.status == "active")
             .filter(DatingPersona.is_reported.is_(False))
             .filter(DatingPersona.age_confirmed_at.isnot(None))
             .filter(gender_filter)
             .filter(or_(DatingPersona.interested_in == persona.gender,
                         DatingPersona.interested_in == "any"))
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

    results = []

    for rank, (other, score) in enumerate(top, start=1):
        match = _get_or_create_match(persona, other)
        match.score = score
        match.updated_at = datetime.utcnow()

        if persona.id == match.persona_low_id:
            match.low_ranks_high = rank
        else:
            match.high_ranks_low = rank

        if match.is_mutual_top and match.status == "candidate":
            # Historical match status is a reciprocal *ranking*, not an
            # expression of interest. No notification is generated here.
            match.status = "matched"
            match.matched_at = datetime.utcnow()

        results.append((match, other, score))

    db.session.commit()

    # Rankings are just suggestions. Do NOT notify users or claim mutual
    # romantic interest until each explicitly expresses interest.
    if _cascade:
        for other, _score in top:
            generate_matches_for_persona(other, top_n=top_n, _cascade=False)

    # Ranked suggestions are recalculated on each refresh; old one-sided
    # suggestions drop out when their rank is cleared. Mutual listings
    # require live reciprocal rankings as well as active status.

    return results


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
        if m.is_mutual_top
        and other and other.id not in blocked
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
    # Once blocked, prior interest does not survive. Unblocking never
    # silently recreates an earlier relationship.
    DatingInterest.query.filter(or_(
        and_(DatingInterest.sender_id == blocker.id,
             DatingInterest.recipient_id == target.id),
        and_(DatingInterest.sender_id == target.id,
             DatingInterest.recipient_id == blocker.id),
    )).delete(synchronize_session=False)
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
    DatingInterest.query.filter(or_(
        DatingInterest.sender_id == persona.id,
        DatingInterest.recipient_id == persona.id,
    )).delete(synchronize_session=False)
    db.session.delete(persona)
    db.session.commit()



def sent_interest_ids(persona: DatingPersona):
    if not persona:
        return set()
    return {row.recipient_id for row in DatingInterest.query.filter_by(
        sender_id=persona.id).all()}


def mutual_connections(persona: DatingPersona):
    """Only show people who deliberately expressed interest in each other."""
    if not persona or not persona.is_active_and_visible():
        return []
    blocked = _blocked_ids(persona.id)
    outgoing = DatingInterest.query.filter_by(sender_id=persona.id).order_by(
        DatingInterest.created_at.desc()).all()
    inward_ids = {
        row.sender_id for row in DatingInterest.query.filter_by(recipient_id=persona.id).all()
    }
    connections = []
    for liked in outgoing:
        if liked.recipient_id in blocked or liked.recipient_id not in inward_ids:
            continue
        other = db.session.get(DatingPersona, liked.recipient_id)
        if (other and other.is_active_and_visible()
                and persona.is_compatible_with(other)):
            connections.append(other)
    return connections


def express_interest(sender: DatingPersona, target: DatingPersona):
    """Return (created, reciprocated). One-sided interest is invisible.

    Notifications are generated exactly when the second side opts in, not
    when the ranking algorithm happens to place two members together.
    """
    if sender.id == target.id:
        raise ValueError("Cannot express interest in yourself")
    if not sender.is_active_and_visible() or not target.is_active_and_visible():
        raise ValueError("Both Dating personas must be active")
    if not sender.is_compatible_with(target) or is_blocked(sender.id, target.id):
        raise ValueError("These Dating personas cannot connect")

    existing = DatingInterest.query.filter_by(
        sender_id=sender.id, recipient_id=target.id).first()
    if existing:
        return False, bool(DatingInterest.query.filter_by(
            sender_id=target.id, recipient_id=sender.id).first())

    reciprocal = DatingInterest.query.filter_by(
        sender_id=target.id, recipient_id=sender.id).first() is not None
    db.session.add(DatingInterest(sender_id=sender.id, recipient_id=target.id))
    db.session.commit()
    if reciprocal:
        # These are private, mutual invitations and do not expose any
        # personal address, phone number, employer, or profile detail.
        sender_name = sender.display_name or "A member"
        target_name = target.display_name or "A member"
        notify(sender.profile.user,
               f"You and {target_name} both expressed interest! See Dating connections.",
               category="success")
        notify(target.profile.user,
               f"You and {sender_name} both expressed interest! See Dating connections.",
               category="success")
    return True, reciprocal


def withdraw_interest(sender: DatingPersona, target_id: int):
    interest = DatingInterest.query.filter_by(
        sender_id=sender.id, recipient_id=target_id).first()
    if interest is None:
        return False
    db.session.delete(interest)
    db.session.commit()
    return True
