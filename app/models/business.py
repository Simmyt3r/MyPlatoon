from datetime import datetime

from app.extensions import db

DEFAULT_CATEGORIES = [
    "Technology", "Fashion", "Food", "Agriculture", "Education", "Health",
    "Photography", "Beauty", "Construction", "Transportation", "Media",
    "Finance", "Retail", "Logistics", "Professional Services",
    "Creative Arts", "Other",
]


class BusinessCategory(db.Model):
    __tablename__ = "business_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)

    businesses = db.relationship("Business", back_populates="category")

    def __repr__(self):
        return f"<BusinessCategory {self.name}>"


class Business(db.Model):
    __tablename__ = "businesses"

    id = db.Column(db.Integer, primary_key=True)
    profile_id = db.Column(db.Integer, db.ForeignKey("profiles.id", ondelete="CASCADE"),
                            nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("business_categories.id"),
                             nullable=True, index=True)

    name = db.Column(db.String(150), nullable=False, index=True)
    description = db.Column(db.Text)
    logo_url = db.Column(db.String(500))
    logo_public_id = db.Column(db.String(255))

    address = db.Column(db.String(255))
    phone = db.Column(db.String(30))
    whatsapp = db.Column(db.String(30))
    email = db.Column(db.String(255))
    website = db.Column(db.String(255))
    facebook = db.Column(db.String(255))
    instagram = db.Column(db.String(255))
    tiktok = db.Column(db.String(255))
    twitter_x = db.Column(db.String(255))

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow,
                            onupdate=datetime.utcnow, nullable=False)

    profile = db.relationship("Profile", back_populates="businesses")
    category = db.relationship("BusinessCategory", back_populates="businesses")

    def __repr__(self):
        return f"<Business {self.name}>"
