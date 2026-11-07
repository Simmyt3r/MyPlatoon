# MyPlatoon: secure Aiven setup and ongoing migrations

## Production shared rate limiting (Vercel / Redis)

MyPlatoon uses Flask-Limiter. The default `memory://` backend is **not shared**
between serverless instances and must not be considered adequate protection
for a public launch. Redis is already a Python dependency.

1. Provision a managed Redis service that can be reached from your deployed
   Vercel functions. Prefer `rediss://` (TLS) when offered by your provider.
   Use the provider's actual URI, including credentials, port and database;
   never store it in GitHub or paste it in an issue.
2. In Vercel Production environment variables, set
   `RATELIMIT_STORAGE_URI` to the secret Redis URI. Leave
   `REQUIRE_SHARED_RATELIMIT=false` initially, and redeploy.
3. From a trusted operator environment that has the production Redis URI,
   test network connectivity with a Redis client. A URL being configured
   does **not** prove that Redis is reachable from Vercel.
4. Set `REQUIRE_SHARED_RATELIMIT=true` in Vercel, then redeploy.
   The application rejects startup if a Redis storage URI is not configured.
   Do this only after the service is provisioned and reachable.
5. In an operator environment with those same two variables exported, run:

   ```bash
   python scripts/check_shared_ratelimit.py
   ```

   Exit code 0 confirms the URI is valid, strict enforcement is enabled,
   and Redis responded to a time-bounded PING **from the machine running
   the check**. This does not certify Vercel's own network access or
   multi-instance counter consistency.
6. In Admin → Recruitment & Growth Insights, confirm both the Redis URI
   and strict enforcement indicators. Exercise a test-only rate-limited
   endpoint from separate Vercel instances to verify shared counters,
   then review login, registration and reset routes for unexpected
   429 responses. Do not hammer production login endpoints.
7. Keep a rollback plan: if Redis becomes unavailable, investigate provider
   health and network reachability. Do not silently fall back to per-instance
   counters while claiming global protection.

**Status wording matters:** configured, reachable, strictly enforced and
confirmed across instances are four different levels of confidence.
The public site and this documentation do not claim that a managed Redis
instance has already been provisioned.

---

## Liveness versus readiness monitoring

Monitoring should make a distinction between **a Python function that responds**
and **a deployment that is safe to receive user traffic**.

- `GET /health/live`: returns `200 {"status":"alive"}` without connecting to
  PostgreSQL, Redis, user sessions, or the application layout. This probe may
  stay green during database outages and must **not** be treated as proof that
  registration, payments, or game scoring are working.
- `GET /health/ready`: uses a read-only `SELECT 1` to check PostgreSQL.
  In production it also requires strict shared rate-limit configuration and
  a time-bounded Redis `PING`. Return `200` only when all required dependencies
  pass; otherwise return `503` with a sanitized `degraded` response.
- Both endpoints set `Cache-Control: no-store`. Degraded readiness includes
  `Retry-After: 60`. Neither discloses credentials, connection hostnames, user
  information, or stack traces. Redis checks can incur a network connection,
  so monitor readiness on a moderate cadence rather than on every page request.

Example check:

```bash
curl -i https://myplatoon.vercel.app/health/live
curl -i https://myplatoon.vercel.app/health/ready
```

**Rollout warning:** Existing production deployments without Redis may return
`503` from **readiness only** even though their public homepage and other
features still work. This is intentional: the readiness probe must not claim
that security prerequisites have been met. A `503` does not automatically
cause Vercel to block traffic unless you explicitly wire it to traffic
routing or an external load balancer. Review your monitoring/alert behavior
before integrating the readiness endpoint into deployment gates.

---

## Graceful dependency failure policy

User experience and security have different fallback requirements:

| Dependency failure | User-facing behavior | Security rule |
| --- | --- | --- |
| Aiven database unreachable or a SQL query fails | HTML or JSON 503, `Retry-After: 60`, no-store, link to the public landing | Never invent account state, credentials, saved changes, certificate progress, or deal history |
| Shared Redis temporarily unreachable | HTML or JSON 503 for requests hitting the limiter | Never fall back silently to per-instance memory counters or skip protections on login and state-changing requests |
| Cloudinary photo upload unavailable | Existing validated form displays a retry message; unrelated profile fields can still be saved | Do not persist an invalid photo URL or falsely announce an upload |
| YouTube playback blocked | Lesson stays incomplete until verified server-side watch progress is sufficient | Do not issue an unearned certificate |
| Production migration missing | Admin should run the reviewed backup-and-migration procedure; release gate fails | No automatic schema modification by ordinary user requests |

