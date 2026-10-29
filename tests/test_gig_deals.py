"""Gig hiring: consent, state transitions, private payments, disputes and rating gates."""
from tests.conftest import _create_user, login
from tests.test_jobs import prepare_org, prepare_job, approve_serving
from app.models import (
    GigDeal, GigDispute, GigReview, JobApplication, Notification,
)

OFFER = {
    "scope": "Teach two sessions of junior secondary school mathematics and submit lesson notes.",
    "schedule": "Saturdays 9 AM to 3 PM",
    "pay_amount": "12000",
}


def setup_gig(db):
    employer, org = prepare_org(db)
    job = prepare_job(db, org, job_kind="gig", pay_min=10000, pay_max=20000)
    worker = _create_user(db, "gig-worker@example.com", full_name="Gig Worker")
    approve_serving(db, worker)
    applicant = JobApplication(
        job_id=job.id, applicant_user_id=worker.id,
        cover_note="I have experience tutoring secondary school students.",
        contact_email="worker-contact@example.com")
    db.session.add(applicant)
    db.session.commit()
    return employer, org, job, worker, applicant


def send_offer(client, employer, application):
    login(client, employer.email)
    result = client.post("/jobs/deals/offer/{}".format(application.id), data=OFFER)
    assert result.status_code == 302
    deal = GigDeal.query.one()
    return deal


def switch(client, account):
    client.post("/auth/logout")
    login(client, account.email)


def accept(client, worker, deal):
    switch(client, worker)
    r = client.post("/jobs/deals/{}/respond".format(deal.id),
                    data={"decision": "accept", "accept_terms": "yes"})
    assert r.status_code == 302


def complete(client, employer, worker, deal):
    accept(client, worker, deal)
    assert client.post("/jobs/deals/{}/finish".format(deal.id)).status_code == 302
    switch(client, employer)
    assert client.post("/jobs/deals/{}/confirm".format(deal.id)).status_code == 302


def test_employer_offers_terms_inside_advertised_pay_range(client, db):
    employer, _, job, worker, app = setup_gig(db)
    login(client, employer.email)
    r = client.get("/jobs/deals/offer/{}".format(app.id))
    assert r.status_code == 200
    assert b"Send a work offer" in r.data
    assert client.post("/jobs/deals/offer/{}".format(app.id),
                       data={**OFFER, "pay_amount": "1000"}).status_code == 200
    assert GigDeal.query.count() == 0
    r = client.post("/jobs/deals/offer/{}".format(app.id), data=OFFER)
    assert r.status_code == 302
    deal = GigDeal.query.one()
    assert deal.status == "offered"
    assert deal.pay_amount == 12000
    assert deal.pay_unit == job.pay_unit
    assert app.status == "submitted"
    assert Notification.query.filter_by(user_id=worker.id).count() == 1
    assert b"Send formal work offer" not in client.get("/jobs/{}/applications".format(job.id)).data
    assert b"View gig agreement" in client.get("/jobs/{}/applications".format(job.id)).data


def test_no_unilateral_hiring_through_legacy_dropdown(client, db):
    employer, _, job, worker, application = setup_gig(db)
    login(client, employer.email)
    client.post("/jobs/applications/{}/status".format(application.id),
                data={"status": "hired"})
    assert application.status == "submitted"
    deal = send_offer(client, employer, application)
    assert client.post("/jobs/applications/{}/status".format(application.id),
                       data={"status": "declined"}).status_code == 409
    assert deal.status == "offered"


