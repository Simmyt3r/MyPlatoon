"""Jobs & Gigs: employer accounts, moderation, consent and privacy boundaries."""
from datetime import date, timedelta

from tests.conftest import _create_user, login
from app.models import Employer, JobListing, JobApplication, Profile, User


def org_data(**kwargs):
    out = {
        "name": "Bright Minds Academy",
        "kind": "school",
        "state": "Benue",
        "lga": "Makurdi",
        "address": "Teaching Campus, North Bank Makurdi",
        "description": "We are a community school that delivers after-school tutoring and classes.",
        "contact_email": "hiring@school.example",
        "contact_phone": "09010010010",
        "website": "https://school.example",
    }
    out.update(kwargs)
    return out


def job_data(**kwargs):
    out = {
        "title": "Weekend mathematics tutor",
        "job_kind": "part_time",
        "work_mode": "onsite",
        "state": "Benue",
        "lga": "Makurdi",
        "location_description": "Near the central market",
        "description": "Teach mathematics on Saturdays for small student classes and prepare weekly exercises.",
        "requirements": "Basic teaching experience and mathematics knowledge.",
        "hours_per_week": "8",
        "schedule_notes": "Saturdays 9 AM to 5 PM",
        "pay_min": "10000",
        "pay_max": "20000",
        "pay_unit": "week",
        "closing_date": (date.today() + timedelta(days=30)).isoformat(),
        "serving_only": "y",
    }
    out.update(kwargs)
    return out


def prepare_org(db, user=None, approved=True):
    if user is None:
        user = _create_user(db, "owner-school@example.com", role="employer",
                            full_name="Head Teacher")
    org = Employer(owner_user_id=user.id, status="approved" if approved else "pending",
                   **org_data())
    db.session.add(org)
    db.session.commit()
    return user, org


def prepare_job(db, org, published=True, **kwargs):
    values = dict(
        employer_id=org.id,
        title="Weekend mathematics tutor",
        job_kind="part_time",
        work_mode="onsite",
        state="Benue",
        lga="Makurdi",
        location_description="Public school",
        description="Teach mathematics to small groups of learners on Saturday mornings.",
        requirements="Knowledge of school mathematics and teaching skills",
        hours_per_week=8,
        schedule_notes="Saturday",
        pay_min=10000,
        pay_max=20000,
        pay_unit="week",
        closing_date=date.today() + timedelta(days=30),
        serving_only=True,
        status="published" if published else "pending",
    )
    values.update(kwargs)
    job = JobListing(**values)
    db.session.add(job)
    db.session.commit()
    return job


def approve_serving(db, user):
    user.profile.status = "approved"
    user.profile.service_stage = "serving"
    db.session.commit()


def test_public_board_and_services_link(client):
    page = client.get("/jobs/")
    assert page.status_code == 200
    assert b"Jobs &amp; Gigs" in page.data
    assert b"recruitment" in page.data.lower()
    assert 'href="/jobs/"' in client.get("/services").get_data(as_text=True)
    assert 'href="/jobs/"' in client.get("/").get_data(as_text=True)


def test_dedicated_school_registers_without_fake_platoon(client, db):
    data = dict(org_data(), full_name="Head Teacher",
                email="head@school.example", password="Password123",
                confirm_password="Password123")
    response = client.post("/jobs/employers/register", data=data)
    assert response.status_code == 302
    user = User.query.filter_by(email="head@school.example").one()
    org = Employer.query.filter_by(owner_user_id=user.id).one()
    assert user.role == "employer"
    assert Profile.query.filter_by(user_id=user.id).first() is None
    assert org.status == "pending"
    login(client, user.email)
    dashboard = client.get("/jobs/employer")
    assert dashboard.status_code == 200
    assert b"Bright Minds Academy" in dashboard.data
    assert Profile.query.filter_by(user_id=user.id).first() is None


def test_existing_member_can_register_school_without_role_change(client, member_user, db):
    login(client, member_user.email)
    response = client.post("/jobs/employers/claim", data=org_data())
    assert response.status_code == 302
    assert Employer.query.count() == 1
    assert member_user.role == "member"
    assert member_user.profile is not None


def test_existing_employer_email_cannot_duplicate(client, db):
    user, org = prepare_org(db)
    data = dict(org_data(), full_name="Another",
                email=user.email, password="Password123",
                confirm_password="Password123")
    assert client.post("/jobs/employers/register", data=data).status_code == 200
    assert Employer.query.count() == 1


def test_unapproved_organisation_and_listing_are_hidden(client, db):
    owner, org = prepare_org(db, approved=False)
    job = prepare_job(db, org, published=True)
    assert job.is_open is False
    assert "Weekend mathematics tutor" not in client.get("/jobs/").get_data(as_text=True)
    assert client.get("/jobs/{}".format(job.id)).status_code == 404


def test_employer_can_submit_pending_listing_and_admin_publishes(client, db):
    owner, org = prepare_org(db)
    login(client, owner.email)
    r = client.post("/jobs/new", data=job_data())
    assert r.status_code == 302
    job = JobListing.query.one()
    assert job.status == "pending"
    assert client.get("/jobs/{}".format(job.id)).status_code == 200  # owner preview
    client.get("/auth/logout")
    admin = _create_user(db, "jobs-admin@example.com", role="admin")
    login(client, admin.email)
    r = client.post("/jobs/admin/listings/{}/review".format(job.id),
                    data={"decision": "published"})
    assert r.status_code == 302
    assert job.status == "published"
    page = client.get("/jobs/?state=Benue&kind=part_time&serving=1")
    assert b"Weekend mathematics tutor" in page.data