The outage page is generated without the standard database-backed layout or
context processors, so a failed query cannot recursively crash the error UI.
The public landing at `/` intentionally remains database-independent.
Do not use an expired or speculative cache to fill privacy-sensitive member,
application, financial, assessment, or authentication data.

**Recovery verification:** reproduce dependency failures in a test environment
and check that the user gets a safe 503 (or explicit upload error), no private
configuration is returned, no unconfirmed write is reported as successful,
and the feature works once the dependency is restored. Do not simulate
database or Redis failure against live users.

---

## First-time setup on Vercel

The MyPlatoon Flask app cannot persist boot-critical environment variables
across Vercel serverless invocations. **One-time bootstrap configuration in
Vercel is mandatory**; no public form can securely save the database URL or
Flask signing secret before the database exists.

1. In Aiven, provision PostgreSQL with a database named `myplatoon`. Confirm
   PostGIS extension privileges and the expected existing records/backups.
   **If replacing a provider's database, data is NOT copied automatically**:
   export and import the data separately before running migrations.
2. In **Vercel → Project → Settings → Environment Variables → Production** set:
   - `FLASK_ENV=production`
   - `SECRET_KEY` to a unique, random **32+ character** secret (generate with
     `python -c "import secrets; print(secrets.token_urlsafe(48))"`).
   - `AIVEN_DATABASE_URL` to the PostgreSQL URL for **myplatoon** using
     `?sslmode=require` or stronger. This is privileged and never submitted
     to the app's public pages.
   - `AUTO_CREATE_TABLES=false`.
   - `SETUP_TOKEN` to a separate 32+ character random token, also generated
     securely. This token authorizes **only the first** schema migration and
     initial admin creation.
   - Optional: `APP_BASE_URL=https://myplatoon.vercel.app`.
3. Redeploy the latest `main` branch from the Vercel dashboard so these
   environment variables reach the serverless function.
4. Open **https://myplatoon.vercel.app/setup**. Enter the private
   `SETUP_TOKEN`, first admin name/email, a 16+ character admin password,
   and backup confirmation. The route rejects unknown or partial legacy
   databases; it never drops existing accounts.
5. Once successful, remove `SETUP_TOKEN` from Vercel and redeploy.
   Even if the token remains set accidentally, the bootstrap form is locked
   whenever an administrator exists. Do not leave the token exposed.
6. Log in as the admin, visit **/setup** and add your Cloudinary cloud name,
   API key and secret. These values are encrypted at rest in Aiven and
   never returned to the browser, and can be changed without redeploying.

## Future releases: admin-controlled migration

1. Review the committed Alembic migration files in GitHub.
2. Back up Aiven and verify the snapshot is restorable.
3. Sign in with an active MyPlatoon administrator account.
4. Open **https://myplatoon.vercel.app/setup** (also linked from Admin Dashboard).
5. Check the backup acknowledgement, type `MIGRATE MYPLATOON`, confirm
   your admin password and submit. Only forward migrations to the committed
   revision `head` are allowed. The page displays the installed revision.
6. Confirm normal login, profile, jobs and moderation workflows afterward.

The app checks for concurrent PostgreSQL migrations using an advisory lock
and validates the resulting schema and required indexes. Web requests have
Vercel function time limits (currently configured in `vercel.json`). For a
large database or a migration that times out, **do not repeatedly retry
blindly**. Inspect database state and use the protected GitHub Actions
migration workflow or a dedicated operator environment for long upgrades.

## What the admin can and cannot configure

| Configuration | Where it belongs | Why |
|---|---|---|
| Aiven PostgreSQL URL | Vercel Production environment | Needed before the app can query the database |
| `SECRET_KEY` | Vercel Production environment | Signs browser sessions, CSRF tokens; derives encryption keys |
| `SETUP_TOKEN` | Temporary Vercel Production environment | One-time initial admin claim |
| Cloudinary credentials | Admin `/setup` form | Stored encrypted in Aiven, dynamically loaded for uploads |
| Future DB schema versions | Admin `/setup` form | Runs checked-in forward-only migrations |

