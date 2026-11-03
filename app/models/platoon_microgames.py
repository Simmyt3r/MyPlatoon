"""Automatically recorded digital microgame contributions per NYSC round."""
from datetime import datetime
from app.extensions import db


class PlatoonGameActivity(db.Model):
    __tablename__ = "platoon_game_activities"
    __table_args__ = (
        db.UniqueConstraint("period_start", "game_key", "user_id", "score_day",
                            name="uq_platoon_microgame_member_day"),
    )
    id = db.Column(db.Integer, primary_key=True)
    period_start = db.Column(db.Date(), nullable=False, index=True)
    game_key = db.Column(db.String(40), nullable=False, index=True)
    platoon_id = db.Column(db.Integer, db.ForeignKey("platoons.id"),
                           nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, index=True)
    # Daily games use the actual Nigeria calendar date; once-per-round games
    # use the round start so a member can only contribute once per round.
    score_day = db.Column(db.Date(), nullable=False)
    created_at = db.Column(db.DateTime(), nullable=False, default=datetime.utcnow)

    user = db.relationship("User")
    platoon = db.relationship("Platoon")
