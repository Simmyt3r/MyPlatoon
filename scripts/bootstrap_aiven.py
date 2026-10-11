"""Idempotent first-admin + categories bootstrap after a fresh Aiven migration.

Run only through the protected GitHub Actions production environment. This
script never resets a password or changes roles on existing accounts.
"""
import os
import sys

# Running `python scripts/...` must resolve the repository's app package.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import User, Profile, BusinessCategory, DEFAULT_CATEGORIES


def main():
    # Don't print credentials, DSNs or tokens in logs.
    email = (os.environ.get("ADMIN_INIT_EMAIL") or "").strip().lower()
    password = os.environ.get("ADMIN_INIT_PASSWORD") or ""
    if not email or "@" not in email or len(password) < 16:
        raise RuntimeError(
            "Set ADMIN_INIT_EMAIL and a strong ADMIN_INIT_PASSWORD (16+ chars) "
            "as GitHub production environment secrets."
        )

    app = create_app("production")
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user:
            if user.role != "admin":
                raise RuntimeError("That address belongs to a non-admin. Refusing role escalation.")
            print("Admin exists: credentials unchanged.")
        else:
            user = User(full_name="MyPlatoon Administrator", email=email, role="admin")
            user.set_password(password)
            db.session.add(user)
            db.session.flush()
            db.session.add(Profile(user_id=user.id))
            print("Created initial administrator.")

        for label in DEFAULT_CATEGORIES:
            exists = BusinessCategory.query.filter_by(name=label).first()
            if not exists:
                db.session.add(BusinessCategory(name=label))
        db.session.commit()
    print("Bootstrap successful. No credentials shown.")


if __name__ == "__main__":
    main()
