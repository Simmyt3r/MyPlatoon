"""Private job-work journal and two-party termination consent records."""
from datetime import datetime

from sqlalchemy import text
from app.extensions import db


class GigWorkUpdate(db.Model):
    __tablename__ = "gig_work_updates"
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey(
        "gig_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False, default="message")
    body = db.Column(db.String(1200), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deal = db.relationship("GigDeal")
    author = db.relationship("User")


class GigTerminationRequest(db.Model):
    __tablename__ = "gig_termination_requests"
    __table_args__ = (
        db.Index("uq_pending_gig_termination", "deal_id", unique=True,
                 postgresql_where=text("status = 'pending'"),
                 sqlite_where=text("status = 'pending'")),
    )
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey(
        "gig_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    proposer_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(1000), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="pending")
    respondent_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime)
    deal = db.relationship("GigDeal")
    proposer = db.relationship("User", foreign_keys=[proposer_id])
