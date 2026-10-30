"""Focused school recruitment portal and per-organisation application isolation."""
from tests.conftest import _create_user, login
from tests.test_jobs import prepare_org, prepare_job
from app.extensions import db
from app.models import JobApplication, Employer


def _application(db, job, email, status="submitted"):
    candidate = _create_user(db, email)
    record = JobApplication(
        job_id=job.id, applicant_user_id=candidate.id,
        cover_note="Teaching qualifications and classroom experience.",
        contact_email=email, status=status,
    )
    db.session.add(record)
    db.session.commit()
    return record


def test_school_login_has_recruitment_only_navigation(client, db):
    owner, employer = prepare_org(db)
    login(client, owner.email)
    page = client.get("/jobs/employer")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert "School recruitment" in html
    assert "Manage applications" in html
    assert "Applications inbox" in html
    assert "Organisation settings" in html
    assert 'href="/jobs/employer/applications"' in html
    assert "Community Feed" not in html
    assert "Platoon Rankings" not in html
    assert "Dating" not in html
    assert "NERD Guide" not in html
    assert "Suggested for you" not in html
    assert "Post a gig" not in html
    assert "Gig owner view" not in html
    assert "Member Directory" not in html


def test_school_recruitment_shell_on_mobile_and_application_pages(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    login(client, owner.email)
    for path in ("/jobs/employer", "/jobs/employer/applications",
                 "/jobs/{}/applications".format(job.id),
                 "/jobs/employer/edit"):
        response = client.get(path)
        assert response.status_code == 200, path
        html = response.get_data(as_text=True)
        assert "p5-bottom-nav" in html
        assert 'href="/jobs/employer/applications"' in html
        assert "Community Feed" not in html
        assert "Platoon Rankings" not in html
        assert "Suggested for you" not in html


def test_member_accounts_keep_community_navigation(client, member_user):
    login(client, member_user.email)
    response = client.get("/profile/dashboard")
    assert response.status_code == 200
    assert b"Community Feed" in response.data
    assert b"Platoon Rankings" in response.data


def test_school_dashboard_counts_only_own_applications(client, db):
    owner, school = prepare_org(db)
    job = prepare_job(db, school)
    _application(db, job, "teacher-new@example.com")
    _application(db, job, "teacher-shortlisted@example.com", "shortlisted")
    other_owner = _create_user(db, "other-school@example.com", role="employer")
    other = Employer(
        owner_user_id=other_owner.id, name="Other School", kind="school",
        state="Lagos", lga="Ikeja", address="Other campus",
        description="School recruiting staff in a different city.",
        contact_email=other_owner.email, status="approved",
    )
    db.session.add(other)
    db.session.commit()
    other_job = prepare_job(db, other)
    _application(db, other_job, "other-secret@example.com")

    login(client, owner.email)
    dashboard = client.get("/jobs/employer").get_data(as_text=True)
    assert "Total applications" in dashboard
    assert "New applications" in dashboard
    assert "teacher-new@example.com" in dashboard or "Test User" in dashboard
    assert "other-secret@example.com" not in dashboard

    inbox = client.get("/jobs/employer/applications").get_data(as_text=True)
    assert "teacher-new@example.com" in inbox
    assert "teacher-shortlisted@example.com" in inbox
    assert "other-secret@example.com" not in inbox


def test_school_application_inbox_filters_status_and_vacancy(client, db):
    owner, school = prepare_org(db)
    first_job = prepare_job(db, school)
    second_job = prepare_job(db, school)
    new = _application(db, first_job, "new-applicant@example.com")
    shortlisted = _application(db, second_job, "shortlisted-applicant@example.com", "shortlisted")
    login(client, owner.email)

    filtered = client.get("/jobs/employer/applications?status=shortlisted")
    assert filtered.status_code == 200
    html = filtered.get_data(as_text=True)
    assert "shortlisted-applicant@example.com" in html
    assert "new-applicant@example.com" not in html

    filtered = client.get(f"/jobs/employer/applications?job={first_job.id}")
    html = filtered.get_data(as_text=True)
    assert "new-applicant@example.com" in html
    assert "shortlisted-applicant@example.com" not in html

    assert client.get("/jobs/employer/applications?status=not-valid").status_code == 400


def test_other_school_cannot_see_or_change_applicants(client, db):
    owner, school = prepare_org(db)
    job = prepare_job(db, school)
    app = _application(db, job, "secret-candidate@example.com")
    other = _create_user(db, "outsider-school@example.com", role="employer")
    db.session.add(Employer(
        owner_user_id=other.id, name="Outsider School", kind="school",
        state="Lagos", lga="Ikeja", address="Outsider campus",
        description="Different hiring organisation.",
        contact_email=other.email, status="approved",
    ))
    db.session.commit()

    login(client, other.email)
    inbox = client.get("/jobs/employer/applications").get_data(as_text=True)
    assert "secret-candidate@example.com" not in inbox
    scoped = client.get(f"/jobs/employer/applications?job={job.id}")
    assert scoped.status_code == 200
    assert "secret-candidate@example.com" not in scoped.get_data(as_text=True)
    assert client.get(f"/jobs/{job.id}/applications").status_code == 403
    assert client.post(f"/jobs/applications/{app.id}/status",
                       data={"status": "hired", "return_to": "inbox"}).status_code == 403
    db.session.refresh(app)
    assert app.status == "submitted"


def test_employer_application_status_returns_to_inbox(client, db):
    owner, school = prepare_org(db)
    job = prepare_job(db, school)
    app = _application(db, job, "candidate@example.com")
    login(client, owner.email)
    response = client.post(
        f"/jobs/applications/{app.id}/status",
        data={"status": "shortlisted", "return_to": "inbox"},
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/jobs/employer/applications")
    db.session.refresh(app)
    assert app.status == "shortlisted"


def test_member_claiming_school_gets_focused_hiring_pages(client, member_user, db):
    school = Employer(
        owner_user_id=member_user.id, name="Member's School", kind="school",
        state="Benue", lga="Makurdi", address="Member campus",
        description="A school with an existing member as owner.",
        contact_email=member_user.email, status="approved",
    )
    db.session.add(school)
    db.session.commit()
    login(client, member_user.email)
    hiring = client.get("/jobs/employer").get_data(as_text=True)
    assert "School recruitment" in hiring
    assert "Community Feed" not in hiring
    community = client.get("/profile/dashboard").get_data(as_text=True)
    assert "Community Feed" in community
