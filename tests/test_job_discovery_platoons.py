"""Personalised gigs, opt-in in-app alerts and fair own-cohort rankings."""
from datetime import datetime, date, timedelta

from tests.conftest import _create_user, login
from app.models import (
    Platoon, PlatoonRating, JobAlertPreference, JobAlertDelivery,
    SavedJob, Notification, Profile, User,
)
from app.services.job_discovery import recommended_jobs, match_score
from app.services.platoon_rankings import leaderboard
from tests.test_jobs import prepare_org, prepare_job


def join_cohort(db, user, platoon=None, state="Benue", approved=True):
    platoon = platoon or Platoon.find_or_create(state, 2026, "B", "II", 5)
    member = Profile.query.filter_by(user_id=user.id).one()
    member.service_stage = "serving"
    member.platoon_id = platoon.id
    member.status = "approved" if approved else "pending"
    db.session.commit()
    return platoon


def test_personalised_jobs_match_posting_state_not_state_of_origin(client, db):
    owner, organisation = prepare_org(db)
    near = prepare_job(db, organisation, title="Weekend maths in Makurdi")
    far = prepare_job(db, organisation, title="Weekend tutoring in Abuja", state="FCT")
    remote = prepare_job(db, organisation, title="Remote class tutor", work_mode="remote", state="Lagos")
    member = _create_user(db, "state-match@example.com")
    join_cohort(db, member)
    member.profile.state_of_origin = "FCT"  # this must NOT be used as the posting state
    db.session.commit()
    results = recommended_jobs(member)
    jobs = {j.id for j, _score in results}
    assert near.id in jobs and remote.id in jobs
    assert far.id not in jobs
    login(client, member.email)
    page = client.get("/jobs/for-me")
    assert page.status_code == 200
    assert b"Weekend maths in Makurdi" in page.data
    assert b"Weekend tutoring in Abuja" not in page.data


def test_preference_controls_hours_types_remote_and_explicit_alert_optin(client, db):
    owner, organisation = prepare_org(db)
    local = prepare_job(db, organisation, title="Short tutoring job", hours_per_week=8)
    long = prepare_job(db, organisation, title="Long tutoring job", hours_per_week=40)
    remote = prepare_job(db, organisation, title="Remote teaching role", work_mode="remote", state="Lagos")
    member = _create_user(db, "prefs@example.com")
    join_cohort(db, member)
    login(client, member.email)
    assert JobAlertPreference.query.count() == 0
    response = client.post("/jobs/preferences", data={
        "preferred_state": "", "preferred_kinds": ["part_time"],
        "available_hours": "12", "enabled": "y",
    })
    assert response.status_code == 302
    preference = JobAlertPreference.query.one()
    assert preference.enabled is True
    assert preference.remote_ok is False
    matches = {j.id for j, _score in recommended_jobs(member)}
    assert local.id in matches
    assert long.id not in matches
    assert remote.id not in matches


def test_bookmarks_are_user_private_idempotent_and_removable(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org)
    member = _create_user(db, "bookmark@example.com")
    other = _create_user(db, "bookmark-other@example.com")
    login(client, member.email)
    assert client.post(f"/jobs/{job.id}/save").status_code == 302
    assert client.post(f"/jobs/{job.id}/save").status_code == 302
    assert SavedJob.query.count() == 1
    assert b"Weekend mathematics tutor" in client.get("/jobs/saved").data
    client.post("/auth/logout")
    login(client, other.email)
    assert b"Weekend mathematics tutor" not in client.get("/jobs/saved").data
    client.post(f"/jobs/{job.id}/unsave")
    assert SavedJob.query.count() == 1
    client.post("/auth/logout")
    login(client, member.email)
    assert client.post(f"/jobs/{job.id}/unsave").status_code == 302
    assert SavedJob.query.count() == 0


def test_public_filters_never_become_private_through_saved_route(client, db):
    owner, org = prepare_org(db)
    draft = prepare_job(db, org, published=False)
    member = _create_user(db, "nonpublic@example.com")
    login(client, member.email)
    assert client.post(f"/jobs/{draft.id}/save").status_code == 404
    assert SavedJob.query.count() == 0


def test_job_publish_alerts_only_opted_in_eligible_matching_members(client, db):
    owner, org = prepare_org(db)
    job = prepare_job(db, org, published=False, state="Benue")
    matched = _create_user(db, "alert-subscriber@example.com")
    unmatched = _create_user(db, "alert-otherstate@example.com")
    opted_out = _create_user(db, "alert-disabled@example.com")
    join_cohort(db, matched)
    join_cohort(db, unmatched, state="Lagos")
    join_cohort(db, opted_out)
    for member, enabled in ((matched, True), (unmatched, True), (opted_out, False)):
        db.session.add(JobAlertPreference(
            user_id=member.id, preferred_kinds="gig,part_time",
            enabled=enabled, remote_ok=True))
    db.session.commit()
    admin = _create_user(db, "alerts-admin@example.com", role="admin")
    login(client, admin.email)
    assert client.post(f"/jobs/admin/listings/{job.id}/review",
                       data={"decision": "published"}).status_code == 302
    assert job.status == "published"
    assert JobAlertDelivery.query.count() == 1
    receipt = JobAlertDelivery.query.one()
    assert receipt.user_id == matched.id
    messages = Notification.query.filter_by(user_id=matched.id).all()
    assert len(messages) == 1
    assert job.title in messages[0].message
    assert Notification.query.filter_by(user_id=unmatched.id).count() == 0
    assert Notification.query.filter_by(user_id=opted_out.id).count() == 0
    # Republishing a job should not produce duplicate alerts for the same member.
    client.post(f"/jobs/admin/listings/{job.id}/review", data={"decision": "published"})
    assert JobAlertDelivery.query.count() == 1


