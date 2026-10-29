# Security

## Authentication
- Production startup refuses missing, predictable or shorter-than-32-character
  `SECRET_KEY` values; configure a unique secret before deploying this change.
- Post-login redirects accept only safe internal paths, including after URL decoding.
- Logout requires an authenticated POST with a CSRF token (GET cannot log users out).
- Passwords hashed with Werkzeug's `generate_password_hash` (scrypt/pbkdf2), never stored
  or logged in plaintext.
- Session cookies are `HttpOnly`, `SameSite=Lax`, and `Secure` in production.
- Login and registration endpoints are rate-limited (Flask-Limiter) to slow down credential
  stuffing / brute-force attempts.
- Suspended accounts cannot log in even with correct credentials.
- The first administrator account can be created automatically on startup from
  `ADMIN_INIT_EMAIL`/`ADMIN_INIT_PASSWORD` environment variables (see DEPLOYMENT.md). There
  is no hardcoded default admin password anywhere in the code — nothing is created until
  you explicitly set both variables yourself, with a password of your choosing. The
  password is rejected (and no account created) if it's under 8 characters. This is
  idempotent: it only ever creates the account once and never resets a password you've
  since changed, so it's safe to leave these variables set permanently. The optional
  `scripts/seed.py` demo script is separate and uses an obviously-fake, publicly-documented
  demo password (`ChangeMe123!`) — never point that script at a real production database.

## Authorization
- `@login_required` (Flask-Login) gates every member-only route.
- A dedicated `admin_required` decorator gates every admin route and returns **403**, not
  a silent redirect, for authenticated non-admins.
- Ownership checks are enforced server-side wherever a member edits their own data (e.g.
  business edit/delete confirms `business.profile_id == current_user.profile.id` or admin).
- Editing a profile always operates on `current_user.profile` — there is no `profile_id`
  parameter a malicious request could substitute to target someone else's data.

## CSRF
- Flask-WTF's `CSRFProtect` is enabled globally in development and production (it's
  intentionally disabled only in the automated-test configuration, where nothing hits a
  real browser).
- Every form includes `{{ form.hidden_tag() }}` or an explicit `csrf_token` hidden field.

## Privacy by Default
- New profiles default to `profile_visibility=platoon`, `phone_visibility=private`,
  `whatsapp_visibility=platoon`, `address_visibility=private` — nothing sensitive is public
  until the member opts in.
- A profile that is private, platoon-only-and-viewed-by-a-guest, or not yet approved
  returns **404** (not 403) on its public URL, so unauthorized visitors can't distinguish
  "doesn't exist" from "exists but you can't see it."
- Contact fields (`phone_number`, `whatsapp_number`, `address`) are resolved through a
  single `privacy_service.serialize_contact()` function — visibility logic lives in one
  place, not scattered across templates.
- The PDF album applies the same rule set as the "platoon member" viewing level: a field
  the member marked private never appears in the album, regardless of who requests it.

## File Uploads
- Extension allow-list (`jpg`, `jpeg`, `png`, `webp`) checked in addition to the browser-
  supplied MIME type.
- Content is actually opened and verified with Pillow (`Image.verify()`) — a malicious
  file with a spoofed `.jpg` extension containing something else is rejected.
- Uploaded images are re-encoded (not passed through as-is) before upload, which strips
  EXIF/metadata and caps dimensions.
- File size is capped (`MAX_CONTENT_LENGTH`, default 6MB).
- Filenames from the client are never trusted or used directly — a fresh UUID-based
  Cloudinary `public_id` is generated for every upload.
- Images are never written to the application server's filesystem.
- If `CLOUDINARY_CLOUD_NAME`/`CLOUDINARY_API_KEY`/`CLOUDINARY_API_SECRET` aren't set, or the
  upload call itself fails (bad credentials, network issue, quota), the upload is rejected
  with a clear message shown to the person uploading — never a silent swap to a placeholder
  image and never an uncaught 500. The rest of the form (profile/business fields) still
  saves even if the photo specifically fails, so one broken upload can't discard everything
  else someone just filled in.

## SQL Injection / XSS
- All database access goes through SQLAlchemy's ORM query builder (parameterized
  queries) — no raw string-interpolated SQL anywhere in the codebase.
- Jinja2 auto-escapes all template output by default; user-supplied text (biography,
  business description, etc.) is never marked `|safe`.

## CSV Exports
- Exported member data is escaped when it could be interpreted as a spreadsheet
  formula, including values beginning with `=`, `+`, `-` or `@` after whitespace.

## Audit Logging
Every security-relevant action is recorded in `audit_logs`: logins (success and failure),
registrations, profile approvals/rejections/suspensions/deletions, category/announcement
changes, album generation, and data exports — each with actor, timestamp, and IP address.
Logs are append-only from the application's perspective (no UI to edit/delete an entry).

## What Is Never Exposed
- Password hashes are never included in any template context or API response.
- Database credentials and Cloudinary/API secrets live only in environment variables,
  never in source control (`.env` is gitignored; only `.env.example` with placeholders
  is committed).
- Stack traces are never shown to visitors in production; the global 500 handler renders
  a branded error page and logs the full exception server-side.

## Dating Feature Safety
- Opt-in only: a dating persona is never auto-created from a member's main profile, and
  requires the member's *main* profile to already be admin-approved -- the same trust bar
  the rest of the platform uses, rather than inventing separate identity/age verification.
- Dating data is fully isolated: it's never returned by directory search, never included
  in the PDF album, never exported in the admin CSV, and doesn't affect a member's public
  profile visibility settings.
- A match only ever notifies both people when it's genuinely mutual -- both sides ranked
  each other in their own top picks. Nobody is notified about, or shown as a "fan of",
  someone who hasn't reciprocated.
- Members can pause their persona at any time, which immediately removes them from
  everyone else's matching pool without deleting their data.
- A "Report" action immediately hides the reported persona from all matching (not just
  from the reporter) pending admin review, and admins can clear the report or permanently
  remove the persona from `/admin/dating`.
- Can be disabled platform-wide via `ENABLE_DATING=false` without touching any other part
  of the app.

## Album Storage
The generated album PDF is stored directly in the database (`AlbumVersion.pdf_data`) as
the source of truth for downloads, with Cloudinary treated as a best-effort *secondary*
copy that's never allowed to block generation or break downloads if it fails. This is
deliberate: Cloudinary's free/default tier blocks public delivery of PDF and ZIP files as
an anti-malware precaution, and that restriction is account-level (it overrides a file's
own access settings, so switching to signed URLs doesn't bypass it) — relying on
Cloudinary alone for something admins and members need to reliably download would make
that feature fragile in a way that's outside this app's control. See DEPLOYMENT.md for
what to do if you specifically need to enable Cloudinary delivery anyway (e.g. to share a
direct link outside the app).

## Known Trade-offs
- Rate limiting uses in-memory storage by default (`RATELIMIT_STORAGE_URI=memory://`),
  which resets on every serverless cold start and doesn't share state across concurrent
  Vercel function instances. For stricter production rate limiting, point
  `RATELIMIT_STORAGE_URI` at a shared Redis instance.
- Email verification on registration is not implemented in this version — any syntactically
  valid, non-duplicate email can register. Consider adding a verification step if this
  becomes a concern for your deployment.
