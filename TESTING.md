# Testing

## Running the suite

```bash
pip install -r requirements.txt
pytest
# with coverage:
pytest --cov=app --cov-report=term-missing
```

Tests run against an **in-memory SQLite database** (see `TestingConfig` in
`app/config.py`) and never touch a real Postgres/Cloudinary — image upload tests
exercise validation logic directly rather than hitting the network.

## Coverage (97 tests)

**`tests/test_auth.py`** — registration (success, duplicate email, password mismatch,
weak password rejected), login (success, wrong password, nonexistent user, suspended
account), logout requires auth, password never stored in plaintext.

**`tests/test_profile.py`** — dashboard requires login, profile edit updates fields and
skills, completion-percentage scoring, submit-for-approval threshold enforcement, privacy
settings persist, private/pending profiles are not publicly viewable.

**`tests/test_business.py`** — create/update a business, ownership enforcement (a member
cannot edit another member's business - 403), business directory search by category and
by free-text query.

**`tests/test_admin.py`** — non-admins and guests cannot reach `/admin/*` (403 or
redirect-to-login), admin approve/reject (with reason)/suspend/reinstate flows, a
non-admin cannot approve someone else's profile, category management.

**`tests/test_album.py`** — album generation includes only `approved` profiles, PDF output
is well-formed (`%PDF` header), only admins can trigger generation, version labels
increment (`1.0` -> `1.1`), the Cloudinary upload's public_id always has a `.pdf`
extension (otherwise Cloudinary can't infer a content type and serves it as generic
binary data), downloads set the correct `Content-Type`/`Content-Disposition` headers,
a Cloudinary upload failure never blocks album generation, and — the actual end-to-end
regression for a real production incident — a newly-generated album downloads correctly
even when Cloudinary's account-level PDF/ZIP delivery restriction actively blocks the
file, since downloads are served from the database rather than depending on Cloudinary.

**`tests/test_security.py`** — cross-user edit attempts are scoped to `current_user` and
can't affect other accounts, private/platoon-only profiles return 404 (not 403 - avoids
confirming existence) to unauthorized viewers, all admin routes reject unauthenticated
requests, CSRF is verified enabled in dev/prod configs, uploaded files are validated by
actual content (Pillow) not just extension/MIME claims, passwords are hashed
(scrypt/pbkdf2 prefix check).

**`tests/test_feed.py`** — reactions (add/toggle-off/change type), comments, login
requirements on both, unified search across members and businesses.

**`tests/test_admin_seeding.py`** — automatic admin account creation from
`ADMIN_INIT_EMAIL`/`ADMIN_INIT_PASSWORD`, idempotency, weak-password rejection, never
overwrites an existing account with the same email.

**`tests/test_profile_autoheal.py`** — every path that can create a `User` (registration,
CLI, auto-seed, demo script) also creates a companion `Profile`; a profile-less account
(e.g. from before this fix) self-heals transparently on next login rather than crashing.

**`tests/test_generic_platform_fixes.py`** — URL scheme normalization (bare domains get
`https://` prepended, both on save and defensively at render time for legacy data), the
short `/profile/<slug>` QR redirect resolves to the canonical profile page, generated QR
codes use that short URL, branding renders from config rather than hardcoded strings, and
image uploads fail with a clear user-facing message (not a silent placeholder swap or a
raw 500) when Cloudinary isn't configured or the API call itself fails.

**`tests/test_dating.py`** — persona creation requires an approved main profile,
compatibility scoring is symmetric regardless of argument order, mutual-match detection
works correctly for the "first mover" case (person A's ranking of a not-yet-existing
person B gets reciprocally refreshed once B joins -- this is the two-sided cascade fix,
covered explicitly since it was a real bug caught during development), both sides get
notified on a mutual match and nobody is notified one-sidedly, opposite-gender-only
matching, unapproved profiles are never matched as candidates, a paused persona is
excluded from new matching, pause/resume toggling, reporting hides a persona from
matching immediately, a user can't report themselves, admin can clear a report or remove
a persona, non-admins are blocked from the moderation queue, and the feature 404s
cleanly when `ENABLE_DATING=false`.

## What's deliberately NOT covered by automated tests

- Actual Cloudinary network calls (mocked out via the `CLOUDINARY_CLOUD_NAME` unset
  fallback path) — verify manually against a real Cloudinary account before production use.
- Actual Vercel serverless behavior — verify via the production testing checklist in
  `DEPLOYMENT.md` after each deploy.
- Visual/CSS regression — this is a server-rendered Bootstrap app; test manually across
  a phone-sized viewport and a desktop viewport after UI changes.

## Manual verification performed during development

Beyond the automated suite, the following were manually exercised end-to-end against a
running instance before considering the build complete:

- Full route smoke test across guest/member/admin roles (23 distinct routes, all 2xx)
- PDF album generation produces a real, multi-page, openable PDF with correct branding,
  table of contents, per-member sections with QR codes, and a business directory section
- PDF generation works correctly even when triggered **outside** an active HTTP request
  context (relevant if album generation is ever wired to a CLI command or scheduled job)
  — this surfaced and fixed a real bug during development (see git history / code comments
  in `app/services/qr_service.py`)

## Adding new tests

Fixtures live in `tests/conftest.py`:
- `app` — fresh Flask app + in-memory DB per test, with default business categories seeded
- `client` — Flask test client bound to `app`
- `db` — the SQLAlchemy extension, for direct model assertions
- `member_user`, `admin_user`, `approved_member` — pre-created users covering the three
  states most tests need
- `login(client, email, password=...)` — helper to authenticate in a test

Follow the existing pattern: one behavior per test function, assert on both the HTTP
response and (where relevant) the resulting database state.

## A note on test isolation

If you ever write standalone diagnostic scripts (outside pytest) that call
`app.test_client()`, avoid holding a single `with app.app_context():` block open across
*multiple* requests to different logged-in users. Flask caches the loaded user on
`flask.g`, which is tied to the app context rather than the request context — reusing one
long-lived app context across several test-client calls can make `current_user` "leak"
from an earlier request. Real deployments and pytest's per-test fixtures don't hit this
because each incoming request gets its own fresh context; it's specifically an ad hoc
scripting pitfall, not an application bug.
