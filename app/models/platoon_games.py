"""Inter-platoon competitions, 14-day leadership candidates and ballots."""
from datetime import datetime
from app.extensions import db


class PlatoonLeaderCandidate(db.Model):
    __tablename__ = "platoon_leader_candidates"
    __table_args__ = (
        db.UniqueConstraint("term_start", "user_id",
                            name="uq_platoon_leader_candidate_term_user"),
    )
    id = db.Column(db.Integer, primary_key=True)
    platoon_id = db.Column(db.Integer, db.ForeignKey("platoons.id"), nullable=False, index=True)
    term_start = db.Column(db.Date(), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    nominated_at = db.Column(db.DateTime(), nullable=False, default=datetime.utcnow)
    platoon = db.relationship("Platoon")
    user = db.relationship("User")


class PlatoonLeaderVote(db.Model):
    __tablename__ = "platoon_leader_votes"
    __table_args__ = (
        db.UniqueConstraint("term_start", "voter_id", name="uq_platoon_leader_term_voter"),
    )
    id = db.Column(db.Integer, primary_key=True)
    platoon_id = db.Column(db.Integer, db.ForeignKey("platoons.id"), nullable=False, index=True)
    term_start = db.Column(db.Date(), nullable=False, index=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey(
        "platoon_leader_candidates.id"), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime(), nullable=False, default=datetime.utcnow)
    candidate = db.relationship("PlatoonLeaderCandidate")
    voter = db.relationship("User")


class PlatoonGameResult(db.Model):
    __tablename__ = "platoon_game_results"
    __table_args__ = (
        db.UniqueConstraint("period_start", "game_key", "platoon_id",
                            name="uq_platoon_game_period_entry"),
        db.CheckConstraint("placement >= 1 AND placement <= 10",
                           name="ck_platoon_game_placement"),
    )
    id = db.Column(db.Integer, primary_key=True)
    period_start = db.Column(db.Date(), nullable=False, index=True)
    platoon_id = db.Column(db.Integer, db.ForeignKey("platoons.id"), nullable=False, index=True)
    game_key = db.Column(db.String(40), nullable=False)
    placement = db.Column(db.Integer, nullable=False)
    details = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime())
    created_at = db.Column(db.DateTime(), nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime(), nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)
    platoon = db.relationship("Platoon")
    submitter = db.relationship("User", foreign_keys=[submitted_by_id])
