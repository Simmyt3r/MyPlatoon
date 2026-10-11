# Deployment Guide

This guide walks through deploying MyPlatoon, the nationwide NYSC community, to **Vercel**, backed by
**Aiven PostgreSQL with PostGIS** and **Cloudinary** for image storage.

> Vercel's Python runtime is serverless: the filesystem is ephemeral and read-only at
> request time outside of `/tmp`. Nothing in this application writes to local disk for
> persistence — uploaded images go to Cloudinary, generated PDFs go to Cloudinary, and
> all structured data goes to PostgreSQL.

---

## Required: database upgrade for nationwide platoons

**Before exposing the new application on an existing database**, apply
the current migrations through revision `63f21ac4db09`. Simply deploying the new Python code will NOT alter
the old `profiles` table because SQLAlchemy `create_all()` adds missing
tables, not missing columns.

For dashboard-only setup:

1. Back up the production PostgreSQL database.
2. GitHub repository → Settings → Environments → `production`.
3. Add an environment secret `DATABASE_URL_UNPOOLED` containing the direct
   PostgreSQL migration connection string (not a pooled runtime connection).
4. GitHub → Actions → **Apply MyPlatoon production migrations** → Run workflow.
5. Confirm the run succeeds before redeploying the latest `main` build in Vercel.
6. In Vercel, set `APP_NAME=MyPlatoon`, `APP_SHORT_NAME=MyPlatoon`,
   `APP_BRAND_INITIALS=MP`, and a correct production `APP_BASE_URL` if
   branding or URLs were previously overridden in the project settings.

The migration script recognizes empty databases, old databases built using
`db.create_all()`, and installations with an Alembic version table. It never
assigns invented platoons to existing members. If it detects a partially
migrated schema, it aborts for manual review.

`FLASK_ENV=production` and `AIVEN_DATABASE_URL` are required for the new Aiven web runtime. The migration workflow reads only the direct connection secret
during an explicitly triggered, environment-protected GitHub Actions run.

---

## 1. GitHub Setup

1. Push this project to a GitHub repository.
2. Ensure `.env` is **not** committed — it's covered by `.gitignore`. Only `.env.example`
   (with placeholder values) should be in version control.

```bash
git init
git add .
git commit -m "Initial MyPlatoon deployment"
git branch -M main
git remote add origin https://github.com/Simmyt3r/MyPlatoon.git
git push -u origin main
```

## 2. Aiven Database Setup (already provisioned)

The connected Aiven service is `simmyt3r / pg-31f7f560`.
The dedicated database **`myplatoon`** and the **PostGIS** extension were
created and verified on 11 October 2026. Do not point this app at `defaultdb`.

