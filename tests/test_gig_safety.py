"""Phase 3: confidential evidence, typed cases, downloads and audit regressions."""
from io import BytesIO

from tests.conftest import _create_user
from tests.test_gig_workspace import start
from tests.test_gig_deals import switch
from app.models import GigDispute, GigDisputeEvidence, GigDisputeEvent, GigDeal
from app.services.gig_reputation import employer_reputation


REASON = "I was promised payment for the delivered work but it was not received."
STATEMENT = "The employer has not supplied the agreed payment receipt or bank proof."
PNG = b"\x89PNG\r\n\x1a\n" + b"example-binary-evidence"


def report(client, deal, reason=REASON, category="nonpayment"):
    return client.post(f"/jobs/deals/{deal.id}/dispute",
                       data={"reason": reason, "category": category})


def evidence(client, case, *, description=STATEMENT,
             kind="payment_record", filename=None, data=None):
    payload = {"kind": kind, "description": description}
    if filename:
        payload["attachment"] = (BytesIO(data), filename)
    return client.post(f"/jobs/deals/case/{case.id}/evidence",
                       data=payload, content_type="multipart/form-data")


def test_dispute_submission_saves_category_and_redirects_to_private_case(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    result = report(client, deal)
    assert result.status_code == 302
    dispute = GigDispute.query.one()
    assert result.headers["Location"].endswith(
        f"/jobs/deals/case/{dispute.id}")
    assert dispute.status == "open"
    assert dispute.category == "nonpayment"
    assert dispute.outcome_code is None
    assert deal.status == "disputed"
    assert GigDisputeEvent.query.filter_by(
        dispute_id=dispute.id, kind="case_opened").count() == 1
    html = client.get(f"/jobs/deals/case/{dispute.id}").get_data(as_text=True)
    assert REASON in html
    assert "Evidence records" in html
    assert "Case timeline" in html


def test_case_details_hide_claim_from_respondent_but_allow_response(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    switch(client, owner)
    view = client.get(f"/jobs/deals/case/{case.id}")
    assert view.status_code == 200
    html = view.get_data(as_text=True)
    assert REASON not in html and "Report concern" not in html
    assert "may provide your own statement" in html
    assert evidence(client, case, description="I have confirmed the work and will check the payment records.").status_code == 302
    row = GigDisputeEvidence.query.one()
    assert row.submitted_by_id == owner.id
    assert row.attachment is None


def test_evidence_text_and_file_are_append_only_with_sha256_and_private_download(client, db):
    import hashlib
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    data = b"Signed delivery note in UTF-8\n"
    assert evidence(client, case, filename="note.txt", data=data).status_code == 302
    stored = GigDisputeEvidence.query.one()
    assert stored.kind == "payment_record"
    assert stored.filename == "note.txt"
    assert stored.content_type == "text/plain"
    assert stored.attachment == data
    assert stored.file_size == len(data)
    assert stored.sha256 == hashlib.sha256(data).hexdigest()
    url = f"/jobs/deals/case/{case.id}/attachment/{stored.id}"
    response = client.get(url)
    assert response.status_code == 200 and response.data == data
    assert response.headers["Cache-Control"] == "no-store, private"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["Content-Type"].startswith("application/octet-stream")
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert client.post(url, data={}).status_code == 405
    assert evidence(client, case,
                    description="A different supporting statement is also attached.",
                    kind="statement").status_code == 302
    assert GigDisputeEvidence.query.count() == 2


def test_counterparty_cannot_read_other_person_evidence_or_attachment(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    secret = "PRIVATE SOURCE SAID THIS IS THE EXACT FINAL REPORT."
    evidence(client, case, description=secret,
             filename="secret.txt", data=b"Private payment document")
    row = GigDisputeEvidence.query.one()
    switch(client, owner)
    case_html = client.get(f"/jobs/deals/case/{case.id}").get_data(as_text=True)
    assert secret not in case_html
    assert row.filename not in case_html
    assert client.get(f"/jobs/deals/case/{case.id}/attachment/{row.id}").status_code == 403
    stranger = _create_user(db, "safety-stranger@example.com")
    switch(client, stranger)
    assert client.get(f"/jobs/deals/case/{case.id}").status_code == 403
    assert evidence(client, case).status_code == 403
    assert client.get(f"/jobs/deals/case/{case.id}/attachment/{row.id}").status_code == 403


def test_admin_may_download_any_case_file_but_cannot_forge_evidence(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    evidence(client, case, filename="payment.txt", data=b"First hand statement")
    row = GigDisputeEvidence.query.one()
    admin = _create_user(db, "safety-case-admin@example.com", role="admin")
    switch(client, admin)
    assert client.get(f"/jobs/deals/case/{case.id}").status_code == 200
    assert client.get(f"/jobs/deals/case/{case.id}/attachment/{row.id}").data == b"First hand statement"
    assert evidence(client, case).status_code == 403
    assert GigDisputeEvidence.query.count() == 1


def test_invalid_file_extension_signature_and_empty_uploads_are_rejected(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    checks = [
        ("evil.svg", b"<svg onload='alert(1)'></svg>", 400),
        ("bad.pdf", b"not really a pdf", 400),
        ("bad.png", b"not really png", 400),
        ("bad.jpeg", b"not really jpeg", 400),
        ("binary.txt", b"some data\x00with null", 400),
        ("empty.pdf", b"", 413),
        ("huge.png", PNG + b"X" * (1024 * 1024), 413),
    ]
    for filename, payload, expected in checks:
        result = evidence(client, case, filename=filename, data=payload)
        assert result.status_code == expected, (filename, result.status_code)
    assert GigDisputeEvidence.query.count() == 0


def test_evidence_count_limit_is_enforced(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    for n in range(8):
        assert evidence(client, case, description=f"Supporting statement #{n}: the work was delivered.").status_code == 302
    assert GigDisputeEvidence.query.count() == 8
    assert evidence(client, case).status_code == 409


def test_invalid_case_category_is_rejected_without_creating_case(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    assert report(client, deal, category="forged_admin_priority").status_code == 400
    assert GigDispute.query.count() == 0
    assert deal.status == "active"


def test_admin_resolution_records_explicit_outcome_event_and_closes_evidence(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    evidence(client, case)
    moderator = _create_user(db, "case-review-admin@example.com", role="admin")
    switch(client, moderator)
    resolution = "The case was reviewed and the agreement will resume after clarification."
    result = client.post(f"/jobs/deals/admin/disputes/{case.id}", data={
        "action": "resume", "resolution": resolution})
    assert result.status_code == 302
    assert case.status == "resolved" and case.outcome_code == "resume"
    assert case.resolution == resolution and deal.status == "active"
    assert GigDisputeEvent.query.filter_by(
        dispute_id=case.id, kind="case_resolved").count() == 1
    assert resolution in client.get(
        f"/jobs/deals/case/{case.id}").get_data(as_text=True)
    switch(client, worker)
    assert evidence(client, case).status_code == 409
    assert GigDisputeEvidence.query.count() == 1
    assert resolution in client.get(
        f"/jobs/deals/case/{case.id}").get_data(as_text=True)


def test_admin_cancellation_does_not_forge_payment_or_completion(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal, category="safety")
    case = GigDispute.query.one()
    admin = _create_user(db, "case-resolver@example.com", role="admin")
    switch(client, admin)
    assert client.post(f"/jobs/deals/admin/disputes/{case.id}", data={
        "action": "cancel",
        "resolution": "The parties should not continue this gig due to the raised concerns."}).status_code == 302
    assert case.outcome_code == "cancel" and deal.status == "cancelled"
    assert deal.payment_status == "not_reported"
    assert deal.completed_at is None
    assert employer_reputation(org)["completed_gigs"] == 0


def test_public_jobs_and_reputation_never_expose_dispute_evidence(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    evidence(client, case, description="CONFIDENTIAL PAYMENT INFORMATION INSIDE THE CASE ONLY.")
    switch(client, owner)
    for route in (f"/jobs/{job.id}", f"/jobs/employers/{org.id}/reputation"):
        response = client.get(route)
        assert response.status_code == 200
        assert b"CONFIDENTIAL PAYMENT INFORMATION" not in response.data
    assert b"CONFIDENTIAL PAYMENT INFORMATION" not in client.get("/jobs/").data


def test_case_pages_and_admin_evidence_queue_are_never_cacheable(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    response = client.get(f"/jobs/deals/case/{case.id}")
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow, noarchive"
    switch(client, owner)
    assert "no-store" in client.get(f"/jobs/deals/case/{case.id}").headers["Cache-Control"]
    admin = _create_user(db, "safety-queue-admin@example.com", role="admin")
    switch(client, admin)
    response = client.get("/jobs/deals/admin/disputes")
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]


def test_corrupted_evidence_is_not_served_even_to_authorized_user(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    evidence(client, case, filename="evidence.txt",
             data=b"The work was delivered in full.")
    record = GigDisputeEvidence.query.one()
    assert client.get(f"/jobs/deals/case/{case.id}/attachment/{record.id}").status_code == 200
    record.attachment = b"Tampered evidence file contents"
    db.session.commit()
    assert client.get(f"/jobs/deals/case/{case.id}/attachment/{record.id}").status_code == 409


def test_suspended_existing_session_is_denied_case_and_attachment(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    evidence(client, case, filename="record.txt", data=b"Private evidence.")
    record = GigDisputeEvidence.query.one()
    worker.is_suspended = True
    db.session.commit()
    # Flask-Login treats suspended accounts as inactive, redirecting them
    # to sign-in (302) rather than returning a route-level 403.
    page = client.get(f"/jobs/deals/case/{case.id}")
    attachment = client.get(f"/jobs/deals/case/{case.id}/attachment/{record.id}")
    for response in (page, attachment):
        assert response.status_code in (302, 403)
        if response.status_code == 302:
            assert "/auth/login" in response.headers["Location"]
        assert b"Private evidence." not in response.data
    assert attachment.data != b"Private evidence."


def test_evidence_page_only_queries_visible_submitter_files(client, db):
    owner, org, job, worker, application, deal = start(client, db)
    report(client, deal)
    case = GigDispute.query.one()
    evidence(client, case, filename="worker-proof.txt",
             data=b"Private evidence for worker")
    switch(client, owner)
    evidence(client, case, filename="owner-proof.txt",
             data=b"Employer's separate evidence")
    response = client.get(f"/jobs/deals/case/{case.id}")
    assert response.status_code == 200
    text = response.get_data(as_text=True)
    assert "owner-proof.txt" in text
    assert "worker-proof.txt" not in text
    switch(client, worker)
    text = client.get(f"/jobs/deals/case/{case.id}").get_data(as_text=True)
    assert "worker-proof.txt" in text
    assert "owner-proof.txt" not in text