def test_worker_must_explicitly_accept_and_only_once(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    switch(client, worker)
    assert client.get("/jobs/deals/{}".format(deal.id)).status_code == 200
    assert client.post("/jobs/deals/{}/respond".format(deal.id),
                       data={"decision": "accept"}).status_code == 400
    assert deal.status == "offered"
    assert client.post("/jobs/deals/{}/respond".format(deal.id),
                       data={"decision": "accept", "accept_terms": "yes"}).status_code == 302
    assert deal.status == "active"
    assert application.status == "hired"
    assert client.post("/jobs/deals/{}/respond".format(deal.id),
                       data={"decision": "accept", "accept_terms": "yes"}).status_code == 409


def test_worker_can_decline_owner_can_cancel_only_unaccepted(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    switch(client, worker)
    assert client.post("/jobs/deals/{}/respond".format(deal.id),
                       data={"decision": "decline"}).status_code == 302
    assert deal.status == "declined"
    switch(client, employer)
    assert client.post("/jobs/deals/{}/cancel".format(deal.id)).status_code == 409


def test_employer_can_withdraw_pending_offer_but_not_accepted_gig(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    assert client.post("/jobs/deals/{}/cancel".format(deal.id)).status_code == 302
    assert deal.status == "cancelled"
    assert client.post("/jobs/deals/{}/cancel".format(deal.id)).status_code == 409


def test_only_worker_requests_completion_employer_must_confirm(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    assert client.post("/jobs/deals/{}/finish".format(deal.id)).status_code == 403
    assert client.post("/jobs/deals/{}/confirm".format(deal.id)).status_code == 409
    accept(client, worker, deal)
    assert client.post("/jobs/deals/{}/confirm".format(deal.id)).status_code == 403
    assert client.post("/jobs/deals/{}/finish".format(deal.id)).status_code == 302
    assert deal.status == "completion_requested"
    assert client.post("/jobs/deals/{}/finish".format(deal.id)).status_code == 409
    switch(client, employer)
    assert client.post("/jobs/deals/{}/confirm".format(deal.id)).status_code == 302
    assert deal.status == "completed"
    assert deal.completed_at is not None


def test_payments_are_voluntary_record_not_automatic_transfer(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    complete(client, employer, worker, deal)
    assert deal.payment_status == "not_reported"
    assert client.post("/jobs/deals/{}/payment".format(deal.id),
                       data={"action": "confirm_receipt"}).status_code == 403
    assert client.post("/jobs/deals/{}/payment".format(deal.id),
                       data={"action": "report_paid"}).status_code == 302
    assert deal.payment_status == "reported_paid"
    assert client.post("/jobs/deals/{}/payment".format(deal.id),
                       data={"action": "report_paid"}).status_code == 409
    switch(client, worker)
    assert client.post("/jobs/deals/{}/payment".format(deal.id),
                       data={"action": "confirm_receipt"}).status_code == 302
    assert deal.payment_status == "confirmed_paid"


def test_unauthorized_member_cannot_read_or_change_private_deal(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    stranger = _create_user(db, "stranger@example.com")
    switch(client, stranger)
    assert client.get("/jobs/deals/{}".format(deal.id)).status_code == 403
    assert client.post("/jobs/deals/{}/respond".format(deal.id),
                       data={"decision": "accept", "accept_terms": "yes"}).status_code == 403
    assert client.post("/jobs/deals/{}/dispute".format(deal.id),
                       data={"reason": "I have been incorrectly charged for work."}).status_code == 403
    assert client.post("/jobs/deals/{}/review".format(deal.id),
                       data={"stars": "5"}).status_code == 403
    assert "Weekend mathematics tutor" not in client.get("/jobs/deals/").get_data(as_text=True)


def test_employer_cannot_offer_on_someone_elses_application(client, db):
    employer, _, job, worker, application = setup_gig(db)
    stranger, other_org = prepare_org(db, user=_create_user(db, "strange-org@example.com", role="employer"))
    login(client, stranger.email)
    assert client.post("/jobs/deals/offer/{}".format(application.id),
                       data=OFFER).status_code == 403
    assert GigDeal.query.count() == 0


def test_published_job_and_verified_employer_required_for_offer(client, db):
    employer, organisation, job, worker, application = setup_gig(db)
    organisation.status = "pending"
    db.session.commit()
    login(client, employer.email)
    assert client.get("/jobs/deals/offer/{}".format(application.id)).status_code == 403
    organisation.status = "approved"
    job.status = "pending"
    db.session.commit()
    assert client.post("/jobs/deals/offer/{}".format(application.id),
                       data=OFFER).status_code == 409
    assert GigDeal.query.count() == 0


def test_member_can_dispute_and_only_admin_sees_report(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    accept(client, worker, deal)
    reason = "The employer demanded a processing fee and changed the working location."
    assert client.post("/jobs/deals/{}/dispute".format(deal.id),
                       data={"reason": reason}).status_code == 302
    assert deal.status == "disputed"
    assert GigDispute.query.count() == 1
    # The counterpart must never see the confidential reason.
    switch(client, employer)
    page = client.get("/jobs/deals/{}".format(deal.id)).get_data(as_text=True)
    assert reason not in page
    assert client.get("/jobs/deals/admin/disputes").status_code == 403
    assert client.post("/jobs/deals/{}/confirm".format(deal.id)).status_code == 409
    admin = _create_user(db, "moderator@example.com", role="admin")
    switch(client, admin)
    assert reason in client.get("/jobs/deals/admin/disputes").get_data(as_text=True)
    report = GigDispute.query.one()
    assert client.post("/jobs/deals/admin/disputes/{}".format(report.id),
                       data={"action": "resume", "resolution": "Members were contacted and agreed to resume the work."}).status_code == 302
    assert deal.status == "active"
    assert report.status == "resolved"
    switch(client, worker)
    personal_workspace = client.get("/jobs/deals/{}".format(deal.id)).get_data(as_text=True)
    assert "Members were contacted and agreed to resume the work." in personal_workspace
    assert reason not in personal_workspace


def test_admin_cannot_mark_dispute_as_completed_or_paid(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    accept(client, worker, deal)
    client.post("/jobs/deals/{}/dispute".format(deal.id),
                data={"reason": "This job no longer matches the original conditions."})
    moderator = _create_user(db, "moderator@example.com", role="admin")
    switch(client, moderator)
    report = GigDispute.query.one()
    assert client.post("/jobs/deals/admin/disputes/{}".format(report.id),
                       data={"action": "completed", "resolution": "Mark the gig finished without worker consent."}).status_code == 400
    assert deal.status == "disputed"


def test_reviews_require_completed_gig_one_per_party(client, db):
    employer, _, job, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    switch(client, worker)
    assert client.post("/jobs/deals/{}/review".format(deal.id),
                       data={"stars": "5"}).status_code == 409
    complete(client, employer, worker, deal)
    assert client.post("/jobs/deals/{}/review".format(deal.id),
                       data={"stars": "0"}).status_code == 400
    assert client.post("/jobs/deals/{}/review".format(deal.id),
                       data={"stars": "4", "comment": "Work was delivered correctly."}).status_code == 302
    assert client.post("/jobs/deals/{}/review".format(deal.id),
                       data={"stars": "5"}).status_code == 409
    switch(client, worker)
    assert client.post("/jobs/deals/{}/review".format(deal.id),
                       data={"stars": "5"}).status_code == 302
    assert GigReview.query.count() == 2


def test_non_gig_applications_cannot_enter_gig_workflow(client, db):
    employer, _, job, worker, application = setup_gig(db)
    job.job_kind = "full_time"
    db.session.commit()
    login(client, employer.email)
    assert client.get("/jobs/deals/offer/{}".format(application.id)).status_code == 400



def test_member_who_owns_an_employer_cannot_hire_self(client, db):
    member = _create_user(db, "self-deal-member@example.com", full_name="Owner Member")
    approve_serving(db, member)
    employer, org = prepare_org(db, user=member)
    job = prepare_job(db, org, job_kind="gig", pay_min=10000, pay_max=20000)
    login(client, member.email)
    assert client.get("/jobs/{}".format(job.id)).status_code == 200
    assert client.post("/jobs/{}/apply".format(job.id), data={
        "cover_note": "I want to apply to my own gig for a fraudulent reputation boost.",
        "contact_email": member.email,
        "consent": "y",
    }).status_code == 302
    assert JobApplication.query.count() == 0
    # Even a forged legacy application cannot create a valid self-deal.
    application = JobApplication(
        job_id=job.id, applicant_user_id=member.id,
        cover_note="Legacy manually inserted fraudulent self-application.",
        contact_email=member.email)
    db.session.add(application)
    db.session.commit()
    assert client.post("/jobs/deals/offer/{}".format(application.id),
                       data=OFFER).status_code == 403
    assert GigDeal.query.count() == 0


def test_acceptance_rechecks_serving_only_restriction(client, db):
    employer, _, job, worker, application = setup_gig(db)
    job.serving_only = True
    db.session.commit()
    deal = send_offer(client, employer, application)
    worker.profile.service_stage = "pcm"
    db.session.commit()
    switch(client, worker)
    assert client.post("/jobs/deals/{}/respond".format(deal.id),
                       data={"decision": "accept", "accept_terms": "yes"}).status_code == 409
    assert deal.status == "offered"
    assert application.status == "submitted"


def test_member_with_hiring_profile_sees_both_worker_and_employer_deals(client, db):
    employer, _, _, worker, application = setup_gig(db)
    deal = send_offer(client, employer, application)
    # Give worker an independent approved employer profile. They now
    # have both the right to work and the right to hire other people.
    second_owner, _org = prepare_org(db, user=worker)
    switch(client, worker)
    response = client.get("/jobs/deals/")
    assert response.status_code == 200
    assert b"Weekend mathematics tutor" in response.data
