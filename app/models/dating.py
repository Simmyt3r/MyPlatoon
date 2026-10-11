"""Dating feature models.

Design notes (see conversation for the reasoning):
  * Dating is entirely opt-in -- a Profile is never enrolled just because
    it exists. A member explicitly creates a DatingPersona.
  * Only approved profiles can create one, consistent with the rest of the
    app's trust model (an admin has already vetted the underlying person).
  * Matching is fully automatic (no manual swiping) and ranked by a
    compatibility score -- see app/services/dating_service.py.
  * The celebratory "It's a Match!" notification only fires when the
    ranking is MUTUAL (each appears in the other's top matches), not the
    instant anyone's algorithm ranks a stranger highly. One-sided high
    rankings still show up in "your top matches" for browsing, but don't
    notify the other person -- avoids notifying someone that a stranger's
    system ranked them highly when it isn't reciprocated.
"""
from datetime import datetime

from app.extensions import db

GENDER_CHOICES = ("male", "female")
PERSONA_STATUSES = ("active", "paused")
MATCH_STATUSES = ("candidate", "matched", "unmatched")

# Fun, human copy for compatibility score bands -- shown next to the
# percentage everywhere a match score appears, so a match never just reads
# as a cold, clinical number.
SCORE_BANDS = (
    (90, "Soulmate Vibes", "\U0001F4AB"),   # 90-100  💫
    (75, "Great Match", "\u2728"),          # 75-89   ✨
    (55, "Worth a Shot", "\U0001F440"),     # 55-74   👀
    (0, "Wildcard", "\U0001F3B2"),          # 0-54    🎲
)


def score_label(score):
    for threshold, label, emoji in SCORE_BANDS:
        if score >= threshold:
            return label, emoji
    return SCORE_BANDS[-1][1], SCORE_BANDS[-1][2]


class DatingPersona(db.Model):
    __tablename__ = "dating_personas"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"),
                            unique=True, nullable=False, index=True)

    display_name = db.Column(db.String(80))
    tagline = db.Column(db.String(140))
    bio = db.Column(db.Text)
    gender = db.Column(db.String(10), nullable=False)
    interested_in = db.Column(db.String(10), nullable=False)
    interests = db.Column(db.String(500))  # comma-separated tags, same pattern as skills

    # Self-attested 18+ eligibility. Never store a DOB solely for Dating.
    # NULL on pre-upgrade personas forces confirmation before further use.
    age_confirmed_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(10), default="active", nullable=False, index=True)
    is_reported = db.Column(db.Boolean, default=False, nullable=False)
    report_reason = db.Column(db.String(500))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                            nullable=False)

    profile = db.relationship("Profile", backref=db.backref("dating_persona", uselist=False,
                                                              cascade="all, delete-orphan"))

    def interest_list(self):
        return [i.strip() for i in (self.interests or "").split(",") if i.strip()]

    def shared_interests_with(self, other):
        if not other:
            return []
        mine_lower = {i.lower() for i in self.interest_list()}
        return [i for i in other.interest_list() if i.lower() in mine_lower]

    def is_compatible_with(self, other) -> bool:
        """Mutual gender-preference compatibility (see GENDER_CHOICES)."""
        return self.gender == other.interested_in and other.gender == self.interested_in

    def is_active_and_visible(self) -> bool:
        return (self.status == "active" and not self.is_reported
                and self.age_confirmed_at is not None
                and self.profile is not None
                and self.profile.status == "approved"
                and self.profile.user.is_active_account
                and not self.profile.user.is_suspended)

    def __repr__(self):
        return f"<DatingPersona profile_id={self.profile_id} status={self.status}>"


class DatingMatch(db.Model):
    """One row per unique persona pair, stored with a canonical (low_id,
    high_id) ordering so a pair is never duplicated regardless of which
    side's match-generation run created it."""
    __tablename__ = "dating_matches"
    __table_args__ = (
        db.UniqueConstraint("persona_low_id", "persona_high_id", name="uq_dating_pair"),
        db.CheckConstraint("persona_low_id < persona_high_id", name="ck_dating_pair_order"),
    )

    id = db.Column(db.Integer, primary_key=True)
    persona_low_id = db.Column(db.Integer, db.ForeignKey("dating_personas.id", ondelete="CASCADE"),
                                nullable=False, index=True)
    persona_high_id = db.Column(db.Integer, db.ForeignKey("dating_personas.id", ondelete="CASCADE"),
                                 nullable=False, index=True)

    score = db.Column(db.Float, nullable=False)  # 0-100, symmetric compatibility score
    low_ranks_high = db.Column(db.Integer)  # this pair's rank within persona_low's top list (1 = best)
    high_ranks_low = db.Column(db.Integer)  # this pair's rank within persona_high's top list

    status = db.Column(db.String(12), default="candidate", nullable=False, index=True)
    matched_notified = db.Column(db.Boolean, default=False, nullable=False)
    matched_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
                            nullable=False)

    persona_low = db.relationship("DatingPersona", foreign_keys=[persona_low_id])
    persona_high = db.relationship("DatingPersona", foreign_keys=[persona_high_id])

    @property
    def is_mutual_top(self) -> bool:
        return self.low_ranks_high is not None and self.high_ranks_low is not None

    def other_persona(self, persona_id):
        if persona_id == self.persona_low_id:
            return self.persona_high
        return self.persona_low

    def __repr__(self):
        return f"<DatingMatch {self.persona_low_id}<->{self.persona_high_id} score={self.score:.0f} {self.status}>"



class DatingBlock(db.Model):
    """One-way personal block. Neither participant sees the other in Dating.

    Unlike reports, blocking does not reveal the reason to the blocked person
    and does not hide anyone from unrelated participants.
    """
    __tablename__ = "dating_blocks"
    __table_args__ = (
        db.UniqueConstraint("blocker_id", "blocked_id", name="uq_dating_block_pair"),
        db.CheckConstraint("blocker_id != blocked_id", name="ck_dating_no_self_block"),
    )

    id = db.Column(db.Integer, primary_key=True)
    blocker_id = db.Column(db.Integer, db.ForeignKey("dating_personas.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    blocked_id = db.Column(db.Integer, db.ForeignKey("dating_personas.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    blocker = db.relationship("DatingPersona", foreign_keys=[blocker_id])
    blocked = db.relationship("DatingPersona", foreign_keys=[blocked_id])
