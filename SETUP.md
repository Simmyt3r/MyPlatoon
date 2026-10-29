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
