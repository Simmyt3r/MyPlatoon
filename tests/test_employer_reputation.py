"""Opt-in, moderated employer reputation regression tests."""
from datetime import datetime
from tests.conftest import _create_user, login
from tests.test_gig_deals import setup_gig, switch
from tests.test_jobs import prepare_job, approve_serving
from app.extensions import db
from app.models import JobApplication, GigDeal, GigReview, GigDispute
from app.services.gig_reputation import employer_reputation


def finished(db, org, job, worker, application, stars=None, public=False, reviewed=False,
             status="completed", receipt=False):
    deal = GigDeal(application_id=application.id, employer_id=org.id, worker_id=worker.id,
        scope="Weekend mathematics tutoring", schedule="Saturday", pay_amount=12000,
        pay_unit="week", status=status, accepted_at=datetime.utcnow(),
        completed_at=datetime.utcnow() if status=="completed" else None,
        payment_status="confirmed_paid" if receipt else "not_reported")
    application.status="hired"
    db.session.add(deal)
    db.session.flush()
    if stars:
        db.session.add(GigReview(deal_id=deal.id, reviewer_id=worker.id, role="worker",
            stars=stars, comment="Very good experience.", public_consent=public,
            moderation_status="approved" if reviewed else "private"))
    db.session.commit()
    return deal


def new_worker(db, job, n):
    worker = _create_user(db, f"reputation-worker-{n}@example.com", full_name=f"Worker {n}")
    approve_serving(db, worker)
    application = JobApplication(job_id=job.id, applicant_user_id=worker.id,
        cover_note="Available to handle the gig safely.", contact_email=f"private-{n}@example.com")
    db.session.add(application)
    db.session.commit()
    return worker, application


def three_finished(db):
    owner, org, job, first, application = setup_gig(db)
    a=finished(db,org,job,first,application,stars=5,public=True,reviewed=True,receipt=True)
    second, ap2=new_worker(db,job,2)
    b=finished(db,org,job,second,ap2,stars=4,public=True,reviewed=True)
    third, ap3=new_worker(db,job,3)
    c=finished(db,org,job,third,ap3)
    return owner,org,job,[(first,a),(second,b),(third,c)]


def test_public_history_is_conditional_on_employer_approval(client, db):
    owner,org,job,worker,application=setup_gig(db)
    assert client.get(f"/jobs/employers/{org.id}/reputation").status_code==200
    org.status="pending";db.session.commit()
    assert client.get(f"/jobs/employers/{org.id}/reputation").status_code==404
    org.status="approved";owner.is_suspended=True;db.session.commit()
    assert client.get(f"/jobs/employers/{org.id}/reputation").status_code==404


def test_reputation_requires_three_distinct_workers_and_two_public_approved_reviews(client,db):
    owner,org,job,worker,application=setup_gig(db)
    finished(db,org,job,worker,application,stars=5,public=True,reviewed=True)
    assert employer_reputation(org)["score"] is None
    w2,a2=new_worker(db,job,2)
    finished(db,org,job,w2,a2,stars=4,public=True,reviewed=True)
    assert employer_reputation(org)["qualified"] is False
    w3,a3=new_worker(db,job,3)
    finished(db,org,job,w3,a3)
    stats=employer_reputation(org)
    assert stats["qualified"] and stats["score"]==3.8 and stats["public_reviews"]==2
    assert stats["unique_workers"]==3


def test_private_and_unmoderated_ratings_never_count(client, db):
    owner,org,job,worker,application=setup_gig(db)
    finished(db,org,job,worker,application,stars=5)
    w2,a2=new_worker(db,job,2)
    finished(db,org,job,w2,a2,stars=5,public=True)
    w3,a3=new_worker(db,job,3); finished(db,org,job,w3,a3)
    assert employer_reputation(org)["public_reviews"]==0
    assert "Reputation developing" in client.get(
        f"/jobs/employers/{org.id}/reputation").get_data(as_text=True)


def test_public_profile_has_no_private_contact_or_worker_identity(client,db):
    owner,org,job,workers=three_finished(db)
    org.address="SENSITIVE-OFFICE-ADDRESS"
    org.contact_phone="SENSITIVE-PHONE"
    org.contact_email="private-employer@example.com"
    db.session.commit()
    text=client.get(f"/jobs/employers/{org.id}/reputation").get_data(as_text=True)
    assert "3.8/5" in text and "Anonymous completed-gig review" in text
    assert "not bank verified" in text and "Worker-confirmed receipts" in text
    for secret in ("SENSITIVE-OFFICE-ADDRESS","SENSITIVE-PHONE",
                   "private-employer@example.com","private-2@example.com",
                   "Worker 2", "reputation-worker-2"):
        assert secret not in text
    assert f"/jobs/employers/{org.id}/reputation" in client.get(
        f"/jobs/{job.id}").get_data(as_text=True)


