"""Access checks for a national platform with distinct camp platoons.

Platoon-only content is for approved members of exactly the SAME orientation
platoon, not everybody with an NYSC account. PCMs without an assigned platoon
have no platoon privileges.
"""
from flask_login import current_user


def viewer_context(target_profile=None):
    """Return (authenticated, same_platoon_as_target, is_admin)."""
    if not current_user.is_authenticated:
        return False, False, False

    if current_user.is_admin:
        return True, True, True

    viewer = current_user.profile
    same = bool(
        target_profile is not None
        and viewer is not None
        and viewer.status == "approved"
        and viewer.platoon_id is not None
        and target_profile.platoon_id is not None
        and viewer.platoon_id == target_profile.platoon_id
    )
    return True, same, False


def can_view_full_profile(profile):
    """Owner/admin may view; others need an approved public or same-platoon profile."""
    is_auth, same_platoon, is_admin = viewer_context(profile)
    if is_admin:
        return True
    if is_auth and current_user.profile and current_user.profile.id == profile.id:
        return True
    if profile.status != "approved":
        return False
    return (profile.profile_visibility == "public"
            or (profile.profile_visibility == "platoon" and same_platoon))


def serialize_contact(profile):
    """Only show contacts for the target's genuinely permitted viewer."""
    is_auth, same_platoon, is_admin = viewer_context(profile)
    owner = bool(is_auth and current_user.profile and current_user.profile.id == profile.id)
    return {
        "phone_number": profile.visible_field("phone_number", same_platoon, owner, is_admin),
        "whatsapp_number": profile.visible_field("whatsapp_number", same_platoon, owner, is_admin),
        "address": profile.visible_field("address", same_platoon, owner, is_admin),
    }
