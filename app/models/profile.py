import uuid
from datetime import datetime

from app.extensions import db
from app.models.skill import profile_skills

VISIBILITY_LEVELS = ("public", "platoon", "private")
ADDRESS_VISIBILITY_LEVELS = ("general", "exact", "private")
PROFILE_STATES = ("draft", "pending", "approved", "rejected", "suspended")


class Profile(db.Model):
    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(36), unique=True, nullable=False,
                      default=lambda: uuid.uuid4().hex[:12])
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"),
                         unique=True, nullable=False)

    # --- Personal information ---
    nickname = db.Column(db.String(80))
    photo_url = db.Column(db.String(500))
    photo_public_id = db.Column(db.String(255))  # Cloudinary asset id, for deletion
    gender = db.Column(db.String(20))
    state_of_origin = db.Column(db.String(60), index=True)
    lga = db.Column(db.String(80), index=True)
    phone_number = db.Column(db.String(30))
    whatsapp_number = db.Column(db.String(30))
    current_location = db.Column(db.String(120))
    address = db.Column(db.String(255))

    # --- Professional information ---
    profession = db.Column(db.String(120), index=True)
    course_of_study = db.Column(db.String(150))
    institution = db.Column(db.String(150))
    graduation_year = db.Column(db.Integer)
    certifications = db.Column(db.Text)
    biography = db.Column(db.Text)

    # --- Social links ---
    website = db.Column(db.String(255))
    facebook = db.Column(db.String(255))
    instagram = db.Column(db.String(255))
    tiktok = db.Column(db.String(255))
    twitter_x = db.Column(db.String(255))

    # --- Privacy settings (defaults are conservative) ---
    profile_visibility = db.Column(db.String(20), default="platoon", nullable=False)
    phone_visibility = db.Column(db.String(20), default="private", nullable=False)
    whatsapp_visibility = db.Column(db.String(20), default="platoon", nullable=False)
    address_visibility = db.Column(db.String(20), default="private", nullable=False)

    # --- Workflow state ---
    status = db.Column(db.String(20), default="draft", nullable=False, index=True)
    rejection_reason = db.Column(db.Text)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    reviewed_at = db.Column(db.DateTime)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="profile", foreign_keys=[user_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])
    skills = db.relationship("Skill", secondary=profile_skills, back_populates="profiles")
    businesses = db.relationship("Business", back_populates="profile",
                                  cascade="all, delete-orphan")

    # ------------------------------------------------------------------
    # Completion scoring (weights per the product spec)
    # ------------------------------------------------------------------
    COMPLETION_WEIGHTS = {
        "photo": 10,
        "full_name": 10,
        "profession": 10,
        "state_lga": 10,
        "biography": 10,
        "skills": 10,
        "contact": 10,
        "business": 20,
        "social_links": 10,
    }

    def completion_breakdown(self):
        checks = {
            "photo": bool(self.photo_url),
            "full_name": bool(self.user and self.user.full_name),
            "profession": bool(self.profession),
            "state_lga": bool(self.state_of_origin and self.lga),
            "biography": bool(self.biography and len(self.biography.strip()) >= 20),
            "skills": len(self.skills) > 0,
            "contact": bool(self.phone_number or self.whatsapp_number),
            "business": len(self.businesses) > 0,
            "social_links": bool(self.website or self.facebook or self.instagram
                                  or self.tiktok or self.twitter_x),
        }
        return checks

    def completion_percent(self) -> int:
        checks = self.completion_breakdown()
        total = sum(self.COMPLETION_WEIGHTS[k] for k, done in checks.items() if done)
        return min(total, 100)

    def visible_field(self, field: str, viewer_is_platoon_member: bool, viewer_is_owner: bool,
                       viewer_is_admin: bool = False):
        """Return the raw value only if the viewer is permitted to see it."""
        if viewer_is_owner or viewer_is_admin:
            return getattr(self, field)

        level_map = {
            "phone_number": self.phone_visibility,
            "whatsapp_number": self.whatsapp_visibility,
            "address": self.address_visibility,
        }
        level = level_map.get(field)
        value = getattr(self, field)

        if field == "address":
            if level == "exact":
                return value
            if level == "general":
                return self.current_location or None
            return None

        if level == "public":
            return value
        if level == "platoon" and viewer_is_platoon_member:
            return value
        return None

    def is_publicly_listable(self) -> bool:
        return self.status == "approved" and self.profile_visibility in ("public", "platoon")

    def __repr__(self):
        return f"<Profile slug={self.slug} status={self.status}>"