**Keep `SECRET_KEY` stable.** Changing it invalidates existing user sessions
and the encryption of Cloudinary credentials. Re-enter these credentials
after an intentional key rotation. A database backup without the stable
external signing key cannot decrypt stored Cloudinary values.

No connection credentials are committed to GitHub. No live Aiven database
is migrated by code review, GitHub merge, or SQLite CI alone; migration
occurs only after a properly authorized operator submits `/setup`
(or the separate protected GitHub Actions workflow).


## Troubleshoot "Could not reach the database"

The connection URL has passed the initial syntax/database/SSL checks, but
PostgreSQL has not accepted the actual connection. The setup page now displays
a sanitized `DB_*` error category and a corresponding next step, without
showing any credential, host, or database connection string.

- `DB_AUTH`: The Aiven login was rejected. In the Aiven Console open
  PostgreSQL → Overview → Connection information, and copy the **current**
  Service URI. If building the URL by hand, percent-encode special characters
  in the password. Never send the URI to a support conversation.
- `DB_MISSING`: Create the `myplatoon` database in the chosen service.
- `DB_DNS`: Verify the hostname copied from the current Aiven service.
  Private-only hostnames will not work from ordinary public Vercel functions.
- `DB_REFUSED`: Verify the Aiven service is RUNNING and use the
  **service-specific port** from the Aiven Console, not an assumed 5432.
- `DB_TIMEOUT`: Review Aiven inbound IP allowlists, public access and VPC
  settings. Vercel functions do not have fixed outbound IPs unless a static
  egress option is configured. Do not permanently widen a production
  firewall merely to make a connection test pass.
- `DB_TLS` / `DB_ACCESS`: Verify `sslmode=require`, TLS credentials,
  database role permissions and Aiven network policy.
- `DB_LIMIT`: Check the Aiven service's connection count and health.
- `DB_PERMISSIONS`: The database role must be able to inspect schema and
  apply the migration DDL. Use a restricted dedicated migration role if
  appropriate.
- `DB_OTHER`: Review Vercel's Production **Runtime Logs** for the sanitized
  error category, then inspect the Aiven service's connection logs privately.

For all changes to Vercel environment variables, explicitly redeploy the
Production deployment. The old deployment may still be using earlier values.

**Security:** Never paste the complete Aiven URI, `SECRET_KEY`, or
`SETUP_TOKEN` into GitHub issues or chats. When you can open the first-admin
wizard, take an Aiven backup before applying a migration.


## Troubleshoot "Setup request denied (400)"

A 400 on submitting `/setup` is usually an HTTP/form security problem,
not proof of an Aiven connectivity failure.

- If the page says **Setup form security check failed**, it will explain
  whether the CSRF token was missing, expired, or did not match the browser
  session. Do not disable Flask-WTF CSRF protection.
- Reopen `https://myplatoon.vercel.app/setup` in a fresh tab, keep cookies
  enabled and submit the newly loaded form. Do not reuse a form loaded before
  the latest Vercel deployment or before a production `SECRET_KEY` change.
- Keep the same production `SECRET_KEY` consistently across deployments.
  Changing it invalidates existing signed browser sessions and CSRF tokens.
- If the page says **The setup action was not recognized**, use the buttons
  on the current `/setup` page rather than posting a custom request.
- A GET navigation to `/setup` should not require CSRF verification. If
  a simple GET results in 400 even in a fresh tab, inspect Vercel runtime
  logs for the request method, status and endpoint (never paste cookies
  or secrets into support tickets).

A rejected CSRF request cannot start migrations or create administrators.

## Troubleshoot repeated "The form security token was missing" after fresh reload

The first-run and admin setup forms already include a hidden CSRF field. A
missing token means the submitted request was not carrying that field. It is
**not** fixed by removing CSRF or changing the Aiven connection string.

1. Open a fresh `/setup` page on the canonical
   `https://myplatoon.vercel.app` hostname. Do not submit from a cached page
   or a different deployment preview.
2. Press **Test form submission** on that page (or **Test form security**
   on the CSRF error page). This read-only request uses the exact same CSRF
   and browser session protections, but does not inspect, migrate, or write
   to the database.
3. If the test **passes**, return to `/setup`, enter the initial admin
   fields, and submit the current form. Never send setup tokens in chat.
