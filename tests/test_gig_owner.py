"""Dedicated paid-gig-owner registration and moderated publishing workflow."""
from datetime import date, timedelta

from tests.conftest import _create_user, login
from app.extensions import db
from app.models import Employer, JobListing, Profile, User


def gig_owner_data(**updates):
    values = {
        "full_name": "Grace Example",
        "email": "grace-gigs@example.com",
        "password": "Password123",
        "confirm_password": "Password123",
        "name": "Grace Weekend Gigs",
        "kind": "individual",
        "state": "Benue",
        "lga": "Makurdi",
        "address": "Community workplace, Makurdi",
        "description": "Independent organiser hiring tutors and local event workers for paid short-term tasks.",
        "contact_email": "grace-gigs@example.com",
        "contact_phone": "",
        "website": "",
        "safety_agreement": "y",
    }
    values.update(updates)
    return values


def gig_data(**updates):
    values = {
        "title": "Saturday mathematics tutor",
        "work_mode": "onsite",
        "state": "Benue",
        "lga": "Makurdi",
        "location_description": "Near central market",
        "description": "Teach a small group of students on Saturday and provide simple mathematics exercises.",
        "requirements": "Comfortable with mathematics tutoring and small groups.",
        "hours_per_week": "6",
        "schedule_notes": "Every Saturday morning",
        "pay_amount": "12000",
        "pay_unit": "project",
        "closing_date": (date.today() + timedelta(days=15)).isoformat(),
        "serving_only": "y",
        "safety_agreement": "y",
    }
    values.update(updates)
    return values


def test_gig_owner_hub_is_public_and_linked(client):
    res = client.get("/jobs/gig-owners")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Need an extra pair of hands?" in html
    assert 'href="/jobs/gig-owners/register"' in html
    assert "Free registration" in html
    assert "No recruitment fees" in html
    assert 'href="/jobs/gig-owners"' in client.get("/").get_data(as_text=True)
    assert 'href="/jobs/gig-owners"' in client.get("/jobs/").get_data(as_text=True)


def test_registration_form_explains_moderation(client):
    res = client.get("/jobs/gig-owners/register")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "Create your gig owner account" in html
    assert "NYSC number" in html
    assert 'name="safety_agreement"' in html


def test_new_gig_owner_can_sign_up_and_start_posting_without_member_profile(client):
    res = client.post("/jobs/gig-owners/register", data=gig_owner_data())
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/jobs/gigs/new")
    owner = User.query.filter_by(email="grace-gigs@example.com").one()
    assert owner.role == "employer"
    assert Profile.query.filter_by(user_id=owner.id).first() is None
    record = Employer.query.filter_by(owner_user_id=owner.id).one()
    assert record.kind == "individual"
    assert record.status == "pending"
    # Logged in directly after signup, ready to add their first gig.
    form_page = client.get("/jobs/gigs/new")
    assert form_page.status_code == 200
    assert b"Step 2 of 2" in form_page.data
    assert b"Organisation: Pending" in form_page.data


def test_register_requires_safety_agreement_and_prevents_duplicate_email(client):
    assert client.post("/jobs/gig-owners/register",
                       data=gig_owner_data(safety_agreement="")).status_code == 200
    assert Employer.query.count() == 0
    assert client.post("/jobs/gig-owners/register",
                       data=gig_owner_data()).status_code == 302
    # Signed in after registration; log out before testing a second signup.
    client.get("/auth/logout")
    result = client.post("/jobs/gig-owners/register", data=gig_owner_data())
    assert result.status_code == 200
    assert Employer.query.count() == 1


def test_serving_member_can_add_owner_profile_without_replacing_member_role(client):
    member = _create_user(db, "corps-gig-owner@example.com")
    login(client, member.email)
    payload = gig_owner_data()
    for name in ("full_name", "email", "password", "confirm_password"):
        payload.pop(name)
    res = client.post("/jobs/gig-owners/claim", data=payload)
    assert res.status_code == 302
    assert res.headers["Location"].endswith("/jobs/gigs/new")
    assert member.role == "member"
    assert member.profile is not None
    record = Employer.query.filter_by(owner_user_id=member.id).one()
    assert record.kind == "individual"
    assert record.status == "pending"


