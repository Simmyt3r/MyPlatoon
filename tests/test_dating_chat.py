"""Private Dating chat: consent, access revocation, moderation and deletion."""
from datetime import datetime

from tests.conftest import _create_user, login
from app.extensions import db
from app.models import (
    DatingPersona, DatingInterest, DatingMessage, DatingMessageReport,
    DatingBlock, Notification, User,
)


def _adult(email, gender, seeking, name):
    user = _create_user(db, email, full_name=name)
    user.profile.status = "approved"
    db.session.commit()
    persona = DatingPersona(
        profile_id=user.profile.id, gender=gender, interested_in=seeking,
        display_name=name.split()[0], status="active",
        age_confirmed_at=datetime.utcnow(),
    )
    db.session.add(persona)
    db.session.commit()
    return user, persona


def _pair(connected=False):
    a, pa = _adult("chat-a@example.com", "male", "female", "Adam One")
    b, pb = _adult("chat-b@example.com", "female", "male", "Ada Two")
    if connected:
        db.session.add(DatingInterest(sender_id=pa.id, recipient_id=pb.id))
        db.session.add(DatingInterest(sender_id=pb.id, recipient_id=pa.id))
        db.session.commit()
    return a, pa, b, pb


def _send(client, persona_id, body):
    return client.post("/dating/messages/{}".format(persona_id),
                       data={"body": body}, follow_redirects=True)


def test_chat_requires_both_sides_to_opt_in(client):
    a, pa, b, pb = _pair()
    login(client, a.email)
    assert client.get("/dating/messages/{}".format(pb.id)).status_code == 404
    assert client.post("/dating/messages/{}".format(pb.id),
                       data={"body": "Hello"}).status_code == 404
    db.session.add(DatingInterest(sender_id=pa.id, recipient_id=pb.id))
    db.session.commit()
    assert client.get("/dating/messages/{}".format(pb.id)).status_code == 404
    assert DatingMessage.query.count() == 0


