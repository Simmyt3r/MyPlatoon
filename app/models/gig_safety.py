"""Private, low-volume gig dispute evidence and append-only case timeline.

Uploaded evidence remains in the database: no public Cloudinary assets or
third-party sharing links. File access is separately authorized by uploader
identity or admin role. This is not evidence authenticity verification.
"""
from datetime import datetime

from app.extensions import db

GIG_DISPUTE_CATEGORIES = (
    ("nonpayment", "Unpaid or disputed payment"),
    ("safety", "Unsafe working conditions"),
    ("harassment", "Harassment or threatening conduct"),
    ("scope", "Changed work or agreed terms"),
    ("other", "Other contract or conduct issue"),
)
GIG_DISPUTE_EVIDENCE_KINDS = (
    ("statement", "Written statement"),
    ("work_record", "Work/delivery record"),
    ("payment_record", "Payment-related record"),
    ("other", "Other supporting information"),
)


class GigDisputeEvidence(db.Model):
    __tablename__ = "gig_dispute_evidence"
    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey(
        "gig_disputes.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = db.Column(db.String(24), nullable=False)
    description = db.Column(db.String(1800), nullable=False)
    filename = db.Column(db.String(180))
    content_type = db.Column(db.String(48))
    file_size = db.Column(db.Integer)
    sha256 = db.Column(db.String(64))
    attachment = db.Column(db.LargeBinary)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    dispute = db.relationship("GigDispute", back_populates="evidence")
    submitter = db.relationship("User", foreign_keys=[submitted_by_id])


class GigDisputeEvent(db.Model):
    __tablename__ = "gig_dispute_events"
    id = db.Column(db.Integer, primary_key=True)
    dispute_id = db.Column(db.Integer, db.ForeignKey(
        "gig_disputes.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="SET NULL"))
    kind = db.Column(db.String(32), nullable=False)
    description = db.Column(db.String(750), nullable=False)
    # Public to both participants only when explicitly intended.
    visibility = db.Column(db.String(16), default="participants", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    dispute = db.relationship("GigDispute", back_populates="events")
    actor = db.relationship("User")
