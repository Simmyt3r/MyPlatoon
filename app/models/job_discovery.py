"""Opt-in job discovery. Saved vacancies and alerts are private to each member."""
from datetime import datetime
from app.extensions import db


class SavedJob(db.Model):
    __tablename__ = "saved_jobs"
    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_saved_job_user"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    listing = db.relationship("JobListing")


class JobAlertPreference(db.Model):
    __tablename__ = "job_alert_preferences"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                        unique=True, nullable=False, index=True)
    # Blank state means use the member's recorded service state; never
    # confuse state of origin with place of NYSC service.
    preferred_state = db.Column(db.String(40))
    preferred_kinds = db.Column(db.String(120), nullable=False, default="gig,part_time")
    available_hours = db.Column(db.Integer)
    remote_ok = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class JobAlertDelivery(db.Model):
    """Idempotency marker: no duplicate announcement for a published listing."""
    __tablename__ = "job_alert_deliveries"
    __table_args__ = (db.UniqueConstraint("user_id", "job_id", name="uq_alert_delivery_user_job"),)
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_listings.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
