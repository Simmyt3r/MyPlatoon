"""Guarantees every User has a companion Profile.

Registration creates a profile immediately. Historical accounts may not
have one, or may still carry old draft/pending approval states. This
service ensures active members are not blocked by the obsolete workflow,
while preserving explicit rejection and suspension decisions.
"""
from app.extensions import db


def ensure_profile(user):
    """Create missing profiles or activate legacy draft/pending members.

    The relationship assignment updates SQLAlchemy's identity map without
    leaving stale cached user.profile values. Rejected and suspended member
    accounts are never automatically reactivated.
    """
    if user is None or user.role == "employer":
        return
    from app.models import Profile
    if user.profile is None:
        user.profile = Profile(status="approved")
        db.session.commit()
    elif (user.role == "member"
          and user.is_active_account
          and not user.is_suspended
          and user.profile.status in ("draft", "pending")):
        # Existing signups must not remain trapped in the obsolete review
        # workflow. Never undo an administrator rejection or suspension.
        user.profile.status = "approved"
        db.session.commit()
