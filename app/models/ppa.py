"""Corps-member-sourced Places of Primary Assignment (PPAs).

These records are NOT official NYSC postings or eligibility confirmations.
Every new or materially edited record requires moderator review.
Coordinates describe an institution/workplace, never a member's home.
"""
from datetime import datetime
from app.extensions import db
from app.models.platoon import NYSC_STATES

PPA_SECTORS = (
    ("education", "Education"),
    ("health", "Healthcare"),
    ("government", "Government"),
    ("agriculture", "Agriculture"),
    ("technology", "Technology"),
    ("ngo", "NGO / Civil Society"),
    ("finance", "Finance"),
    ("industry", "Industry"),
    ("other", "Other"),
)
PPA_STATUSES = ("pending", "verified", "rejected")
PPA_YES_NO = (("unknown", "Unknown"), ("yes", "Yes"), ("no", "No"))


class PPA(db.Model):
    __tablename__ = "ppas"
    __table_args__ = (
        db.CheckConstraint("latitude IS NULL OR (latitude BETWEEN -90 AND 90)",
                           name="ck_ppa_latitude"),
        db.CheckConstraint("longitude IS NULL OR (longitude BETWEEN -180 AND 180)",
                           name="ck_ppa_longitude"),
        db.CheckConstraint(
            "(latitude IS NULL AND longitude IS NULL) OR "
            "(latitude IS NOT NULL AND longitude IS NOT NULL)",
            name="ck_ppa_coordinates_both"),
        db.Index("ix_ppas_state_lga_status", "state", "lga", "status"),
    )
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    # Normalized display name is used for duplicate checking, scoped by state and LGA.
    name_key = db.Column(db.String(180), nullable=False, index=True)
    state = db.Column(db.String(40), nullable=False, index=True)
    lga = db.Column(db.String(100), nullable=False)
    town = db.Column(db.String(120), nullable=True)
    address = db.Column(db.String(250), nullable=True)
    sector = db.Column(db.String(24), nullable=False, default="other")
    website = db.Column(db.String(250), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    # When a reporter knows only town/LGA, the pin must NOT be guessed.
    accommodation = db.Column(db.String(12), nullable=False, default="unknown")
    allowance = db.Column(db.String(12), nullable=False, default="unknown")
    experience_notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    submitted_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    verified_at = db.Column(db.DateTime, nullable=True)
    rejection_reason = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    submitter = db.relationship("User", foreign_keys=[submitted_by_id])
    reviewer = db.relationship("User", foreign_keys=[verified_by_id])
    experiences = db.relationship("PPAExperience", back_populates="ppa",
                                  cascade="all, delete-orphan", lazy="dynamic")

    @staticmethod
    def normalize_name(value):
        return " ".join((value or "").casefold().split())

    @property
    def has_location(self):
        return self.latitude is not None and self.longitude is not None

    @property
    def sector_label(self):
        return dict(PPA_SECTORS).get(self.sector, "Other")

    @property
    def public_location(self):
        # Return only vetted institutional coordinates. Zero is valid.
        if self.status == "verified" and self.has_location:
            return {"lat": self.latitude, "lng": self.longitude}
        return None


class PPAExperience(db.Model):
    """An independently moderated account by another corps member.

    Member identities are retained for moderation but never published.
    We allow at most one currently editable contribution per member/PPA.
    """
    __tablename__ = "ppa_experiences"
    __table_args__ = (
        db.UniqueConstraint("ppa_id", "submitted_by_id",
                            name="uq_ppa_experience_member"),
    )
    id = db.Column(db.Integer, primary_key=True)
    ppa_id = db.Column(db.Integer, db.ForeignKey("ppas.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"),
                                nullable=True, index=True)
    service_year = db.Column(db.Integer, nullable=False)
    accommodation = db.Column(db.String(12), nullable=False, default="unknown")
    allowance = db.Column(db.String(12), nullable=False, default="unknown")
    notes = db.Column(db.String(1200))
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    rejection_reason = db.Column(db.String(500))
    verified_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    ppa = db.relationship("PPA", back_populates="experiences")
    submitter = db.relationship("User", foreign_keys=[submitted_by_id])
