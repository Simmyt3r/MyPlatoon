# MyPlatoon: secure Aiven setup and ongoing migrations

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