def test_new_gig_is_saved_pending_not_in_public_board(client):
    client.post("/jobs/gig-owners/register", data=gig_owner_data())
    result = client.post("/jobs/gigs/new", data=gig_data())
    assert result.status_code == 302
    assert result.headers["Location"].endswith("/jobs/gig-owners/dashboard")
    gig = JobListing.query.one()
    assert gig.job_kind == "gig"
    assert gig.status == "pending"
    assert gig.pay_min == 12000 and gig.pay_max == 12000
    assert gig.serving_only is True
    assert b"Pending review" in client.get("/jobs/gig-owners/dashboard").data
    client.get("/auth/logout")
    assert "Saturday mathematics tutor" not in client.get("/jobs/").get_data(as_text=True)
    assert client.get("/jobs/{}".format(gig.id)).status_code == 404


def test_approval_is_required_for_both_employer_and_gig(client):
    client.post("/jobs/gig-owners/register", data=gig_owner_data())
    client.post("/jobs/gigs/new", data=gig_data())
    gig = JobListing.query.one()
    owner_record = Employer.query.one()
    client.get("/auth/logout")
    admin = _create_user(db, "gig-admin@example.com", role="admin")
    login(client, admin.email)
    # A listing cannot be forced live while the gig owner is still pending.
    assert client.post("/jobs/admin/listings/{}/review".format(gig.id),
                       data={"decision": "published"}).status_code == 302
    assert gig.status == "pending"
    assert client.post("/jobs/admin/employers/{}/review".format(owner_record.id),
                       data={"decision": "approved"}).status_code == 302
    assert owner_record.status == "approved"
    assert client.post("/jobs/admin/listings/{}/review".format(gig.id),
                       data={"decision": "published"}).status_code == 302
    assert gig.status == "published"
    client.get("/auth/logout")
    assert b"Saturday mathematics tutor" in client.get("/jobs/").data
    assert client.get("/jobs/{}".format(gig.id)).status_code == 200


def test_gig_validation_blocks_zero_pay_past_deadline_and_missing_consent(client):
    client.post("/jobs/gig-owners/register", data=gig_owner_data())
    assert client.post("/jobs/gigs/new",
                       data=gig_data(pay_amount="0")).status_code == 200
    assert client.post("/jobs/gigs/new",
                       data=gig_data(safety_agreement="")).status_code == 200
    assert client.post("/jobs/gigs/new",
                       data=gig_data(closing_date=(date.today() - timedelta(days=1)).isoformat())).status_code == 200
    assert JobListing.query.count() == 0


def test_gig_owner_does_not_have_cross_owner_access_to_applicants_or_edits(client):
    client.post("/jobs/gig-owners/register", data=gig_owner_data())
    client.post("/jobs/gigs/new", data=gig_data())
    gig = JobListing.query.one()
    client.get("/auth/logout")
    second = _create_user(db, "another-employer@example.com", role="employer")
    db.session.add(Employer(
        owner_user_id=second.id, name="Another School", kind="school",
        state="Benue", lga="Makurdi", address="Another campus",
        description="We hire a variety of weekend instructors for our programme.",
        contact_email=second.email, status="approved",
    ))
    db.session.commit()
    login(client, second.email)
    assert client.get("/jobs/{}/applications".format(gig.id)).status_code == 403
    assert client.post("/jobs/{}/edit".format(gig.id),
                       data={"title": "Tampered gig"}).status_code == 403
    assert client.post("/jobs/{}/close".format(gig.id)).status_code == 403
    assert gig.status == "pending"


def test_suspended_gig_owner_cannot_submit_more_gigs(client):
    client.post("/jobs/gig-owners/register", data=gig_owner_data())
    employer = Employer.query.one()
    employer.status = "suspended"
    db.session.commit()
    assert client.get("/jobs/gigs/new").status_code == 302
    assert client.post("/jobs/gigs/new", data=gig_data()).status_code == 302
    assert JobListing.query.count() == 0