def test_mutual_interest_enables_private_two_way_text(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    r = _send(client, pb.id, "Hello, Ada.")
    assert r.status_code == 200
    assert DatingMessage.query.count() == 1
    assert DatingMessage.query.one().body == "Hello, Ada."
    # No private message text appears in the in-app notification.
    assert Notification.query.count() == 1
    assert "Hello, Ada" not in Notification.query.one().message
    assert "Hello, Ada." in r.get_data(as_text=True)
    client.get("/auth/logout")
    login(client, b.email)
    assert "Hello, Ada." in client.get(
        "/dating/messages/{}".format(pa.id)).get_data(as_text=True)
    r = _send(client, pa.id, "Nice to meet you.")
    assert r.status_code == 200
    assert DatingMessage.query.count() == 2


def test_stranger_cannot_read_guessable_conversation_or_report(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    _send(client, pb.id, "Our message must remain private.")
    message = DatingMessage.query.one()
    client.get("/auth/logout")
    c, pc = _adult("chat-c@example.com", "male", "female", "Visitor Three")
    login(client, c.email)
    assert client.get("/dating/messages/{}".format(pa.id)).status_code == 404
    assert client.post("/dating/messages/{}".format(pb.id),
                       data={"body": "No"}).status_code == 404
    assert client.get("/dating/messages/report/{}".format(message.id)).status_code == 404
    assert client.post("/dating/messages/report/{}".format(message.id),
                       data={"reason": "Trying to report other people's private text."}).status_code == 404


def test_withdrawal_revokes_chat_both_ways_but_retains_history(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    _send(client, pb.id, "Earlier text")
    assert DatingMessage.query.count() == 1
    client.post("/dating/interest/{}/withdraw".format(pb.id))
    assert client.get("/dating/messages/{}".format(pb.id)).status_code == 404
    client.get("/auth/logout")
    login(client, b.email)
    assert client.get("/dating/messages/{}".format(pa.id)).status_code == 404
    assert DatingMessage.query.count() == 1


def test_block_revokes_chat_both_ways_even_if_link_known(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    _send(client, pb.id, "Hi")
    client.post("/dating/block/{}".format(pb.id))
    assert DatingBlock.query.count() == 1
    assert client.get("/dating/messages/{}".format(pb.id)).status_code == 404
    client.get("/auth/logout")
    login(client, b.email)
    assert client.get("/dating/messages/{}".format(pa.id)).status_code == 404
    assert client.post("/dating/messages/{}".format(pa.id),
                       data={"body": "No access"}).status_code == 404


def test_empty_and_overlong_messages_are_not_saved(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    assert _send(client, pb.id, "  ").status_code == 200
    assert _send(client, pb.id, "Z" * 1501).status_code == 200
    assert DatingMessage.query.count() == 0


def test_html_is_displayed_as_text_not_markup(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    response = _send(client, pb.id, '<script>alert("x")</script>')
    html = response.get_data(as_text=True)
    assert '&lt;script&gt;' in html
    assert '<script>alert("x")</script>' not in html


def test_only_recipient_can_report_and_only_once(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    _send(client, pb.id, "Inappropriate message")
    msg = DatingMessage.query.one()
    assert client.get("/dating/messages/report/{}".format(msg.id)).status_code == 404
    client.get("/auth/logout")
    login(client, b.email)
    assert client.get("/dating/messages/report/{}".format(msg.id)).status_code == 200
    assert client.post("/dating/messages/report/{}".format(msg.id),
                       data={"reason": "This text makes me feel unsafe."}).status_code == 302
    report = DatingMessageReport.query.one()
    assert report.reporter_id == pb.id
    assert report.message_id == msg.id
    assert report.status == "pending"
    client.post("/dating/messages/report/{}".format(msg.id),
                data={"reason": "Again, duplicate"})
    assert DatingMessageReport.query.count() == 1


def test_recipient_may_report_after_connection_is_withdrawn_or_blocked(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    _send(client, pb.id, "Evidence")
    msg = DatingMessage.query.one()
    client.get("/auth/logout")
    login(client, b.email)
    client.post("/dating/block/{}".format(pa.id))
    assert client.get("/dating/messages/{}".format(pa.id)).status_code == 404
    assert client.post("/dating/messages/report/{}".format(msg.id),
                       data={"reason": "Evidence of abusive behaviour."}).status_code == 302
    assert DatingMessageReport.query.count() == 1


def test_admin_can_moderate_report_without_exposing_thread(client):
    a, pa, b, pb = _pair(connected=True)
    admin = _create_user(db, "chat-admin@example.com", role="admin")
    login(client, a.email)
    _send(client, pb.id, "Unwelcome conversation")
    msg = DatingMessage.query.one()
    client.get("/auth/logout")
    login(client, b.email)
    client.post("/dating/messages/report/{}".format(msg.id),
                data={"reason": "Please remove this inappropriate message."})
    assert client.get("/dating/moderation/messages").status_code == 403
    client.get("/auth/logout")
    login(client, admin.email)
    page = client.get("/dating/moderation/messages")
    assert page.status_code == 200
    assert "Please remove this" in page.get_data(as_text=True)
    assert client.post("/dating/moderation/messages/{}/review".format(
        DatingMessageReport.query.one().id), data={"decision": "removed"}).status_code == 302
    assert DatingMessage.query.one().is_removed is True
    assert DatingMessageReport.query.one().status == "removed"
    client.get("/auth/logout")
    login(client, b.email)
    html = client.get("/dating/messages/{}".format(pa.id)).get_data(as_text=True)
    assert "This message was removed by a moderator" in html
    assert "Unwelcome conversation" not in html


def test_delete_persona_removes_messages_and_reports(client):
    a, pa, b, pb = _pair(connected=True)
    login(client, a.email)
    _send(client, pb.id, "Delete me with Dating")
    msg = DatingMessage.query.one()
    client.get("/auth/logout")
    login(client, b.email)
    client.post("/dating/messages/report/{}".format(msg.id),
                data={"reason": "Message should be deleted later."})
    assert DatingMessageReport.query.count() == 1
    client.get("/auth/logout")
    login(client, a.email)
    assert client.post("/dating/delete").status_code == 302
    assert DatingMessage.query.count() == 0
    assert DatingMessageReport.query.count() == 0
    assert User.query.get(a.id) is not None
