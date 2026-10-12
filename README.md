# MyPlatoon · Nationwide NYSC Community

## Public landing and community feed

The root **`/`** is a fast, self-contained marketing landing with a short
description of MyPlatoon's NYSC community, key features and Join / Sign in
buttons. It uses no database queries, authentication/session lookups, live
member counts, external JS/CSS, or deployment-specific branding values.
That means the public introduction is still renderable before the final
Aiven/Vercel configuration or during a database outage. This does **not**
mean database-dependent features (registration, feed, directories, jobs,
etc.) will work without their production database.

The existing announcement stream, reactions and community stories have
moved to **`/feed`** and are still available through the sidebar/mobile
Feed links. Shared announcement links now point to `/feed#announcement-ID`.
The public landing intentionally stays content-light: what MyPlatoon is,
who it serves, four essential benefits and clear calls to action.
Tests in `tests/test_landing.py` verify rendering with SQL queries blocked.

## NERD guidance for prospective corps members

**New:** The public [NERD requirements checklist](/nerd/requirements)
organises 38 personal, contact, academic, institutional and document items
into seven printable sections with in-page readiness tracking. This is a
preparation aid based on user-provided requirements, not an official
government registration or document-upload form. MyPlatoon does not store
NINs, identity scans, next-of-kin details or checklist progress.

MyPlatoon offers a public [NERD & NYSC mobilisation guide](/nerd) with links to the official NERD student enrolment, academic deposit receipt, and NYSC registration resources. MyPlatoon support is available on **09039930006**.

**Important:** MyPlatoon is independent. The guide does not connect to NERD's API, issue government certificates or collect NERD login credentials. See [NERD_INTEGRATION.md](NERD_INTEGRATION.md) for current scope, official source links and partnership prerequisites.


**Powered by Silabs & Co Technologies Ltd — With Love for One Nigeria**

MyPlatoon is a nationwide, independent NYSC community for prospective corps
members (PCMs), serving corps members and ex-corps members. The platform
connects each member to their actual orientation-camp cohort, not a single
hardcoded Platoon 5. Users may share skills, businesses and selected profile
details while respecting platoon-level privacy. Albums are community
publications, not official NYSC documents.

---

## Platoon Power Rankings

The public [Platoon Power Rankings](/platoons/rankings) compare real
NYSC cohorts scoped by state, year, batch, stream and platoon number.
Scores are based on normalized approved-member participation, verified
community contributions and one 1–5-star mini rating per eligible
member for their **own** platoon. Low-sample groups are provisional,
and the board is explicitly **not an official NYSC competition result**.
See [DISCOVERY_RANKINGS.md](DISCOVERY_RANKINGS.md).

## Jobs & Gigs

The nationwide [Jobs & Gigs board](/jobs/) brings paid part-time gigs,
school tutoring work, internships, contracts and full-time job listings
into MyPlatoon. Schools and businesses can register as independent employer
accounts with no fake NYSC platoon, or existing members can link an
organisation to their account. Employer accounts and listings both require
moderator review before postings appear publicly.

Approved members can apply to jobs and follow status updates; the employer
receives only the contact details deliberately provided on the application.
No recruitment, activation or application fees are collected, and job
postings are not NYSC endorsements. Personalised recommendations, private
saved vacancies and opt-in in-app notifications are also available for
approved members. See [JOBS_GIGS.md](JOBS_GIGS.md) and
[DISCOVERY_RANKINGS.md](DISCOVERY_RANKINGS.md).

## Services and career support

