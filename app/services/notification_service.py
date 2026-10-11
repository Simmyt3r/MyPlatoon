from app.extensions import db
from app.models import Notification


def notify(user, message: str, category: str = "info"):
    """Create an in-app notification for a user.

    Email notifications are an optional future enhancement (see README);
    this keeps the write path simple and dependency-free.
    """
    if user is None:
        return None
    note = Notification(user_id=user.id, message=message, category=category)
    db.session.add(note)
    db.session.commit()
    return note


def unread_count(user) -> int:
    if user is None or not getattr(user, "is_authenticated", False):
        return 0
    return Notification.query.filter_by(user_id=user.id, is_read=False).count()