def test_unapproved_employer_cannot_have_jobs_published(client, db):
    owner, org = prepare_org(db, approved=False)
    job = prepare_job(db, org, published=False)
    admin = _create_user(db, "jobs-admin@example.com", role="admin")
    login(client, admin.email)
    client.post("/jobs/admin/listings/{}/review".format(job.id),
                data={"decision": "published"})
    assert job.status == "pending"


def test_negative_or_zero_pay_and_past_deadline_rejected(client, db):
    owner, org = prepare_org(db)
    login(client, owner.email)
    assert client.post("/jobs/new", data=job_data(pay_min="0")).status_code == 200
    assert client.post("/jobs/new", data=job_data(pay_min="50000",
                                                   pay_max="10000")).status_code == 200
    assert client.post("/jobs/new", data=job_data(
        closing_date=(date.today() - timedelta(days=1)).isoformat())).status_code == 200
    assert JobListing.query.count() == 0


def test_edit_requires_review_again(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    login(client, owner.email)
    r = client.post("/jobs/{}/edit".format(job.id),
                    data=job_data(title="New weekend teaching role"))
    assert r.status_code == 302
    assert job.status == "pending"
    client.get("/auth/logout")
    assert client.get("/jobs/{}".format(job.id)).status_code == 404


def test_approved_serving_member_applies_once_and_shares_only_opted_contact(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    candidate = _create_user(db, "candidate@example.com", full_name="Candidate One")
    approve_serving(db, candidate)
    candidate.profile.phone_number = "PRIVATE-NOT-SHARED"
    candidate.profile.address = "PRIVATE-HOME"
    db.session.commit()
    login(client, candidate.email)
    data = {
        "cover_note": "I can teach mathematics at the weekend and have class management experience.",
        "contact_email": "myjobs@example.com",
        "contact_phone": "08012349876",
        "consent": "y",
    }
    assert client.post("/jobs/{}/apply".format(job.id), data=data).status_code == 302
    application = JobApplication.query.one()
    assert application.contact_email == "myjobs@example.com"
    assert application.contact_phone == "08012349876"
    assert JobApplication.query.count() == 1
    client.post("/jobs/{}/apply".format(job.id), data=data)
    assert JobApplication.query.count() == 1
    client.get("/auth/logout")
    login(client, owner.email)
    html = client.get("/jobs/{}/applications".format(job.id)).get_data(as_text=True)
    assert "myjobs@example.com" in html
    assert "PRIVATE-NOT-SHARED" not in html
    assert "PRIVATE-HOME" not in html


def test_unapproved_member_cannot_apply_and_serving_only_is_enforced(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    candidate = _create_user(db, "candidate@example.com")
    login(client, candidate.email)
    assert client.post("/jobs/{}/apply".format(job.id),
                       data={"contact_email": candidate.email}).status_code == 302
    assert JobApplication.query.count() == 0
    candidate.profile.status = "approved"
    candidate.profile.service_stage = "pcm"
    db.session.commit()
    assert client.post("/jobs/{}/apply".format(job.id),
                       data={"contact_email": candidate.email}).status_code == 302
    assert JobApplication.query.count() == 0


def test_application_requires_explicit_contact_consent(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    candidate = _create_user(db, "candidate@example.com")
    approve_serving(db, candidate)
    login(client, candidate.email)
    r = client.post("/jobs/{}/apply".format(job.id), data={
        "cover_note": "I have teaching experience and can work on Saturdays for the school.",
        "contact_email": candidate.email,
    })
    assert r.status_code == 200
    assert JobApplication.query.count() == 0


def test_other_employers_cannot_read_candidates_or_change_status(client, db):
    owner, org = prepare_org(db)
    outsider, outsider_org = prepare_org(db,
        user=_create_user(db, "outsider@example.com", role="employer"))
    job = prepare_job(db, org)
    candidate = _create_user(db, "candidate@example.com")
    approve_serving(db, candidate)
    app = JobApplication(job_id=job.id, applicant_user_id=candidate.id,
                         cover_note="Applicant-specific private message.",
                         contact_email="candidate-private@example.com")
    db.session.add(app)
    db.session.commit()
    login(client, outsider.email)
    assert client.get("/jobs/{}/applications".format(job.id)).status_code == 403
    assert client.post("/jobs/applications/{}/status".format(app.id),
                       data={"status": "hired"}).status_code == 403
    assert app.status == "submitted"


def test_reviewer_permissions_and_rejection_notes(client, db):
    owner, org = prepare_org(db, approved=False)
    job = prepare_job(db, org, published=False)
    member = _create_user(db, "normal@example.com")
    login(client, member.email)
    assert client.get("/jobs/admin/employers").status_code == 403
    assert client.post("/jobs/admin/employers/{}/review".format(org.id),
                       data={"decision": "approved"}).status_code == 403
    client.get("/auth/logout")
    admin = _create_user(db, "jobs-admin@example.com", role="admin")
    login(client, admin.email)
    assert client.post("/jobs/admin/employers/{}/review".format(org.id),
                       data={"decision": "rejected", "note": "no"}).status_code == 302
    assert org.status == "pending"
    assert client.post("/jobs/admin/employers/{}/review".format(org.id),
                       data={"decision": "approved"}).status_code == 302
    assert org.status == "approved"
    assert job.status == "pending"


def test_expired_listing_not_discoverable_or_open_for_application(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org,
        closing_date=date.today() - timedelta(days=1))
    assert job.is_open is False
    assert client.get("/jobs/{}".format(job.id)).status_code == 404


def test_moderated_employer_contacts_not_public(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    html = client.get("/jobs/{}".format(job.id)).get_data(as_text=True)
    assert "hiring@school.example" not in html
    assert "09010010010" not in html
