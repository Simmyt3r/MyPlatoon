# Platoon 5 Digital Album & Networking Directory

**Powered by Silabs & Co Technologies Ltd — With Love for One Nigeria**

A production-ready web platform for members of NYSC 2026 Batch B Stream II,
Platoon 5 to build professional profiles, showcase businesses and skills,
connect with one another, and generate an official digital PDF album.

---

## Features

- **Member profiles** — personal, professional, and business information, skills, social links
- **Privacy controls** — per-field visibility (public / platoon-only / private) for phone, WhatsApp,
  address, and the overall profile; conservative defaults (addresses are private unless changed)
- **Admin workflow** — draft → pending → approved/rejected/suspended, with audit-logged approvals
- **Member & business directories** — search, filter, pagination, mobile-first cards
- **Digital PDF album** — ReportLab-generated, versioned, with per-member QR codes linking to
  live profiles; regenerated on demand rather than on every change
- **Secure image uploads** — validated, re-encoded (metadata stripped), stored on Cloudinary —
  never on the application server's filesystem
- **Notifications & announcements**, **audit logging**, **CSV export**
- **Dating** (optional, `ENABLE_DATING` flag) — members create a separate, opt-in dating
  persona and are automatically ranked-matched against opposite-gender, active personas
  by shared interests, profession, and location. A match only becomes a notified "mutual
  match" when both people rank each other in their own top picks — nothing is shown or
  sent one-sidedly. Includes pause-anytime, a report-and-hide safety flow, and an admin
  moderation queue. Entirely separate storage from the main professional profile/directory —
  dating data never appears in search, the PDF album, or CSV exports.
- **Automated tests** — 90 pytest cases covering auth, profiles, businesses, admin
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
