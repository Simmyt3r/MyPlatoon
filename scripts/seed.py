"""Development seed script.

Usage:
    python scripts/seed.py

Creates:
  * one admin account (development/demo only — DO NOT use in production)
  * several sample members with varying profile-completion levels
  * several sample businesses across categories
  * the default business categories

All accounts created here are clearly fake and use example.com emails.
Never seed real user data with this script.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.extensions import db
from app.models import (
    User, Profile, Skill, Business, BusinessCategory, DEFAULT_CATEGORIES, Announcement, Platoon,
)

SAMPLE_MEMBERS = [
    {
        "full_name": "Chidinma Okafor", "email": "chidinma.demo@example.com",
        "profession": "Software Engineer", "state": "Anambra", "lga": "Awka South",
        "institution": "University of Nigeria, Nsukka", "skills": "Python, Flask, React",
        "bio": "Backend-leaning full-stack developer passionate about civic tech.",
        "status": "approved",
    },
    {
        "full_name": "Musa Abdullahi", "email": "musa.demo@example.com",
        "profession": "Agricultural Extension Officer", "state": "Kano", "lga": "Nassarawa",
        "institution": "Ahmadu Bello University", "skills": "Agronomy, Farm Advisory",
        "bio": "Working to bring modern agricultural practices to smallholder farmers.",
        "status": "approved",
    },
    {
        "full_name": "Ifeoma Nwosu", "email": "ifeoma.demo@example.com",
        "profession": "Graphic Designer", "state": "Imo", "lga": "Owerri Municipal",
        "institution": "Federal University of Technology, Owerri", "skills": "Branding, Illustration, Figma",
        "bio": "Visual storyteller helping small businesses build memorable brands.",
        "status": "pending",
    },
    {
        "full_name": "Emeka Eze", "email": "emeka.demo@example.com",
        "profession": "Photographer", "state": "Enugu", "lga": "Enugu East",
        "institution": "University of Nigeria, Nsukka", "skills": "Event Photography, Editing",
        "bio": "", "status": "draft",
    },
    {
        "full_name": "Blessing Etim", "email": "blessing.demo@example.com",
        "profession": "Registered Nurse", "state": "Akwa Ibom", "lga": "Uyo",
        "institution": "University of Uyo", "skills": "Community Health, First Aid Training",
        "bio": "Committed to accessible primary healthcare in underserved communities.",
        "status": "approved",
    },
]

SAMPLE_BUSINESSES = [
    {"owner_email": "chidinma.demo@example.com", "name": "CodeCraft Solutions",
     "category": "Technology", "description": "Custom web and mobile app development."},
    {"owner_email": "ifeoma.demo@example.com", "name": "Ify Creatives",
     "category": "Creative Arts", "description": "Branding and graphic design studio."},
    {"owner_email": "blessing.demo@example.com", "name": "CareFirst Health Consult",
     "category": "Health", "description": "Home nursing and health education services."},
]


def run():
    app = create_app(os.environ.get("FLASK_ENV", "development"))
    with app.app_context():
        db.create_all()

        # --- Categories ---
        for name in DEFAULT_CATEGORIES:
            if not BusinessCategory.query.filter_by(name=name).first():
                db.session.add(BusinessCategory(name=name))
        db.session.commit()

        # --- Admin ---
        admin_email = "admin.demo@example.com"
        if not User.query.filter_by(email=admin_email).first():
            admin = User(full_name="MyPlatoon Administrator (Demo)", email=admin_email, role="admin")
            admin.set_password("ChangeMe123!")
            db.session.add(admin)
            db.session.flush()
            db.session.add(Profile(user_id=admin.id, status="approved"))
            db.session.commit()
            print(f"Created demo admin: {admin_email} / ChangeMe123! (CHANGE THIS)")

        # --- Members ---
        for m in SAMPLE_MEMBERS:
            if User.query.filter_by(email=m["email"]).first():
                continue
            user = User(full_name=m["full_name"], email=m["email"], role="member")
            user.set_password("ChangeMe123!")
            db.session.add(user)
            db.session.flush()

            profile = Profile(
                user_id=user.id,
                profession=m["profession"],
                state_of_origin=m["state"],
                lga=m["lga"],
                institution=m["institution"],
                biography=m["bio"],
                status=m["status"],
                phone_number="+2348000000000",
                whatsapp_number="+2348000000000",
                phone_visibility="platoon",
                whatsapp_visibility="platoon",
            )
            # Demo cohorts are fictional and must not be copied onto real members.
            if m["status"] == "approved":
                profile.service_stage = "serving"
                demo_camp = {
                    "chidinma.demo@example.com": ("Anambra", 2026, "B", "II", 5),
                    "musa.demo@example.com": ("Kano", 2026, "B", "II", 5),
                    "blessing.demo@example.com": ("Akwa Ibom", 2026, "A", "I", 2),
                }[m["email"]]
                profile.platoon = Platoon.find_or_create(*demo_camp)
            db.session.add(profile)
            db.session.flush()

            for skill_name in m["skills"].split(","):
                skill_name = skill_name.strip()
                if not skill_name:
                    continue
                skill = Skill.query.filter_by(name=skill_name).first()
                if not skill:
                    skill = Skill(name=skill_name)
                    db.session.add(skill)
                    db.session.flush()
                profile.skills.append(skill)

        db.session.commit()
        print(f"Seeded {len(SAMPLE_MEMBERS)} sample members (password: ChangeMe123!)")

        # --- Businesses ---
        created = 0
        for b in SAMPLE_BUSINESSES:
            owner = User.query.filter_by(email=b["owner_email"]).first()
            if not owner or not owner.profile:
                continue
            if Business.query.filter_by(name=b["name"]).first():
                continue
            category = BusinessCategory.query.filter_by(name=b["category"]).first()
            db.session.add(Business(
                profile_id=owner.profile.id, name=b["name"], category_id=category.id if category else None,
                description=b["description"],
            ))
            created += 1
        db.session.commit()
        print(f"Seeded {created} sample businesses.")

        # --- Announcement ---
        if not Announcement.query.first():
            admin = User.query.filter_by(email=admin_email).first()
            db.session.add(Announcement(
                title="Welcome to MyPlatoon!",
                body="Join as a PCM or add your camp platoon and connect with your NYSC community.",
                created_by_id=admin.id if admin else None,
            ))
            db.session.commit()
            print("Seeded a welcome announcement.")

        print("\nSeed complete. All accounts are DEMO accounts — do not use in production.")


if __name__ == "__main__":
    run()
