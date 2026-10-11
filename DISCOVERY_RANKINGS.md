# MyPlatoon Discovery & Platoon Power Rankings

## Jobs & Gigs recommendations

`/jobs/for-me` is available to signed-in, **approved** NYSC members.
This page is a bounded suggestion list built from already-published
vacancies; it is NOT a hiring, screening, ranking or eligibility decision
by any employer, and never auto-applies to a vacancy.

Relevance is a transparent 0–100 heuristic:
- The member's **orientation posting state** is used for on-site or
  hybrid jobs. State of origin is never used as a substitute.
- Members may override the state in `/jobs/preferences`, and choose
  gig/part-time/full-time/contract/internship types, maximum hours
  available per week, and whether remote work should be included.
- Remote opportunities can match across states without GPS or precise
  coordinates. The algorithm does not currently compute kilometre
  distances. It uses employer-declared state; the member's current
  or residential location is never consulted. Listing locations are **not GIS verified** yet.
- Public professional skills and profession already entered by the
  member may increase relevance where they overlap vacancy titles and
  requirements. The score is deliberately labelled **relevance**,
  never 'likelihood of being hired' or romantic-style compatibility.
- Jobs excluded by explicit preferences are not shown in this
  personalised view. The public job board remains available independently.
- Recommendations are calculated on demand from the newest 300 public
  listings; no behavioural tracking or external AI calls.

### Bookmarks

`/jobs/saved` holds a private, one-per-member-per-job bookmark.
Saving or removing is authenticated and CSRF-protected.
Closed, expired and withdrawn listings do not become public again because
someone bookmarked them. No bookmarked job is shared with employers.

### Optional in-app alerts

- `/jobs/preferences` includes a **disabled-by-default** checkbox to
  opt in to alerts. No automatic enrolment, email, SMS, device GPS or
  off-platform messaging.
- When a moderator publishes a job, the application matches it against
  opted-in, approved members. Only matching opportunities create
  in-app notifications. Unapproved, suspended, or opted-out members
  are excluded. A separate `job_alert_deliveries` table prevents
  duplicates from repeated publication.
- This is event-driven on moderation, not a guaranteed scheduled digest
  or a promise of instantaneous delivery across offline browsers.

## Platoon Power Rankings

`/platoons/rankings` shows a public **on-platform participation
leaderboard**, not an official NYSC camp performance, physical strength
or general character ranking. Every platoon is uniquely identified by
**state + service year + batch + stream + platoon number**.
Users can filter by state/year/batch/stream to compare like for like.

Only approved, active **serving members and alumni** with a real platoon
contribute to the counts. Prospective corps members (PCMs), suspended or
unapproved accounts are excluded.

### Transparent strength score (0–100 points)

All factors are normalized by approved cohort membership size to
avoid bigger platoons winning simply by signing up more members:

- **30 points**: fraction of eligible members with profile completeness
  of at least 60%. An approved member counts at most once.
- **25 points**: fraction with a profile update in the last 90 days.
  One update counts at most once regardless of how many edits were made.
- **20 points**: fraction with at least one verified PPA/experience
  contribution or active listed MyPlatoon business. Contributions
  are capped at one credit per member; applications for jobs and
  private Dating activity **never count**.
- **25 points**: peer mini ratings (1–5 stars). A smoothed average with
  five virtual 3.5-star prior ratings reduces the advantage from a
  handful of perfect votes. The UI shows the actual star average
  and review count separately.

A cohort must have **at least three approved active members and two
eligible mini ratings** to earn an official rank within MyPlatoon.
Otherwise it is shown **provisional**. The UI must not equate a
provisional score with verified superiority.

### Mini-rating rules

- Signed-in, approved, active **serving/alumni** members may vote
  **only for their own recorded platoon**.
- Each account gets one current rating, from 1 to 5 stars. It can be
  changed, but not multiplied by submitting repeatedly.
- If a member's recorded platoon changes, the old vote is excluded
  immediately. A new vote updates that existing row instead of
  creating a second account-wide vote.
- Votes by inactive, suspended, unapproved, nonmember, PCM, or
  no-longer-matching platoon records are ignored.
- The public board contains only aggregate activity statistics and
  star counts, not the identity of individual voters.

**Limits:** This ranking is based on information entered into
MyPlatoon, not independent verification of competition results.
Moderation and anti-bot protections will need continued review at
national scale. Low-population cohorts are visibly provisional.
Profile-edit recency is a coarse proxy for on-platform participation,
not a measure of service impact.

## User routes

| Route | Description |
| --- | --- |
| `/jobs/for-me` | Personalised opportunity discovery |
| `/jobs/preferences` | Job types, posting state, hours and alert opt-in |
| `/jobs/saved` | Private bookmarks |
| `/jobs/<id>/save` | Bookmark a reviewed listing (POST) |
| `/jobs/<id>/unsave` | Unsave (POST) |
| `/platoons/rankings` | Public rankings and mini-rating widget |
| `/platoons/<id>/rate` | Rate current verified cohort (POST) |

## Database and testing

Migration **`e71f6c82a9bb`** after `d6ee891f0d42` adds:
`saved_jobs`, `job_alert_preferences`, `job_alert_deliveries`,
and `platoon_ratings`.

Regression tests: `tests/test_job_discovery_platoons.py` plus
the entire `national-tests.yml` suite and fresh upgrade check.

Production database configuration remains deferred until the agreed
final setup. The migrations and UI can be committed without changing
Aiven secrets, production schema or deploying fake placeholder rankings.
