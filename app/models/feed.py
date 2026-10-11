from datetime import datetime

from app.extensions import db

REACTION_TYPES = ("like", "love", "celebrate", "support")


class AnnouncementReaction(db.Model):
    """One reaction per user per announcement (changing type replaces it)."""
    __tablename__ = "announcement_reactions"
    __table_args__ = (
        db.UniqueConstraint("announcement_id", "user_id", name="uq_reaction_per_user"),
    )

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey("announcements.id", ondelete="CASCADE"),
                                 nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    reaction_type = db.Column(db.String(20), default="like", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")
    announcement = db.relationship("Announcement", back_populates="reactions")


class AnnouncementComment(db.Model):
    __tablename__ = "announcement_comments"

    id = db.Column(db.Integer, primary_key=True)
    announcement_id = db.Column(db.Integer, db.ForeignKey("announcements.id", ondelete="CASCADE"),
                                 nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    body = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship("User")
    announcement = db.relationship("Announcement", back_populates="comments")