def test_worker_review_opt_in_admin_approves_and_worker_can_revoke(client,db):
    owner,org,job,worker,application=setup_gig(db)
    deal=finished(db,org,job,worker,application)
    login(client,worker.email)
    assert client.post(f"/jobs/deals/{deal.id}/review",data={
        "stars":"5","public_consent":"yes","comment":"Good and prompt support."}).status_code==302
    rating=GigReview.query.one()
    assert rating.public_consent and rating.moderation_status=="pending"
    admin=_create_user(db,"review-moderator@example.com",role="admin")
    switch(client,admin)
    assert "Good and prompt support" in client.get(
        "/jobs/deals/admin/reviews").get_data(as_text=True)
    assert client.post(f"/jobs/deals/admin/reviews/{rating.id}",data={
        "decision":"approved"}).status_code==302
    assert rating.moderation_status=="approved"
    switch(client,worker)
    assert client.post(f"/jobs/deals/{deal.id}/review/withdraw").status_code==302
    assert rating.moderation_status=="private" and not rating.public_consent
    switch(client,admin)
    assert client.post(f"/jobs/deals/admin/reviews/{rating.id}",data={
        "decision":"approved"}).status_code==409


def test_existing_private_review_requires_fresh_explicit_consent(client,db):
    owner,org,job,worker,application=setup_gig(db)
    deal=finished(db,org,job,worker,application)
    login(client,worker.email)
    client.post(f"/jobs/deals/{deal.id}/review", data={"stars":"4"})
    rating=GigReview.query.one()
    assert not rating.public_consent and rating.moderation_status=="private"
    assert client.post(f"/jobs/deals/{deal.id}/review/publish").status_code==400
    assert client.post(f"/jobs/deals/{deal.id}/review/publish",data={
        "public_consent":"yes"}).status_code==302
    assert rating.public_consent and rating.moderation_status=="pending"


def test_employer_reviews_of_workers_cannot_be_published(client,db):
    owner,org,job,worker,application=setup_gig(db)
    deal=finished(db,org,job,worker,application)
    login(client,owner.email)
    client.post(f"/jobs/deals/{deal.id}/review",data={"stars":"1","public_consent":"yes"})
    rating=GigReview.query.one()
    assert not rating.public_consent and rating.moderation_status=="private"
    assert client.post(f"/jobs/deals/{deal.id}/review/publish",data={
        "public_consent":"yes"}).status_code==403
    rating.public_consent=True; rating.moderation_status="pending";db.session.commit()
    admin=_create_user(db,"mod-employer@example.com",role="admin")
    switch(client,admin)
    assert client.post(f"/jobs/deals/admin/reviews/{rating.id}",data={
        "decision":"approved"}).status_code==409


def test_admin_can_revoke_approved_and_audit_rejection(client,db):
    owner,org,job,workers=three_finished(db)
    rating=GigReview.query.filter_by(reviewer_id=workers[0][0].id).one()
    admin=_create_user(db,"mod-revoke@example.com",role="admin")
    login(client,admin.email)
    assert client.get("/jobs/deals/admin/reviews?status=approved").status_code==200
    assert client.post(f"/jobs/deals/admin/reviews/{rating.id}",data={
        "decision":"rejected","note":"short"}).status_code==400
    assert client.post(f"/jobs/deals/admin/reviews/{rating.id}",data={
        "decision":"rejected","note":"Text contains personal contact details."}).status_code==302
    assert employer_reputation(org)["qualified"] is False


def test_repeat_worker_gigs_count_one_star_vote(client,db):
    owner,org,job,worker,application=setup_gig(db)
    finished(db,org,job,worker,application,stars=5,public=True,reviewed=True)
    extra=prepare_job(db,org,title="Different weekend teaching task",job_kind="gig")
    a=JobApplication(job_id=extra.id,applicant_user_id=worker.id,
        cover_note="Returning gig worker",contact_email="private@example.com")
    db.session.add(a);db.session.commit()
    finished(db,org,extra,worker,a,stars=1,public=True,reviewed=True)
    w2,a2=new_worker(db,job,2);finished(db,org,job,w2,a2,stars=4,public=True,reviewed=True)
    w3,a3=new_worker(db,job,3);finished(db,org,job,w3,a3)
    stats=employer_reputation(org)
    assert stats["completed_gigs"]==4
    assert stats["unique_workers"]==3 and stats["public_reviews"]==2


def test_dispute_removes_public_rating_and_requires_moderator_reapproval(client,db):
    owner,org,job,workers=three_finished(db)
    worker,deal=workers[0]
    assert employer_reputation(org)["qualified"]
    switch(client,worker)
    assert client.post(f"/jobs/deals/{deal.id}/dispute",data={
        "reason":"My employer changed the agreed work terms and has not paid."}).status_code==302
    assert deal.status=="disputed"
    review=GigReview.query.filter_by(deal_id=deal.id).one()
    assert review.moderation_status=="pending"
    assert not employer_reputation(org)["qualified"]


def test_no_review_approval_for_unfinished_work_or_unrelated_user(client,db):
    owner,org,job,worker,application=setup_gig(db)
    deal=finished(db,org,job,worker,application,stars=5,public=True,status="active")
    review=GigReview.query.one();review.moderation_status="pending";db.session.commit()
    stranger=_create_user(db,"random-viewer@example.com")
    login(client,stranger.email)
    assert client.post(f"/jobs/deals/{deal.id}/review/publish",data={
        "public_consent":"yes"}).status_code==403
    assert client.get("/jobs/deals/admin/reviews").status_code==403
    admin=_create_user(db,"mod-incomplete@example.com",role="admin");switch(client,admin)
    assert client.post(f"/jobs/deals/admin/reviews/{review.id}",data={
        "decision":"approved"}).status_code==409
