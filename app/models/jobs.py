"""Jobs, part-time gigs, employers and voluntary applications.

Employer accounts are NOT NYSC platoon members. Every organisation and
listing needs a separate admin review before public discovery. Applicant
contact data is sent only through a deliberate application.
"""
from datetime import datetime

from app.extensions import db

EMPLOYER_KINDS = (
    ("school", "School or educational institution"),
    ("business", "Business or company"),
    ("ngo", "NGO or community organisation"),
    ("public", "Public agency"),
    ("other", "Other organisation"),
)
JOB_KINDS = (
    ("gig", "One-off gig"),
    ("part_time", "Part-time"),
    ("full_time", "Full-time"),
    ("internship", "Internship"),
    ("contract", "Contract"),
)
WORK_MODES = (
    ("onsite", "On-site"),
    ("hybrid", "Hybrid"),
    ("remote", "Remote"),
)
PAY_UNITS = (
    ("hour", "Per hour"), ("day", "Per day"), ("week", "Per week"),
    ("month", "Per month"), ("project", "Per project"),
)
APP_STATUSES = ("submitted", "shortlisted", "declined", "hired")


class Employer(db.Model):
    __tablename__ = "job_employers"
    id = db.Column(db.Integer, primary_key=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                              nullable=False, unique=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    kind = db.Column(db.String(20), nullable=False)
    state = db.Column(db.String(60), nullable=False)
    lga = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    description = db.Column(db.String(1200), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)
    contact_phone = db.Column(db.String(30))
    website = db.Column(db.String(255))
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    review_note = db.Column(db.String(500))
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    owner = db.relationship("User", foreign_keys=[owner_user_id])
    listings = db.relationship("JobListing", back_populates="employer",
                               cascade="all, delete-orphan")

    @property
    def kind_label(self):
        return dict(EMPLOYER_KINDS).get(self.kind, self.kind)


class JobListing(db.Model):
    __tablename__ = "job_listings"
    id = db.Column(db.Integer, primary_key=True)
    employer_id = db.Column(db.Integer, db.ForeignKey("job_employers.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    title = db.Column(db.String(160), nullable=False)
    job_kind = db.Column(db.String(16), nullable=False, index=True)
    work_mode = db.Column(db.String(12), nullable=False)
    state = db.Column(db.String(60), nullable=False, index=True)
    lga = db.Column(db.String(100))
    location_description = db.Column(db.String(255))
    description = db.Column(db.Text, nullable=False)
    requirements = db.Column(db.Text, nullable=False)
    hours_per_week = db.Column(db.Integer)
    schedule_notes = db.Column(db.String(240))
    # Non-zero compensation is mandatory to limit exploitation and fake
    # unpaid "trial" shifts. Amounts are NGN; no platform payment gateway.
    pay_min = db.Column(db.Integer, nullable=False)
    pay_max = db.Column(db.Integer, nullable=False)
    pay_unit = db.Column(db.String(12), nullable=False)
    closing_date = db.Column(db.Date, nullable=False)
    serving_only = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(16), nullable=False, default="pending", index=True)
    review_note = db.Column(db.String(500))
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    employer = db.relationship("Employer", back_populates="listings")
    applications = db.relationship("JobApplication", back_populates="listing",
                                   cascade="all, delete-orphan")

    @property
    def kind_label(self):
        return dict(JOB_KINDS).get(self.job_kind, self.job_kind)

    @property
    def work_label(self):
        return dict(WORK_MODES).get(self.work_mode, self.work_mode)

    @property
    def pay_label(self):
        return dict(PAY_UNITS).get(self.pay_unit, self.pay_unit)

    @property
    def is_open(self):
        return (self.status == "published" and self.employer.status == "approved"
                and self.closing_date >= datetime.utcnow().date()
                and self.employer.owner.is_active)


class JobApplication(db.Model):
    __tablename__ = "job_applications"
    __table_args__ = (
        db.UniqueConstraint("job_id", "applicant_user_id", name="uq_job_one_application"),
    )
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey("job_listings.id", ondelete="CASCADE"),
                       nullable=False, index=True)
    applicant_user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                                  nullable=False, index=True)
    cover_note = db.Column(db.String(1500), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)
    contact_phone = db.Column(db.String(30))
    status = db.Column(db.String(12), nullable=False, default="submitted", index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow,
                           onupdate=datetime.utcnow)

    listing = db.relationship("JobListing", back_populates="applications")
    applicant = db.relationship("User")
