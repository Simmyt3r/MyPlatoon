"""Gig workspace phase 2: private notes, revisions and two-party termination."""
from tests.conftest import _create_user, login
from tests.test_gig_deals import setup_gig, send_offer, accept, complete, switch
from app.models import (
    GigDeal, GigDispute, GigWorkUpdate, GigTerminationRequest,
    JobApplication, Notification,
)

GOOD_REASON = "The schedule has changed and we should agree to end the current gig."


def start(client, db):
    owner, org, job, worker, app = setup_gig(db)
    deal = send_offer(client, owner, app)
    accept(client, worker, deal)
    assert deal.status == "active"
    return owner, org, job, worker, app, deal


def request_termination(client, deal, reason=GOOD_REASON):
    return client.post(
        "/jobs/deals/{}/termination".format(deal.id),
        data={"reason": reason})


def respond_termination(client, deal, request, action):
    return client.post(
        "/jobs/deals/{}/termination/{}/respond".format(deal.id, request.id),
        data={"decision": action})


def test_work_notes_require_accepted_gig_and_keep_notes_private(client, db):
    owner, org, job, worker, app = setup_gig(db)
    deal = send_offer(client, owner, app)
    assert client.post(f"/jobs/deals/{deal.id}/updates",
                       data={"body": "Can we start at ten?"}).status_code == 409
    accept(client, worker, deal)
    note_text = "The draft is ready <script>alert('secret')</script>"
    assert client.post(f"/jobs/deals/{deal.id}/updates",
                       data={"body": note_text}).status_code == 302
    record = GigWorkUpdate.query.one()
    assert record.author_id == worker.id and record.kind == "message"
    assert record.body == note_text
    text = client.get(f"/jobs/deals/{deal.id}").get_data(as_text=True)
    assert "&lt;script&gt;" in text
    assert "<script>alert" not in text
    assert "Private work updates" in text
    assert note_text not in client.get(f"/jobs/{job.id}").get_data(as_text=True)
    stranger = _create_user(db, "not-on-this-work@example.com")
    switch(client, stranger)
    assert client.get(f"/jobs/deals/{deal.id}").status_code == 403
    assert client.post(f"/jobs/deals/{deal.id}/updates",
                       data={"body": "I'm changing your terms."}).status_code == 403


