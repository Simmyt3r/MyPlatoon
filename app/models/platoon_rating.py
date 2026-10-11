"""One 1–5 star community rating per approved member, for their OWN NYSC platoon."""
from datetime import datetime
from app.extensions import db


class PlatoonRating(db.Model):
    __tablename__ = "platoon_ratings"
    __table_args__ = (
        db.UniqueConstraint("platoon_id", "user_id", name="uq_platoon_rating_member"),
        db.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_platoon_rating_stars"),
    )
    id = db.Column(db.Integer, primary_key=True)
    platoon_id = db.Column(db.Integer, db.ForeignKey("platoons.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    # Global unique prevents a moved member from voting for two cohorts.
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        nullable=False, unique=True, index=True)
    stars = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, onupdate=datetime.utcnow)
    platoon = db.relationship("Platoon")