4. If it **fails**, the error screen now shows a safe transport code:
   - `EMPTY_BODY`: no body was sent;
   - `NO_PARSED_FIELDS`: Flask could not see any HTML form fields;
   - `CSRF_FIELD_OMITTED`: form fields arrived, but the CSRF input was missing;
   - `EMPTY_CSRF_FIELD`: the CSRF input arrived with no value;
   - `UNSUPPORTED_CONTENT_TYPE`: this was not a browser-encoded form;
   - `CSRF_VALIDATION`: a token was posted but verification failed.
5. For persistent transport errors, open browser DevTools → Network and
   inspect the failed **POST** request to `/setup` or
   `/setup/form-check`. Look only at the request method, request
   `Content-Type`, and whether the **name** `csrf_token` appears among
   the form field names. Do **not** copy the token, cookie or other values.
   This helps distinguish missing form submission data from a stale session.
6. If the browser sends the field but Vercel does not receive it, inspect
   the Vercel Deployment → Runtime Logs and check routing/middleware, and
   confirm that the production deployment matches the latest Git commit.

CSRF protection remains enforced. The probe cannot grant admin access or
execute a migration.


## Fix for secure HTTPS form submissions with a missing Referer

In deployments before this fix, the standalone `/setup` blueprint set
`Referrer-Policy: no-referrer` on its GET form response, while the global
Flask-WTF `CSRFProtect` extension (with `WTF_CSRF_SSL_STRICT=True` by default)
required a same-origin `Referer` header for all HTTPS POSTs. This
contradictory configuration caused otherwise valid setup and form-check
submissions to return HTTP 400.

The error handler also mapped **any** error containing "missing" to
"form security token was missing", including the **separate** Flask-WTF
"referrer header is missing" error. The symptom was a nonempty posted
`csrf_token`, an existing session cookie, and the misleading
`CSRF_VALIDATION` diagnostic.

**Fix:** The setup blueprint now sends `Referrer-Policy: same-origin`.
Browsers send the referrer for same-origin setup form posts while suppressing
it to external sites. Global CSRF validation, HTTPS strict referrer checking,
and signed session requirements all remain **enabled**. Missing and
cross-origin referrers are still rejected with explicit, safe
`HTTPS_REFERRER_MISSING` / `HTTPS_REFERRER_MISMATCH` diagnostics.

After redeploying, open a fresh `https://myplatoon.vercel.app/setup`
page and use **Test form submission**. Its POST should succeed on a normal
browser that sends a same-origin referrer. If the browser still strips
the referrer (for example, a privacy extension or an embedded browser),
open the site in a normal first-party browser tab, inspect only request
header **names**, and keep CSRF protection enabled. No production
database write is performed by the test route.


## Verify Cloudinary credentials from the Admin UI

Once an administrator has saved `CLOUDINARY_CLOUD_NAME`,
`CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` in
`/setup`, they can choose **Test Cloudinary connection** and
confirm their administrator password. This makes a **read-only
Cloudinary Admin API ping** using the encrypted database settings
(env variables are used only when no saved value exists for a key).
It does **not** upload or delete images, change keys, or execute
database migrations. Only the sanitized success/failure message
is displayed; the raw SDK response is never logged or shown.

A successful ping verifies credentials and API reachability; it
does not guarantee that a particular photo upload will succeed
or that the account has free storage quota. After a successful
ping, test a small JPG through **Profile → Edit Profile**.

Members now see a local preview of their selected photo before
they save, with an immediate warning for unsupported MIME types,
empty files, or files larger than 6 MB. The server also validates
and re-encodes the image; browser-side previews are not security
enforcement. Profile photo changes are persisted in PostgreSQL,
while the image file is stored only in Cloudinary.


## School and employer recruitment workspace

Schools should register through `/jobs/employers/register` and choose
**School or educational institution**. That creates a separate employer
account instead of an NYSC member profile. After logging in, the school
lands on **Recruitment dashboard** (`/jobs/employer`), not on the community
feed. The header, sidebar and mobile navigation show only:

- **Overview & vacancies** — hiring status, vacancy list and recent applications.
- **Applications** — a private inbox across all the school's job listings,
  filterable by vacancy or application status; change an application to
  submitted, shortlisted, declined or hired where permitted.
- **Post vacancy** — create a paid job listing.
- **Organisation settings** — update the school's hiring profile.

