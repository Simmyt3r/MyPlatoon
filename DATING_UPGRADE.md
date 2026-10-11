# MyPlatoon Dating v2

## What changed

The Dating area is an **independent, opt-in, adults-only community** for
approved MyPlatoon members. It uses its own `DatingPersona`; creating a
normal NYSC/PCM profile does not register anyone for Dating.

### Adults-only confirmation

Each user must expressly confirm they are 18 or older to create or continue
using a dating persona. The database stores only the time of self-attestation
(`age_confirmed_at`), **not** an identity document or birth date. This is
self-reported and **is not verified proof of age**. Older personas with no
confirmation must acknowledge the requirement at the edit page before they
are eligible to browse or be recommended.

### Matching, suggestions and consent

- Suggestions are ranked by overlapping self-declared interests (80%) and
  listed skills (20%) using Jaccard similarity; no inferred ethnicity,
  state-of-origin bonus, pseudo-random spark or relationship-success
  prediction.
- Mutual top picks are **algorithmic overlaps**, *not* explicit agreement,
  reciprocated attraction or an invitation to communicate.
- No match notification is sent solely because two ranked lists overlap.
- A member may privately express interest in an active, compatible dating
  persona. A unilateral interest is not notified to the recipient.
- **Only when the interest is mutual** are both users notified and the other
  person listed under `/dating/connections`.
- Members can withdraw interest and the pair disappears from Connections.
- Once two members explicitly express interest in each other, they can
  exchange **private plain-text messages** through `/dating/messages/<id>`.
  Every message read/send checks active reciprocal consent, approval,
  age confirmation and blocks. Withdrawing interest or blocking immediately
  revokes both sides' chat access, even if the URL was bookmarked.
- Private message notifications never include message bodies.
- Message recipients can confidentially flag received content to moderators.
  This continues to work after blocking or withdrawing interest.
- No images, attachments, automatic phone-number exchange or encrypted
  end-to-end messaging are provided by this release.

### Privacy

- Dating persona previews use `/dating/person/<id>` and display only a
  chosen display name, tagline, optional bio, self-entered interests and
  optional profile picture.
- The user must explicitly select **Show my MyPlatoon profile picture to
  other Dating participants**. It defaults OFF, including all existing
  personas after migration.
- No automatic link to the full member directory profile. Member phone,
  WhatsApp, address, place of assignment, alumni cohort or full name are not
  included in Dating previews.
- A personal block works in both directions and is not announced to the
  blocked person. Blocking deletes any existing interest between the pair
  and prevents new suggestions, previews and connections.
- Paused, reported, unapproved, suspended and unconfirmed adult personas are
  hidden from candidates and existing suggestion lists.
- A user can delete a Dating persona, matches, interest and blocks without
  losing their primary MyPlatoon account.
- Reporting is moderated by the existing admin safety queue. Reported
  personas are temporarily suppressed from discovery until an admin clears
  or removes them.

### Gender preferences

Self-described identity options: man, woman and nonbinary.
The member may prefer men, women, nonbinary people or everyone.
Candidate eligibility requires preferences to be **compatible in both
directions**.

### User routes

| URL | Method | Purpose |
| --- | --- | --- |
| `/dating/` | GET | Dashboard with suggested people |
| `/dating/persona` | GET/POST | Create/edit adult opted-in persona and photo choice |
| `/dating/browse` | GET | Ranked suggestions |
| `/dating/matches` | GET | Algorithmic mutual top picks |
| `/dating/connections` | GET | Explicitly reciprocal expressions of interest |
| `/dating/person/<id>` | GET | Limited persona preview |
| `/dating/interest/<id>` | POST | Express interest privately |
| `/dating/interest/<id>/withdraw` | POST | Withdraw interest |
| `/dating/block/<id>` | POST | Personal block |
| `/dating/blocked` | GET | Manage own blocked personas |
| `/dating/unblock/<id>` | POST | Remove an initiated block |
| `/dating/report/<id>` | GET/POST | Request moderation |
| `/dating/pause` | POST | Pause / resume discovery |
| `/dating/delete` | POST | Delete dating persona (not the account) |
| `/dating/messages/<id>` | GET/POST | Private text conversation for reciprocal active adults |
| `/dating/messages/report/<message_id>` | GET/POST | Confidential recipient report |
| `/dating/moderation/messages` | GET | Admin-only reports queue |
| `/dating/moderation/messages/<report_id>/review` | POST | Admin hide/dismiss decision |

State-changing actions require logged-in accounts and CSRF tokens; the
existing application and route-specific rate limits remain active.

## Data migration

The new revision is `f1a9c3de7b21` after `63f21ac4db09`.
It adds `age_confirmed_at`, `show_profile_photo`, `dating_blocks` and
`dating_interests`. All existing member and dating-persona records remain
intact. **No older persona is silently marked age-confirmed or
photo-sharing-enabled**.

The target production database is the dedicated Aiven PostgreSQL database
`myplatoon`. Since configuration is deferred, do **not** switch Vercel or
run production migration until the user is ready. When ready, use the
protected GitHub Actions **Apply MyPlatoon production migrations** UI
workflow described in `DEPLOYMENT.md`. Back up user data and confirm the
old Neon-to-Aiven transfer if it exists before switching database URLs.

## Testing

- `tests/test_dating.py`: older functionality and age-confirmation edits.
- `tests/test_dating_v2.py`: adults-only self-attestation, profile/photo
  privacy, two-way blocks, deletion, preference compatibility and mutual
  interest consent.
- Run `python -m pytest -q tests/test_dating.py tests/test_dating_v2.py`.
- `.github/workflows/national-tests.yml` also runs the entire project
  test suite on pushes.

## Remaining work

This is not a substitute for dedicated age verification, independent abuse
reporting teams, intimate-content moderation, consent education or
anti-harassment controls. Before a public nationwide Dating launch, perform
a manual safety review, verify the age-verification approach, assess
retention/deletion requirements under applicable privacy laws, and test
mobile usability under real network conditions.