def test_work_updates_validate_length_and_notify_only_counterparty(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    assert client.post(f"/jobs/deals/{deal.id}/updates", data={"body": "  "}).status_code == 400
    assert client.post(f"/jobs/deals/{deal.id}/updates",
                       data={"body": "x" * 1201}).status_code == 400
    assert GigWorkUpdate.query.count() == 0
    assert client.post(f"/jobs/deals/{deal.id}/updates",
                       data={"body": "Progress report submitted."}).status_code == 302
    assert GigWorkUpdate.query.count() == 1
    assert Notification.query.filter_by(user_id=owner.id).count() >= 2


def test_revision_only_original_employer_after_worker_requests_completion(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    amount, scope, schedule = deal.pay_amount, deal.scope, deal.schedule
    assert client.post(f"/jobs/deals/{deal.id}/revision",
                       data={"reason": "Please correct the second mathematics lesson."}).status_code == 403
    assert client.post(f"/jobs/deals/{deal.id}/finish").status_code == 302
    assert deal.status == "completion_requested"
    switch(client, owner)
    assert client.post(f"/jobs/deals/{deal.id}/revision",
                       data={"reason": "Too short"}).status_code == 400
    assert client.post(f"/jobs/deals/{deal.id}/revision", data={
        "reason": "The agreed second lesson has not been delivered. Please finish it."
    }).status_code == 302
    assert deal.status == "active"
    assert (deal.pay_amount, deal.scope, deal.schedule) == (amount, scope, schedule)
    note = GigWorkUpdate.query.filter_by(kind="revision_requested").one()
    assert "second lesson" in note.body
    assert client.post(f"/jobs/deals/{deal.id}/revision",
                       data={"reason": "Please deliver the second lesson again."}).status_code == 409
    switch(client, worker)
    assert "second lesson" in client.get(f"/jobs/deals/{deal.id}").get_data(as_text=True)
    assert client.post(f"/jobs/deals/{deal.id}/finish").status_code == 302
    switch(client, owner)
    assert client.post(f"/jobs/deals/{deal.id}/confirm").status_code == 302
    assert deal.status == "completed"
    assert GigWorkUpdate.query.count() == 1


def test_mutual_termination_requires_second_person_explicitly_accept(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    assert request_termination(client, deal).status_code == 302
    request = GigTerminationRequest.query.one()
    assert deal.status == "active" and request.status == "pending"
    assert "The gig is still active." in client.get(
        f"/jobs/deals/{deal.id}").get_data(as_text=True)
    assert respond_termination(client, deal, request, "accept").status_code == 403
    switch(client, owner)
    assert respond_termination(client, deal, request, "accept").status_code == 302
    assert deal.status == "cancelled"
    assert deal.closed_at is not None
    assert request.status == "accepted"
    assert app.status == "hired"  # historic consent, not an ongoing contract
    assert deal.payment_status == "not_reported"
    assert client.post(f"/jobs/deals/{deal.id}/confirm").status_code == 409
    assert client.post(f"/jobs/deals/{deal.id}/review",
                       data={"stars": "5"}).status_code == 409
    assert client.post(f"/jobs/deals/{deal.id}/updates",
                       data={"body": "Trying to write after closure."}).status_code == 409
    assert "Cancellation history" in client.get(
        f"/jobs/deals/{deal.id}").get_data(as_text=True)


def test_requester_can_withdraw_but_other_person_can_decline(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    assert request_termination(client, deal).status_code == 302
    first = GigTerminationRequest.query.one()
    assert request_termination(client, deal).status_code == 409
    assert client.post(
        f"/jobs/deals/{deal.id}/termination/{first.id}/withdraw").status_code == 302
    assert first.status == "withdrawn"
    assert deal.status == "active"
    assert request_termination(client, deal).status_code == 302
    second = GigTerminationRequest.query.filter_by(status="pending").one()
    switch(client, owner)
    assert client.post(f"/jobs/deals/{deal.id}/termination/{second.id}/withdraw").status_code == 403
    assert respond_termination(client, deal, second, "decline").status_code == 302
    assert second.status == "declined" and deal.status == "active"
    assert respond_termination(client, deal, second, "accept").status_code == 409
    assert request_termination(client, deal).status_code == 302
    assert GigTerminationRequest.query.count() == 3


def test_pending_termination_blocks_completion_and_revision(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    request_termination(client, deal)
    assert client.post(f"/jobs/deals/{deal.id}/finish").status_code == 409
    proposed = GigTerminationRequest.query.one()
    switch(client, owner)
    assert respond_termination(client, deal, proposed, "decline").status_code == 302
    switch(client, worker)
    assert client.post(f"/jobs/deals/{deal.id}/finish").status_code == 302
    switch(client, owner)
    assert request_termination(client, deal).status_code == 302
    assert client.post(f"/jobs/deals/{deal.id}/confirm").status_code == 409
    assert client.post(f"/jobs/deals/{deal.id}/revision", data={
        "reason": "The original deliverable is missing two required pages."
    }).status_code == 409


def test_opening_confidential_dispute_supersedes_cancel_proposal(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    client.post(f"/jobs/deals/{deal.id}/updates", data={
        "body": "I have already provided the initial draft and lesson notes."})
    assert request_termination(client, deal).status_code == 302
    pending = GigTerminationRequest.query.one()
    complaint = "I was asked for a secret advance fee not mentioned in our gig agreement."
    assert client.post(f"/jobs/deals/{deal.id}/dispute",
                       data={"reason": complaint}).status_code == 302
    assert deal.status == "disputed"
    assert pending.status == "superseded"
    switch(client, owner)
    assert complaint not in client.get(
        f"/jobs/deals/{deal.id}").get_data(as_text=True)
    assert respond_termination(client, deal, pending, "accept").status_code == 409
    admin = _create_user(db, "journal-moderator@example.com", role="admin")
    switch(client, admin)
    review = client.get("/jobs/deals/admin/disputes").get_data(as_text=True)
    assert complaint in review
    assert "initial draft and lesson notes" in review
    assert "Private work updates (moderator review only)" in review


def test_proposal_cannot_start_before_acceptance_or_after_completion(client, db):
    owner, org, job, worker, app = setup_gig(db)
    deal = send_offer(client, owner, app)
    assert request_termination(client, deal).status_code == 409
    accept(client, worker, deal)
    client.post(f"/jobs/deals/{deal.id}/finish")
    switch(client, owner)
    client.post(f"/jobs/deals/{deal.id}/confirm")
    assert request_termination(client, deal).status_code == 409
    assert GigTerminationRequest.query.count() == 0


def test_stranger_cannot_open_or_respond_to_other_people_termination(client, db):
    owner, org, job, worker, app, deal = start(client, db)
    request_termination(client, deal)
    pending = GigTerminationRequest.query.one()
    stranger = _create_user(db, "another-worker@example.com")
    switch(client, stranger)
    assert request_termination(client, deal).status_code == 403
    assert respond_termination(client, deal, pending, "accept").status_code == 403
    assert client.post(f"/jobs/deals/{deal.id}/termination/{pending.id}/withdraw").status_code == 403
    assert pending.status == "pending"


def test_mutual_cancellation_is_not_a_fake_completed_gig(client, db):
    from app.services.gig_reputation import employer_reputation
    owner, org, job, worker, app, deal = start(client, db)
    request_termination(client, deal)
    pending = GigTerminationRequest.query.one()
    switch(client, owner)
    respond_termination(client, deal, pending, "accept")
    stats = employer_reputation(org)
    assert stats["completed_gigs"] == 0
    assert stats["public_reviews"] == 0
    assert stats["score"] is None
