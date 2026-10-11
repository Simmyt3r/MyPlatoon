"""Guarantees every User has a companion Profile.

Registration always creates both together, but a few paths historically
didn't (admin accounts created via the CLI, the ADMIN_INIT_EMAIL/PASSWORD
auto-seed, or scripts/seed.py before this existed) -- and nearly every
authenticated page assumes `current_user.profile` is never None. This is
the single place that invariant gets enforced/repaired.
"""
from app.extensions import db


def ensure_profile(user):
    """If `user` has no Profile yet, create one and attach it in-memory.

    Assigning through the relationship (rather than adding a separately
    constructed Profile and committing) keeps SQLAlchemy's identity map in
    sync immediately on the same `user` object -- important because the
    caller has usually just checked `user.profile is None`, which caches
    that (now-stale) result on the instance unless we update it this way.
    """
    if user is None or user.profile is not None:
        return
    from app.models import Profile
    user.profile = Profile(status="approved" if user.is_admin else "draft")
    db.session.commit()