The shared social feed, NERD pages, platoons, dating, suggested members,
community footer and public jobs browsing links are excluded from the
school's recruitment navigation. Existing NYSC members who also manage
an organisation get the focused navigation on recruitment screens and
keep their personal member workspace elsewhere. Other employer types
use the same hiring-focused navigation, without changing the
separately supported gig-owner workflows.

Application inbox queries are always restricted to the current
employer's own listings, including vacancy/status filtering. Existing
server-side ownership checks still apply to applicant detail and status
changes. Applicants' contact details remain recruitment-only.

**Important:** Employer verification and listing review are intentionally
separate from self-service member registration. Registration creates
the employer workspace immediately but does not bypass employer/listing
moderation or publish vacancies automatically. No database migration is
required for this navigation and inbox update.


## Silabs Academy — learning platform and certificates

After this release, open **Admin Dashboard → Manage Silabs Academy**
(`/learn/admin`) to create a course, enter the title, summary, detailed
learning outcomes and difficulty, and save it as a **draft**. Add an ordered
series of lessons by pasting a valid **HTTPS YouTube watch, share, Shorts or
embed URL** for each lesson. Titles and descriptions are editable. Publish
only once at least one lesson exists. Unpublished courses are hidden from
normal learners. Each course may be unpublished later.

Members browse **Silabs Academy** (`/learn/`), view course details, watch
privacy-enhanced embedded YouTube videos, and press **Mark complete** after
each lesson. Records are stored per user and lesson. A downloadable PDF
certificate with a unique ID and QR verification link is issued automatically
**once all lessons in a published course are marked complete**. Certificates
remain valid when the course is unpublished. Award records store immutable
learner name, course title, lesson count and issuance date. After certificates
are issued, lessons are locked so the awarded learning series does not change.
Administrators can still edit course details or create a new course edition.

The public verification endpoint `/learn/certificates/<uuid>` displays
the certificate holder's name, course and date to anyone possessing the
unguessable certificate ID or QR link. **Downloads are private** to the
recipient and platform administrators. A certificate is a record of
**self-reported completion of video lessons**, not proof of viewing,
proctored examination, competence or professional licensing. For such
claims, add a verified assessment workflow.

The Silabs logo mark is included at
`app/static/img/silabs-academy-logo.svg`, and the PDF is branded
**SILABS & CO TECHNOLOGIES LTD.**.
Set `APP_BASE_URL=https://myplatoon.vercel.app` in Vercel Production for
QR codes to resolve reliably to the correct public hostname. No Cloudinary
configuration is needed for YouTube lessons or certificate PDFs.

**Production database action required:** this feature adds four new
tables with Alembic revision `e2c5a84f9b31`. After deployment,
use the existing admin **Database & API Setup → Apply reviewed migrations**
workflow on a backed-up database before opening the Academy. Production
does not auto-create the tables. Never run migrations automatically in
request handlers. The schema release check expects this revision.

## Minimum video playback before marking a lesson complete

Silabs Academy requires **90 seconds (1 minute 30 seconds) of accumulated
active video playback per lesson** before the completion endpoint will
record a lesson. The YouTube IFrame Player API reports playing/paused/
buffering and video playback position. The browser sends checkpoints
about every five seconds only for a visible tab. PostgreSQL tracks
progress **per learner and lesson**, using server time and sanity checks
on consecutive video positions; page reloads preserve earned seconds.

Pausing, buffering, leaving the browser tab, seeking ahead or sending
a burst of fake time requests will not earn immediate credit. Playback
can resume later and repeated viewings contribute to the 90 seconds.
A short video must be replayed as necessary; administrators should
prefer lessons at least 90 seconds long.

The completion endpoint re-checks the stored server-side watch time
before saving a completed lesson or automatically issuing a Silabs
certificate. Older already-completed lessons/certificates remain valid.
Signed-in employers still cannot mark learning progress.

**Security limitation:** IFrame playback is observed by a user's own
browser. It is practical friction against skipping and casual bypass,
but a manipulated client can still forge credible timed playback
reports. A supervised exam or trusted-video-attestation service would
be necessary to independently certify attention or skill acquisition.

**Production migration:** revision `f49a1d8e2c90` adds the
`learning_watch` table after `e2c5a84f9b31`. Deploy, back up Aiven,
then run **/setup → Apply reviewed migrations** as admin. Do not
run automatically on incoming requests.

