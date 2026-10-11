from flask import request

from app.extensions import db
from app.models import AuditLog


def log_action(user, action: str, target_type: str = None, target_id=None, detail: str = None):
    """Record an administrative or security-relevant action.

    Never include secrets (passwords, tokens) in `detail`.
    """
    entry = AuditLog(
        user_id=user.id if user and getattr(user, "id", None) else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id) if target_id is not None else None,
        detail=detail,
        ip_address=request.remote_addr if request else None,
    )
    db.session.add(entry)
    db.session.commit()
    return entry
