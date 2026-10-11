# MyPlatoon Jobs & Gigs: Employer marketplace (phase 1)

## Purpose

Connect serving corps members and other approved MyPlatoon members with
paid, legitimate part-time work and longer-term vacancies nationwide.
Typical sources are schools needing weekend/after-school tutors,
businesses needing technology, retail, administrative or media help,
local NGOs, and employers offering full-time graduate positions.

This is an **independent community marketplace**, not NYSC deployment,
posting, CDS, PPA acceptance, NYSC permission or employment accreditation.

## Employer onboarding and identity separation

Employers may:
- Register directly at `/jobs/employers/register` with a dedicated
  `role=employer` account; these accounts do not require an NYSC camp
  platoon, stage or bogus corps-member profile.
- Already have a MyPlatoon member account? Link one organisation using
  `/jobs/employers/claim` without changing the user's existing role.
- Declare organisation type (school, business, NGO, public agency,
  other), state, LGA, public work address, description, website and
  recruiting contact details.
- Edit an organisation, which **resets its approval to pending**, hiding
  all its previously approved listings from public discovery until re-review.
- Create, edit, close, and manage applications for their own jobs.

Registration is **free**. The platform does not collect employer
verification documents, incorporation numbers, applicant NINs, CV uploads
or payments in phase one. Moderators must perform an independent
identity check before approval. Approval labels represent internal
MyPlatoon review, **not government endorsement or a guarantee**.

## Job postings

Postings must disclose:
- Opportunity title and category: gig, part-time, full-time, internship,
  or contract.
- Remote/hybrid/on-site arrangement, Nigerian state and optional LGA,
  location details and responsibilities.
- Qualifications and estimated hours/week (optional).
- Positive minimum and maximum **NGN** pay, with pay basis of hour,
  day, week, month or completed project; the maximum cannot be lower
  than the minimum. This is **advertised pay, not guaranteed wages**.
- An application deadline, not in the past.
- Whether applications are restricted to current NYSC serving members.

New and edited listings start `pending`. Listings are public only if:
1. Listing status is `published` (admin reviewed).
2. Employer is `approved`.
3. Employer account is active and not suspended.
4. Deadline has not passed.

Employer can close own listing immediately. The admin can reject or
close posts with an explanation. After an employer edits a listing or
organisation, the appropriate review must recur before publication.
No automated importing of jobs from third-party websites.

## Member application workflow

- Public visitors may browse and filter reviewed jobs by state, search
  phrase, job type and work arrangement, plus a gig/part-time shortcut.
- Only **approved, signed-in MyPlatoon member profiles** can apply.
  `serving_only` opportunities require the `serving` NYSC stage.
- Each applicant can apply **once** to a listing. Applications include
  a cover note, contact email and optional contact phone **explicitly
  provided for that vacancy only**, with consent.
- An employer sees submitted contact details, applicant's MyPlatoon
  account display name, and cover note; not the hidden main profile
  phone, residence, state of origin, platoon or NIN.
- Employers can mark an application submitted, shortlisted, declined
  or hired. MyPlatoon notifies the applicant about changes in-app.
- No in-app payments or job completion verification in phase one.
  Employers and candidates arrange payment independently after
  verifying one another. A 'hired' status reflects the employer's
  statement, **not independently verified employment**.

## Safety and moderation

- No listing, application, recruitment, or activation fees are
  collected through the platform. Listings demanding payment or PINs
  must be rejected by moderators.
- Never enter bank PINs, passwords, NIN scans, card details or personal
  credentials in job advertisements or cover notes.
- Corps members should confirm that any side work is compatible with
  PPA attendance, NYSC/CDS commitments and applicable workplace rules.
- Recruitment fraud, discrimination, exploitation or harassment should
  be reviewed by an independent moderation process before launching
  at nationwide scale.
- Members may submit a confidential safety/scam report for a listing.
  The moderation queue allows admins to dismiss an unsubstantiated report
  or close a suspicious job to stop new applications. The employer is
  informed if the listing is closed; the reporter's identity is not
  disclosed.
- An organisation name and 'reviewed' listing do not prove a vacancy
  is genuine. Encourage independent verification before accepting an
  offer or visiting an unfamiliar worksite.
- User-entered text is Jinja HTML-escaped; no user-controlled HTML
  embedding or arbitrary file upload is supported.

## Important routes

| Path | Purpose |
| --- | --- |
| `/jobs/` | Public searchable job board |
| `/jobs/<id>` | Public reviewed vacancy details |
| `/jobs/employers/register` | New employer-only account |
| `/jobs/employers/claim` | Existing member adds their organisation |
| `/jobs/employer` | Owner's organisation and vacancy dashboard |
| `/jobs/employer/edit` | Edit organisation; resets moderation |
| `/jobs/new` | Create paid posting |
| `/jobs/<id>/edit` | Edit posting; resets moderation |
| `/jobs/<id>/close` | Close posting |
| `/jobs/<id>/apply` | Consent-based private application |
| `/jobs/my-applications` | Candidate tracker |
| `/jobs/<id>/applications` | Employer applicant view |
| `/jobs/applications/<id>/status` | Change status, notifying applicant |
| `/jobs/admin/employers` | Moderator organisation queue |
| `/jobs/admin/listings` | Moderator vacancy queue |

## Database and deployment

Models: `Employer`, `JobListing`, `JobApplication`.
Database revisions: **`c8a49d127e03`** followed by
**`d6ee891f0d42`** for private job safety reports. SQLite is used for tests; the final
production target is the dedicated Aiven PostgreSQL `myplatoon`
database. **Do not execute production migrations or switch Vercel
environment secrets until the agreed end-of-project configuration**.

Development check:
`python -m pytest -q tests/test_jobs.py`, plus the existing full
`national-tests.yml` workflow and the fresh Alembic migration test.

## Next phases

Optional improvements after phase-one testing: save jobs and alerts,
employer verification evidence uploaded privately, accessible application
attachments/CV links to CareerMirror with consent, job complaint reporting,
geospatial worksite search using PostGIS and reviewed PPA data,
job recommendation filters by skills and realistic availability,
part-time-friendly shift scheduling, and school/business hiring analytics.