## Digital interplatoon microgames (replaces physical placement reports)

The Games page at `/platoons/games` now hosts **ten small,
server-scored activities completed inside MyPlatoon**:

1. **Daily Roll Call** — a successful daily login or Check In button.
2. **GOAL Rush** — members tap **GOAL!** during a live competition.
3. **Academy Graduate** — a newly completed Silabs Academy course.
4. **Lesson Sprint** — a newly completed Academy lesson (subject to the
   existing 90-second playback requirement).
5. **Profile Ready** — verify a MyPlatoon profile is at least 50% complete.
6. **Photo Finish** — verify a Cloudinary profile photograph is present.
7. **NYSC Camp Quiz** — one correct camp-knowledge question daily.
8. **Tech Trivia** — one correct safety/technology question daily.
9. **Number Sprint** — solve a brief arithmetic problem each day.
10. **Team Cheer** — submit one cheer daily.

Participation records are created on real authenticated actions, never
submitted on behalf of a team leader. Daily game contributions are
**capped at one per eligible user per game per Nigeria calendar day**;
profile/photo milestones count **once per round**. Member state, serving
status and platoon are checked on the server. Answers are validated
server-side; source-driven events cannot be forged via the Games UI.

The competition calendar still begins **15 November 2026** and repeats
every three months on 15 February, May, August and November until the
30th (or February's last day). Scores are segregated by state, service
year, batch and stream. Each game ranks platoons by accumulated member
contributions, awarding 10 points for the leading platoon, 9 for second
and so forth. Equal positive contribution totals share a rank and
score; zero contributions earn zero. Both contribution counts and
competition points are displayed.

Historical **physical-event result submissions have been disabled (HTTP
410)** and no longer appear on the Games page or contribute to this
new digital leaderboard. Elected leaders, voting rules and the 14-day
badge system remain intact.

**Operator action:** Migration `j61a7f3d9c02` follows
`h50d2e9a7c14` and adds `platoon_game_activities` with a database
uniqueness constraint to prevent duplicate daily/round participation.
Back up the production database, deploy the new code and apply the
reviewed migration via `/setup` before enabling the Games page. The
read-only release schema check also verifies that the uniqueness constraint
on `(period_start, game_key, user_id, score_day)` exists, so concurrent
submissions cannot silently double-credit one game/day.
Existing manual event rows are retained for data preservation but
not used for the new digital scoring.



## Recruitment pilot insights and safer sign-in defaults (November 2026)

Open **Admin → Recruitment & Growth Insights** (`/admin/insights`) to
review live database counts: registrations, recent login timestamps,
employers and approved schools, published/open vacancies, applications,
shortlists and recorded hires, plus rolling weekly trends. No new
database migration is needed. This **admin-only, no-store** dashboard
exposes aggregated recruitment data without applicant phone numbers,
emails or cover notes. Revenue is **not** displayed because no paid
billing provider or verified payment records are connected. Follow
`PILOT_RECRUITMENT.md` for a strictly limited first paid-product test.

**Session security:** Flask session persistence is reduced from 365 days
to **12 hours**. Remember-me is **unchecked by default** and, when
explicitly selected, creates a cookie lasting at most **14 days**.
Existing remembered sessions may have been issued under the older
policy; for immediate mass revocation, plan a controlled credential/
session invalidation strategy rather than rotating SECRET_KEY without
preparation (encrypted setup credentials also depend on it).

**Distributed rate limiting:** Flask-Limiter's `memory://` backend is
per-worker and is not reliable behind Vercel serverless instances.
Set `RATELIMIT_STORAGE_URI` in Vercel Production to the **TLS-protected
Redis provider URL** (for example `rediss://...`) using a secret
environment variable. Never commit that URI to GitHub. A Redis client
dependency is included. Test a real rate-limited endpoint from multiple
instances after deployment. The admin Insights page warns when there
is no configured shared storage, but cannot certify Redis connectivity.

When Redis is confirmed and login/register requests have been tested,
set `REQUIRE_SHARED_RATELIMIT=true` in Vercel. That opt-in production
startup gate rejects missing/non-Redis storage and prevents future
silent fallbacks. Keep it false only during the transition.
An additional **keyed-hash per-account login throttle** complements
the IP rate limit; attempted email values are no longer copied into
failed-login audit details. Until Redis is configured, neither limit
is globally shared and this remains an unresolved security risk.
