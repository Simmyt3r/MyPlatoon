"""Accepted gig agreements, private work tracking and post-completion feedback.

Payments occur outside MyPlatoon. Status flags are voluntary attestations,
never proof of an actual bank transfer. A party cannot accept for the other,
or unilaterally declare a deal completed.
"""
from datetime import datetime
from app.extensions import db

DEAL_STATUSES = ("offered", "declined", "active", "completion_requested",
                 "completed", "disputed", "cancelled")
PAYMENT_STATUSES = ("not_reported", "reported_paid", "confirmed_paid")
RATING_ROLES = ("worker", "employer")


class GigDeal(db.Model):
    __tablename__ = "gig_deals"
    __table_args__ = (
        db.UniqueConstraint("application_id", name="uq_gig_deal_application"),
        db.CheckConstraint("pay_amount > 0", name="ck_gig_deal_positive_pay"),
    )
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey(
        "job_applications.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    employer_id = db.Column(db.Integer, db.ForeignKey(
        "job_employers.id", ondelete="CASCADE"), nullable=False, index=True)
    worker_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    # The exact offer remains immutable once sent.
    scope = db.Column(db.String(2500), nullable=False)
    schedule = db.Column(db.String(300), nullable=False)
    pay_amount = db.Column(db.Integer, nullable=False)
    pay_unit = db.Column(db.String(12), nullable=False)
    status = db.Column(db.String(24), default="offered", nullable=False, index=True)
    payment_status = db.Column(db.String(20), default="not_reported", nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    accepted_at = db.Column(db.DateTime)
    completion_requested_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)
    application = db.relationship("JobApplication", backref=db.backref(
        "gig_deal", uselist=False, cascade="all, delete-orphan"))
    employer = db.relationship("Employer")
    worker = db.relationship("User", foreign_keys=[worker_id])
    reviews = db.relationship("GigReview", back_populates="deal",
                              cascade="all, delete-orphan")
    disputes = db.relationship("GigDispute", back_populates="deal",
                               cascade="all, delete-orphan")


class GigDispute(db.Model):
    __tablename__ = "gig_disputes"
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey(
        "gig_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    raised_by_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    reason = db.Column(db.String(1500), nullable=False)
    category = db.Column(db.String(32), default="other", nullable=False)
    outcome_code = db.Column(db.String(32))
    status = db.Column(db.String(16), default="open", nullable=False, index=True)
    resolution = db.Column(db.String(1000))
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    deal = db.relationship("GigDeal", back_populates="disputes")
    reporter = db.relationship("User", foreign_keys=[raised_by_id])
    evidence = db.relationship("GigDisputeEvidence", back_populates="dispute",
                               cascade="all, delete-orphan")
    events = db.relationship("GigDisputeEvent", back_populates="dispute",
                             cascade="all, delete-orphan")


class GigReview(db.Model):
    __tablename__ = "gig_reviews"
    __table_args__ = (
        db.UniqueConstraint("deal_id", "reviewer_id", name="uq_gig_review_deal_reviewer"),
        db.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_gig_review_stars"),
    )
    id = db.Column(db.Integer, primary_key=True)
    deal_id = db.Column(db.Integer, db.ForeignKey(
        "gig_deals.id", ondelete="CASCADE"), nullable=False, index=True)
    reviewer_id = db.Column(db.Integer, db.ForeignKey(
        "users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = db.Column(db.String(12), nullable=False)
    stars = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.String(500))
    # Existing reviews remain private after migration. Only a worker's
    # explicitly opted-in and moderator-approved review can become public.
    public_consent = db.Column(db.Boolean, nullable=False, default=False)
    moderation_status = db.Column(db.String(16), nullable=False, default="private", index=True)
    moderation_note = db.Column(db.String(500))
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deal = db.relationship("GigDeal", back_populates="reviews")
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