In the [Aiven Console](https://console.aiven.io), open the service and
copy its PostgreSQL connection URL for database `myplatoon` (SSL required).
The connection password is private and **not in GitHub**.

**If your previous deployed app already has users**, back up and migrate the
old database first. A fresh database will have no old member accounts. See
[PPA_GIS_AIVEN.md](PPA_GIS_AIVEN.md) for the safe migration checklist.

## 3. Environment Variables

You will need the following (see `.env.example` for the full list with descriptions):

| Variable | Where to get it |
|---|---|
| `SECRET_KEY` | Generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `AIVEN_DATABASE_URL` | PostgreSQL service URL for **myplatoon** from Aiven Console; include `sslmode=require` |\n| `AUTO_CREATE_TABLES` | Set to `false` for production; use Alembic migrations |
| `CLOUDINARY_CLOUD_NAME` | From Cloudinary dashboard |
| `CLOUDINARY_API_KEY` | From Cloudinary dashboard |
| `CLOUDINARY_API_SECRET` | From Cloudinary dashboard |
| `APP_BASE_URL` | Your production URL, e.g. `https://your-myplatoon-deployment.vercel.app` |
| `FLASK_ENV` | `production` |

**Never commit real values for any of these.**

## 4. Cloudinary Setup

1. Create a free account at cloudinary.com.
2. From the dashboard, copy your **Cloud Name**, **API Key**, and **API Secret**.
3. No further configuration is required — the application uploads directly via the
   Cloudinary SDK using these credentials and organizes assets under `myplatoon/profiles`,
   `myplatoon/businesses`, and `myplatoon/albums`.
4. Optional: set upload restrictions (max file size, allowed formats) in your Cloudinary
   account settings as a second layer of defense on top of the application's own validation.

## 5. Vercel Project Creation

1. Go to vercel.com and import your GitHub repository.
2. Vercel auto-detects Flask via `requirements.txt` and looks for an `app` instance at a
   supported entrypoint — `wsgi.py` (which exports `app = create_app(...)`) is one of the
   recognized names, so **no `builds`/`routes` config is needed**. This project's
   `vercel.json` only sets `maxDuration` for the one function; it deliberately does not use
   the legacy `builds`/`routes` schema, which is no longer the recommended approach and can
   cause the deployed function to crash on every request.
3. In **Project Settings → Environment Variables**, add every variable from step 3 for the
   **Production** environment (and optionally **Preview**). This is required — a `.env`
   file in your repo is never read by Vercel (it's also gitignored, so it isn't even in
   your repo). If these aren't set here, the app has no database connection and every
   page that touches the database will crash.
4. Static assets (CSS/JS/images) are served from the `public/` directory rather than
   through Flask's own static handler, per Vercel's guidance for the Python runtime. The
   `public/static/` directory is already committed to this repo, pre-mirrored from
   `app/static/`. If you change anything under `app/static/`, run `python build.py`
   locally and commit the result before deploying — **don't** add a `pyproject.toml` to
   automate this: merely having a `pyproject.toml` present switches Vercel's Python build
   from `requirements.txt` to a `uv`-based resolver that requires a fully-formed PEP 621
   project file, which is easy to get subtly wrong and breaks the build entirely rather
   than just the one route. This project deliberately keeps only `requirements.txt`.

## 6. Deployment

```bash
# Option A: via the Vercel dashboard - click "Deploy" after import.

# Option B: via the Vercel CLI
npm install -g vercel
vercel login
vercel --prod
```

## 7. Aiven Schema Migration

Production no longer relies on `db.create_all()`. It does not upgrade
existing tables and can create a partly initialized database, so it now
defaults to disabled in production.

1. GitHub → MyPlatoon → Settings → Environments → `production`.
2. Set secret `DATABASE_URL_UNPOOLED` to the direct Aiven connection URL
   for **`myplatoon`**.
3. GitHub → Actions → `Apply MyPlatoon production migrations` → Run workflow.
4. Wait for a successful run. Verify the installed revision is
   `63f21ac4db09` (includes nationwide platoons, PPA records, member
   experience reports, and PostGIS index).
5. For new installations, create GitHub `production` secrets
   `ADMIN_INIT_EMAIL` and `ADMIN_INIT_PASSWORD` (16+ characters) and run
   Actions → **Bootstrap Aiven MyPlatoon administrator** → Run workflow.
6. Vercel → Settings → Environment Variables: set `AIVEN_DATABASE_URL`
   to the Aiven **myplatoon** URI; set `AUTO_CREATE_TABLES=false`.
6. Deploy the updated main branch through Vercel UI.

The workflow's `scripts/upgrade_nysc_schema.py` handles an empty database
or a verified legacy schema. It refuses partially initialized databases
rather than overwriting user records.

Important: Vercel's existing `DATABASE_URL` from another provider may
remain configured; `AIVEN_DATABASE_URL` has priority when set.

## 7b. Your First Admin Account

The simplest path: set `ADMIN_INIT_EMAIL` and `ADMIN_INIT_PASSWORD` in your Vercel
project's environment variables (Production). After the database migration, you can run the CLI admin bootstrap; setting
these variables also enables its initial-admin creation during startup only
when automatic bootstrap is enabled. It only ever runs once (it's a no-op if that email already exists) and never
overwrites a password you've since changed. Use a real password here, at least 8
characters — there's no default baked into the code, so nothing is created until you set
this yourself.

If you'd rather not put a password in an environment variable, create the account
interactively instead:

```bash
export DATABASE_URL="$DATABASE_URL_UNPOOLED"
flask init-categories   # only needed if AUTO_CREATE_TABLES is disabled
flask create-admin
```

## 8. Production Testing Checklist

After deploying, verify:

- [ ] The landing page loads at your production URL
- [ ] Registration -> login -> profile creation works end-to-end
- [ ] A profile photo upload succeeds and appears via a Cloudinary URL (check the image
      `src` in your browser's dev tools - it should point to `res.cloudinary.com`)
- [ ] An admin account can log in and approve a test profile
- [ ] The member directory and business directory search/filter/paginate correctly
- [ ] A public/platoon-visible profile is reachable at `/directory/member/<slug>`, and a
      **private** profile correctly 404s for a logged-out visitor
- [ ] Album generation (`/album/generate`, admin only) produces a downloadable PDF and the
      PDF opens correctly with QR codes that resolve to the right profile URLs
- [ ] Error pages (visit a nonexistent route) render the branded 404 page, not a stack trace
- [ ] `flask db upgrade` has been run against production and the schema matches the models

## Troubleshooting

### "This Serverless Function has crashed" / `FUNCTION_INVOCATION_FAILED`

This means the Python process itself threw an unhandled exception while handling a
request (not a build failure — the deploy succeeded, the crash happens at request time).
Work through these in order:

1. **Read the real error first.** Vercel's crash page never shows the actual Python
   traceback (by design, and this app also disables debug output in production). Go to
   your project on vercel.com → **Deployments** → click the deployment → **Runtime Logs**
   (or run `vercel logs <your-deployment-url>` from the CLI). The traceback there will
   name the exact exception and line — everything below is an educated guess without it.
2. **Confirm environment variables are actually set in Vercel**, not just in your local
   `.env`. Project Settings → Environment Variables should list `SECRET_KEY`,
   `DATABASE_URL`, `APP_BASE_URL`, `FLASK_ENV=production`, and the `CLOUDINARY_*` vars.
   If `DATABASE_URL` is missing, the app silently falls back to a local SQLite file path —
   which is read-only on Vercel's filesystem — and **every single page that touches the
   database crashes immediately**, including the homepage. This is the single most common
   cause of the exact crash shown in a fresh deploy.
3. **If tables are still missing**: this should now be automatic (see Section 7 above),
   but confirm `AUTO_CREATE_TABLES` wasn't set to `false`, and check the Runtime Logs for
   a warning like "Could not verify/create database tables on startup" — that means the
   database was unreachable at cold start (wrong connection string, Neon project
   suspended, etc.), not that the feature is missing.
4. **Redeploy after pulling the latest `vercel.json`/`public/` changes** if
   you deployed before these were added — the old `vercel.json` used a legacy
   `builds`/`routes` schema that Vercel's current Python runtime doesn't expect, which can
   itself cause the deployed function to fail to import correctly.
5. **If the build itself fails** (not a runtime crash — the deploy never completes) with
   an error mentioning `uv lock` or `No project table found`, check whether a
   `pyproject.toml` has been added to the repo. Its mere presence switches Vercel's Python
   dependency resolution from `requirements.txt` to `uv`, which then requires a valid
   `[project]` table — this project intentionally has no `pyproject.toml` to avoid that
   failure mode entirely.

### Other issues

- **Profile/business photos not showing up**: all three `CLOUDINARY_CLOUD_NAME`,
  `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` environment variables must be set in
  Vercel — without them, uploads are rejected with a clear on-screen message (the rest of
  the form still saves) rather than silently failing. Get these three values free at
  cloudinary.com → Dashboard, and add them under Project Settings → Environment Variables.
  If they're set and it's still not working, check Runtime Logs for a line starting
  "Cloudinary upload failed" — that'll show the actual API error (bad credentials, quota,
  etc.).
- **Database connection errors**: confirm your Neon connection string includes
  `?sslmode=require` and that the Neon project isn't suspended (free-tier projects can be
  auto-suspended after long inactivity - visiting the Neon dashboard wakes it up).
- **PDF generation fails when triggered outside a request** (e.g. a future scheduled job):
  the app builds public profile URLs via `APP_BASE_URL` directly rather than Flask's
  `url_for` in that scenario, so make sure `APP_BASE_URL` is set correctly in production.
- **Album downloads fail or download as an unrecognized binary file**: as of this version,
  album downloads are served directly from the database (`AlbumVersion.pdf_data`) and never
  depend on Cloudinary at all, so this shouldn't happen for any album generated going
  forward — **generate a new album version and download that one**. This exists because of a
  well-known Cloudinary behavior: free/new accounts block public delivery of PDF and ZIP
  files by default as an anti-malware precaution (uploading still works fine; only serving
  the file back out is blocked), and that restriction is account-level — it overrides a
  file's own access settings, so switching to signed/authenticated delivery URLs doesn't
  bypass it either. If you specifically need an *old* album version that predates this fix
  (one with no database copy) to download: Cloudinary dashboard → **Settings → Security →
  "PDF and ZIP files delivery"** → check **"Allow delivery of PDF and ZIP files"** → Save →
  accept the terms-of-service prompt. As an admin, the flash message on any remaining
  Cloudinary-related download failure names the exact cause directly (regular members see a
  generic message, since they can't act on Cloudinary settings).
- **CSS/JS/images 404 or don't load**: confirm `public/static/` exists and is current. It's
  committed directly to the repo (not generated at build time — see the note in Section 5
  above about why this project avoids a `pyproject.toml`-based build hook). If you've
  changed anything under `app/static/`, run `python build.py` locally and commit the
  updated `public/static/` before deploying.
