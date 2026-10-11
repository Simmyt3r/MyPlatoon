"""Central place that decides what a given viewer is allowed to see.

Keeping this logic in one module (rather than scattering visibility
checks across templates and routes) is what makes "privacy by default"
actually enforceable.
"""
from flask_login import current_user


def viewer_context():
    """Return (is_authenticated, is_platoon_member, is_admin) for the
    current request's viewer."""
    if not current_user.is_authenticated:
        return False, False, False
    is_admin = current_user.is_admin
    is_platoon_member = current_user.profile is not None and current_user.profile.status == "approved"
    return True, is_platoon_member or is_admin, is_admin


def can_view_full_profile(profile) -> bool:
    """Guests: only if profile_visibility == public and approved.
    Platoon members: public or platoon-only, and approved.
    Owner/Admin: always.
    """
    is_auth, is_platoon_member, is_admin = viewer_context()
    if is_admin:
        return True
    if is_auth and current_user.profile and current_user.profile.id == profile.id:
        return True
    if profile.status != "approved":
        return False
    if profile.profile_visibility == "public":
        return True
    if profile.profile_visibility == "platoon" and is_platoon_member:
        return True
    return False


def serialize_contact(profile) -> dict:
    """Return only the contact fields the current viewer is allowed to see."""
    is_auth, is_platoon_member, is_admin = viewer_context()
    is_owner = is_auth and current_user.profile and current_user.profile.id == profile.id

    return {
        "phone_number": profile.visible_field("phone_number", is_platoon_member, is_owner, is_admin),
        "whatsapp_number": profile.visible_field("whatsapp_number", is_platoon_member, is_owner, is_admin),
        "address": profile.visible_field("address", is_platoon_member, is_owner, is_admin),
    }