def test_ranking_page_is_public_and_no_unverified_members_count(client, db):
    p = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    db.session.commit()
    pending = _create_user(db, "pending-rank@example.com")
    pending.profile.platoon_id = p.id
    pending.profile.service_stage = "serving"
    pending.profile.status = "pending"
    db.session.commit()
    board = client.get("/platoons/rankings?state=Benue&year=2026&batch=B&stream=II")
    assert board.status_code == 200
    html = board.get_data(as_text=True)
    assert "Platoon Power Rankings" in html
    rows = leaderboard(state="Benue", year=2026, batch="B", stream="II")
    assert len(rows) == 1
    assert rows[0]["members"] == 0
    assert rows[0]["qualified"] is False


def test_member_may_rate_only_own_approved_cohort(client, db):
    own = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    other = Platoon.find_or_create("Benue", 2026, "B", "II", 4)
    db.session.commit()
    user = _create_user(db, "rater@example.com")
    join_cohort(db, user, own)
    login(client, user.email)
    assert client.post(f"/platoons/{other.id}/rate", data={"stars": "5"}).status_code == 403
    assert client.post(f"/platoons/{own.id}/rate", data={"stars": "7"}).status_code == 400
    assert client.post(f"/platoons/{own.id}/rate", data={"stars": "5"}).status_code == 302
    assert PlatoonRating.query.count() == 1
    assert PlatoonRating.query.one().stars == 5
    assert client.post(f"/platoons/{own.id}/rate", data={"stars": "3"}).status_code == 302
    assert PlatoonRating.query.count() == 1
    assert PlatoonRating.query.one().stars == 3


def test_pcm_unapproved_and_employer_are_unable_to_vote(client, db):
    p = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    db.session.commit()
    member = _create_user(db, "pcm-rater@example.com")
    member.profile.status = "approved"
    member.profile.service_stage = "pcm"
    member.profile.platoon_id = p.id
    db.session.commit()
    login(client, member.email)
    assert client.post(f"/platoons/{p.id}/rate", data={"stars": "5"}).status_code == 403
    client.post("/auth/logout")
    employer = _create_user(db, "employer-rater@example.com", role="employer")
    login(client, employer.email)
    assert client.post(f"/platoons/{p.id}/rate", data={"stars": "5"}).status_code == 403
    assert PlatoonRating.query.count() == 0


def test_cohort_scoped_rank_and_size_normalisation(client, db):
    own = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    other = Platoon.find_or_create("Borno", 2026, "B", "II", 5)
    db.session.commit()
    voters = []
    for n in range(3):
        user = _create_user(db, f"rank-member-{n}@example.com")
        join_cohort(db, user, own)
        voters.append(user)
    for n in range(2):
        user = _create_user(db, f"other-member-{n}@example.com")
        join_cohort(db, user, other)
    for user in voters[:2]:
        db.session.add(PlatoonRating(platoon_id=own.id, user_id=user.id, stars=5))
    db.session.commit()
    board = leaderboard()
    row = next(r for r in board if r["platoon"].id == own.id)
    other_row = next(r for r in board if r["platoon"].id == other.id)
    assert row["qualified"] is True
    assert row["rank"] == 1
    assert row["members"] == 3
    assert row["ratings"] == 2
    assert row["stars"] == 5.0
    assert 0 <= row["score"] <= 100
    assert other_row["qualified"] is False
    assert other_row["rank"] is None
    assert own.label != other.label


def test_rating_previous_cohort_is_disregarded_if_member_moves(client, db):
    p1 = Platoon.find_or_create("Benue", 2026, "B", "II", 5)
    p2 = Platoon.find_or_create("Benue", 2026, "B", "II", 3)
    db.session.commit()
    user = _create_user(db, "moved-rater@example.com")
    join_cohort(db, user, p1)
    login(client, user.email)
    client.post(f"/platoons/{p1.id}/rate", data={"stars": "5"})
    user.profile.platoon_id = p2.id
    db.session.commit()
    # Old vote no longer contributes to score.
    row = next(r for r in leaderboard() if r["platoon"].id == p1.id)
    assert row["ratings"] == 0
    assert client.post(f"/platoons/{p1.id}/rate", data={"stars": "4"}).status_code == 403
    client.post(f"/platoons/{p2.id}/rate", data={"stars": "4"})
    rating = PlatoonRating.query.one()
    assert rating.platoon_id == p2.id
    assert rating.stars == 4



def test_national_rankings_do_not_omit_late_alphabet_states_after_100_cohorts(db):
    # Historical bug: the scoreboard took the first 100 states/cohorts in
    # alphabetical order and called the winner the national strongest.
    # A Zamfara cohort must not disappear behind 100 Abia/Adamawa rows.
    for index in range(102):
        state = "Abia" if index < 99 else "Adamawa"
        number = index + 1 if index < 99 else index - 98
        Platoon.find_or_create(state, 2026, "A", "I", number)
    target = Platoon.find_or_create("Zamfara", 2026, "B", "II", 5)
    db.session.commit()
    voters = []
    for index in range(3):
        user = _create_user(db, "zamfara-{}@example.com".format(index))
        join_cohort(db, user, target)
        voters.append(user)
    db.session.add(PlatoonRating(platoon_id=target.id, user_id=voters[0].id, stars=4))
    db.session.add(PlatoonRating(platoon_id=target.id, user_id=voters[1].id, stars=5))
    db.session.commit()
    rows = leaderboard()
    assert len(rows) == 103
    row = next(item for item in rows if item["platoon"].id == target.id)
    assert row["qualified"]
    assert row["rank"] == 1
