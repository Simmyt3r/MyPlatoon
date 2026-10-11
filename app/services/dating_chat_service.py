"""Mutual-consent, text-only private messaging for adult Dating personas.

Important: the server re-checks reciprocal active consent on every GET/POST.
A shared suggestion, one-sided like, stale notification or guessed URL is
never sufficient to view/send messages. Blocking and withdrawal revoke access.
"""
from sqlalchemy import or_

from app.extensions import db
from app.models import DatingInterest, DatingMessage, DatingMessageReport, DatingPersona
from app.services.dating_service import is_blocked
from app.services.notification_service import notify


def can_message(a: DatingPersona, b: DatingPersona) -> bool:
    if not a or not b or a.id == b.id:
        return False
    if not (a.is_active_and_visible() and b.is_active_and_visible()):
        return False
    if not a.is_compatible_with(b) or is_blocked(a.id, b.id):
        return False
    # Both sides must have individually expressed interest. No ranking
    # score, algorithmic overlap or cached boolean grants access.
    return (DatingInterest.query.filter_by(
        sender_id=a.id, recipient_id=b.id).first() is not None
        and DatingInterest.query.filter_by(
            sender_id=b.id, recipient_id=a.id).first() is not None)


def conversation_query(a_id: int, b_id: int):
    low, high = DatingMessage.pair(a_id, b_id)
    return DatingMessage.query.filter_by(
        persona_low_id=low, persona_high_id=high)


def send_text(sender: DatingPersona, recipient: DatingPersona, body: str):
    if not can_message(sender, recipient):
        raise PermissionError("A reciprocal, active connection is required.")
    content = (body or "").strip()
    if not content or len(content) > 1500:
        raise ValueError("Message must contain 1–1500 characters.")
    low, high = DatingMessage.pair(sender.id, recipient.id)
    message = DatingMessage(
        persona_low_id=low, persona_high_id=high,
        sender_id=sender.id, body=content,
    )
    db.session.add(message)
    db.session.commit()

    # Never include private chat text or member contact details in push or
    # in-app notifications. The recipient must open the authorised inbox.
    notify(recipient.profile.user,
           "You have a new private message in Dating from {}.".format(
               sender.display_name or "a connection"),
           category="info")
    return message


def received_message(message: DatingMessage, viewer_id: int) -> bool:
    """An abuse report is allowed after withdrawal/blocking if the message
    was actually sent to this persona. Authors may not report themselves.
    """
    return (viewer_id in (message.persona_low_id, message.persona_high_id)
            and message.sender_id != viewer_id)


def message_reports_for_admin(status="pending", limit=100):
    return (DatingMessageReport.query.filter_by(status=status)
            .order_by(DatingMessageReport.created_at.asc())
            .limit(min(max(limit, 1), 100)).all())


def purge_persona_chat(persona_id: int):
    """Remove report and message rows before deleting a Dating persona.

    Both sent and received messages are deleted on Dating persona deletion.
    Database ON DELETE CASCADE remains a second line of protection.
    """
    messages = DatingMessage.query.filter(or_(
        DatingMessage.persona_low_id == persona_id,
        DatingMessage.persona_high_id == persona_id,
    )).with_entities(DatingMessage.id).all()
    ids = [mid for (mid,) in messages]
    if ids:
        DatingMessageReport.query.filter(
            DatingMessageReport.message_id.in_(ids)
        ).delete(synchronize_session=False)
        DatingMessage.query.filter(
            DatingMessage.id.in_(ids)
        ).delete(synchronize_session=False)
    # Reports by this persona on other conversations shouldn't exist
    # without being a member of the pair, but clean defensively.
    DatingMessageReport.query.filter_by(
        reporter_id=persona_id).delete(synchronize_session=False)