The public **Services & Career Tools** hub is available at `/services`.
It links to MyPlatoon's PPA Lookup, NERD guidance and the separately hosted
[CareerMirror](https://mycareermirror.vercel.app/) website for CV/résumé
preparation. CareerMirror is an **external service**, not part of MyPlatoon's
database, authentication or content-management systems. Clicking its link
opens a new tab; MyPlatoon sends no personal profile information to it.

CareerMirror was added as a link-only service. No database migrations,
API keys, login synchronisation or new environment variables are required.
Website configuration and deployment remain deferred to final setup.

## PPA lookup and GIS

The [PPA Lookup](/ppas/) helps PCMs and corps members find community-reported
Places of Primary Assignment nationwide. Approved corps members and alumni
can submit workplaces and add historical experiences to existing listings;
moderators must review both before they become public. Browse by state,
town, sector or distance. The GIS map is powered by Leaflet and PostGIS and
never maps private member residences.

**Aiven database:** service `pg-31f7f560` in project `simmyt3r`, dedicated
`myplatoon` database with PostGIS. To deploy, see
[PPA_GIS_AIVEN.md](PPA_GIS_AIVEN.md). Data from an earlier Neon or SQLite
deployment has **not** been automatically transferred.

## Nationwide membership rules

- Every member has a **platoon assignment state**.
- **PCM:** platoon is `NULL` and the UI says “Awaiting camp assignment.”
- **Serving member or alumnus:** must enter complete camp details before registration can finish or profile changes can be accepted.
- Platoon uniqueness: state + camp year + batch + stream + platoon number. The same number in two camps does not mean the same community.
- Members' camp details are self-reported, NOT verified by an NYSC API.
- Contact information or profiles marked **platoon-only** are visible exclusively to approved members of that same recorded cohort.
- Albums belong to one platoon. Previous unspecific album records are visible only to administrators.
- Old accounts are intentionally not assigned invented platoon numbers; users must supply them.

PCM guide: `/platoons/guide`. NERD guide: `/nerd`.

## Database upgrade before deployment

The new fields require a schema migration on existing deployments. **Do not rely on
`db.create_all()` to add columns to the existing `profiles` table.**

In GitHub, go to **Settings → Environments**, create/select `production`, and
configure a secret named `DATABASE_URL_UNPOOLED` with a database migration
connection URL. Take a database backup before updating an existing deployment.

Then go to **Actions → Apply MyPlatoon production migrations → Run workflow**.
The workflow runs `scripts/upgrade_nysc_schema.py`, detecting clean databases,
fully verified old unversioned installations, or already-versioned installations.
It refuses ambiguous partial schemas rather than erasing data.

See `migrations/versions/0d842ac781b6_nationwide_platoons.py` and
`DEPLOYMENT.md`. After migrations, redeploy via your Vercel dashboard.

## Features

- **NYSC journey and platoons** — PCM (awaiting assignment), serving and alumni.
  A platoon is uniquely identified by orientation **state, year, batch, stream and
  platoon number**. PCMs do not have to invent an assignment.
- **Member profiles** — personal, professional, and business information, skills, social links
- **Privacy controls** — per-field visibility (public / platoon-only / private) for phone, WhatsApp,
  address, and the overall profile; conservative defaults (addresses are private unless changed)
- **Admin workflow** — draft → pending → approved/rejected/suspended, with audit-logged approvals
- **Member & business directories** — search, filter, pagination, mobile-first cards
- **Platoon-scoped PDF album** — generated per verified cohort identity, with QR codes linking to
  live profiles; regenerated on demand rather than on every change
- **Secure image uploads** — validated, re-encoded (metadata stripped), stored on Cloudinary —
  never on the application server's filesystem
- **Notifications & announcements**, **audit logging**, **CSV export**
- **Dating v2** (optional, `ENABLE_DATING` flag) — an adults-only opt-in
  community with separate personas, photo-sharing consent, inclusive
  preferences, interest/skill-based discovery, block/report/pause/delete,
  and limited persona previews that do not expose member contact details.
  Automatic mutual top picks are **suggestions only**. A connection exists,
  and both users are notified, **only when both explicitly express interest**.
  Unilateral interests are private. Reciprocal connections can privately
  exchange text messages and report abuse without disclosing their phone
  numbers or full profiles. See [DATING_UPGRADE.md](DATING_UPGRADE.md).
- **Automated tests** — pytest cases covering auth, profiles, businesses, admin
  authorization, album/PDF generation, security boundaries, generic-platform behavior,
  and the dating matching/notification/moderation flow

## Branding & White-Labeling

This is a generic community-directory platform — everything that makes a deployment look
like "Platoon 5" (name, subtitle, motto, powered-by line, theme colors, brand initials,
member label) is controlled entirely by environment variables, not hardcoded in the
templates or PDF generator. Set these in `.env` (see `.env.example`) to deploy the exact
same codebase for a different group with zero code changes:

```
APP_NAME, APP_SHORT_NAME, APP_SUBTITLE, APP_MOTTO, APP_TAGLINE, POWERED_BY,
APP_BRAND_INITIALS, APP_MEMBER_LABEL, APP_PRIMARY_COLOR, APP_ACCENT_COLOR
```

Leave `APP_SUBTITLE`/`APP_MOTTO`/`POWERED_BY` blank to omit them from the UI entirely.
Note that `APP_PRIMARY_COLOR`/`APP_ACCENT_COLOR` only override the two base theme colors —
derived shades (darker/lighter variants) stay fixed in `app/static/css/style.css`, so a
very different hue may need a manual pass there for full consistency.

## Technology Stack

| Layer | Choice |
|---|---|
| Backend | Python 3.11+, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-WTF, Flask-Limiter |
| Database | PostgreSQL (Neon in production; SQLite for local/test convenience) |
| Frontend | HTML5, Bootstrap 5, vanilla JS, Font Awesome — mobile-first |
| Image storage | Cloudinary (never the application filesystem) |
| PDF | ReportLab |
| QR codes | `qrcode` |
| Hosting | Vercel (serverless Python runtime) |
| Tests | pytest |

## Project Structure

```
platoon5/
├── app/
│   ├── __init__.py          # application factory
│   ├── config.py            # environment-based configuration
│   ├── extensions.py        # Flask extension instances
│   ├── cli.py                # flask create-admin / init-categories
│   ├── models/                # SQLAlchemy models
│   ├── blueprints/            # main, auth, profile, business, directory, admin, album
│   ├── services/               # cloudinary, qr, pdf, album, privacy, audit, notification
│   ├── forms/                   # Flask-WTF forms
│   ├── templates/                # Jinja2 templates (Bootstrap 5)
│   └── static/                    # CSS, JS, images
├── tests/                # pytest suite
├── scripts/seed.py       # development seed data
├── wsgi.py               # WSGI entry point
├── vercel.json            # Vercel deployment config
├── requirements.txt
└── .env.example
```

## Local Development

### 1. Prerequisites
- Python 3.11+
- A PostgreSQL database (or just use the SQLite fallback for quick local testing)
- A Cloudinary account (free tier is fine) — optional locally; without it, image uploads fall
  back to a placeholder image so the app still runs

### 2. Setup

```bash
git clone <your-repo-url> platoon5
cd platoon5
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# edit .env with your DATABASE_URL, SECRET_KEY, Cloudinary credentials, etc.
```

### 3. Database

```bash
export FLASK_APP=wsgi.py
flask db init          # first time only
flask db migrate -m "Initial schema"
flask db upgrade
flask init-categories  # populate default business categories
flask create-admin     # create your first administrator account
```

Everything above also happens **automatically on startup** if you don't run it manually —
tables and default categories are created if missing, and if you set
`ADMIN_INIT_EMAIL`/`ADMIN_INIT_PASSWORD` in `.env`, a first admin account is created too
(only once — it's a no-op on every later restart, and never overwrites an existing
account). This is what makes a fresh Neon+Vercel deploy work with zero manual setup
steps. See `DATABASE.md` for details and `SECURITY.md` for why there's no default
password baked into the code.

Alternatively, for a quick start with demo data:

```bash
python scripts/seed.py
```

This creates a demo admin (`admin.demo@example.com` / `ChangeMe123!`) and several sample
members and businesses. **These are clearly-marked demo accounts — never use this script
against a production database.**

### 4. Run

```bash
flask run
# or
python wsgi.py
```

Visit `http://localhost:5000`.

### 5. Run tests

```bash
pytest
```

See [TESTING.md](TESTING.md) for details on what's covered.

## Environment Variables

See [`.env.example`](.env.example) for the full list. Never commit a real `.env` file.

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full Vercel + Neon + Cloudinary deployment walkthrough.

## Database

See [DATABASE.md](DATABASE.md) for the schema and relationships.

## Security

See [SECURITY.md](SECURITY.md) for the security model and privacy-by-default design.

## API

Where the app exposes JSON-friendly endpoints (CSV export, etc.), see [API.md](API.md).
Most of the application is server-rendered (Jinja2 + Bootstrap), not a JSON API.

## License & Ownership

This project is developed and maintained by **Silabs & Co Technologies Ltd** (RC 7740645),
Abuja & Biu, Borno State, Nigeria, for the members of NYSC 2026 Batch B Stream II, Platoon 5.

*With Love for One Nigeria.*
