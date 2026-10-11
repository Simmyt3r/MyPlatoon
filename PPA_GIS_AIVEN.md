# PPA Lookup + GIS + Aiven setup

MyPlatoon PPA Lookup is an **independent, corps-member-contributed** directory. A PPA (Place of Primary Assignment) is an organisation where an NYSC corps member serves after orientation. Listing a workplace here is **not** NYSC approval, proof of acceptance, nor a guarantee of posting.

## Shipped interfaces

| URL | Access | Purpose |
| --- | --- | --- |
| `/ppas/` | Public | Search reviewed PPAs by name, town/LGA, state, sector and distance |
| `/ppas/geojson` | Public | GeoJSON FeatureCollection with reviewed workplace pins only |
| `/ppas/<id>` | Public for reviewed; owner/admin for pending | PPA details |
| `/ppas/new` | Approved serving members, alumni and admins | Submit a PPA |
| `/ppas/mine` | Signed in | My submitted records and status |
| `/ppas/<id>/edit` | Report owner/admin | Edit; resubmit for approval |
| `/ppas/<id>/experience` | Approved serving members/alumni | Contribute or revise a historical experience |
| `/ppas/review` | Admin | Approve or reject pending entries |
| `/ppas/review/experiences` | Admin | Moderate historical experiences separately |

Location is optional. We do **not** generate imaginary coordinates when a user only provides an address or LGA. Browser location requests happen only when a user explicitly presses *Use my location*. Exact coordinates in the public map are *workplace* coordinates submitted by a member and approved by a moderator. Home locations, sensitive person-level information and contact details are not collected for PPA records.

## Database

An Aiven PostgreSQL service was found with project `simmyt3r`, service
`pg-31f7f560`. A **dedicated database `myplatoon`** was created within
that existing service, and **PostGIS was installed** in that database.
The existing `defaultdb` and other projects have not been changed.

**No passwords are stored in this repository.** The Aiven plugin deliberately
redacts database secrets.

1. Open the [Aiven Console](https://console.aiven.io).
2. Select project `simmyt3r` → PostgreSQL service `pg-31f7f560`.
3. In the service connection information, locate your PostgreSQL connection
   URL and choose database **`myplatoon`**, not `defaultdb`.
   Keep `sslmode=require` on the connection URL.
4. Before switching environments, decide if there are active member profiles
   in the *old* database. **This is a fresh Aiven database**; it does not
   automatically contain any accounts or profiles from Neon or SQLite.
   If old data is needed, back it up and migrate it into Aiven first.
5. GitHub → MyPlatoon → **Settings → Environments → production** → Secrets:
   set `DATABASE_URL_UNPOOLED` to your Aiven **myplatoon** connection URL.
6. GitHub → **Actions → Apply MyPlatoon production migrations → Run workflow**.
   Confirm the migration completes. The latest Alembic revision is
   `63f21ac4db09`. This sets up the application tables, PPA table and
   PostGIS spatial index.
7. Vercel → connected MyPlatoon project → **Settings → Environment Variables**:
   set `AIVEN_DATABASE_URL` to the exact same Aiven **myplatoon** URI.
   This has priority over any old `DATABASE_URL` configured in Vercel.
   Set `AUTO_CREATE_TABLES=false`, `FLASK_ENV=production` and your existing
   `SECRET_KEY` and other required settings.
8. Redeploy **after** migrations. Confirm `/ppas/` loads and that admin
   review and member submission work.

Use Aiven's real service credentials from its console. Do not paste passwords
in GitHub README, issues, chat messages or public build logs.

### Connection URL format (placeholder, not a usable secret)

```dotenv
AIVEN_DATABASE_URL=postgresql://avnadmin:<AIVEN_PASSWORD>@<AIVEN_HOST>:<AIVEN_PORT>/myplatoon?sslmode=require
AUTO_CREATE_TABLES=false
FLASK_ENV=production
```

The runtime uses `AIVEN_DATABASE_URL` when set, otherwise `DATABASE_URL`.
Local automated tests explicitly use isolated in-memory SQLite.

### GIS functionality

Aiven PostGIS runs `ST_DWithin` against the recorded workplace point using
WGS84 latitude/longitude. The PostgreSQL migration adds a partial spatial
GiST index for reviewed PPAs with valid pins. Distances are in **metres**;
users select 5, 10, 20, 50 or 100 km.

Leaflet renders the interactive map. OpenStreetMap raster tiles are used for
low-traffic prototype display with the required attribution. For a large-scale
production rollout, select a dedicated tile provider and respect the
[OSM tile usage policy](https://operations.osmfoundation.org/policies/tiles/).
Do not bulk prefetch tiles or use OSM's community servers as an unrestricted
high-volume production CDN.

### Moderation & data quality

- Only an approved serving member or NYSC alumnus who has a recorded platoon
  can submit a PPA; PCM visitors may still browse.
- First publication and subsequent edits enter `pending`.
- Only admins can approve/reject and see the moderation queue.
- No pending/rejected records or private submitter identifiers appear in
  the public map API or public search.
- Duplicates with the same normalized name, state and LGA are blocked in the
  submission UI (best-effort; a future database constraint/consolidation job
  will improve race handling).
- Notes and accommodation/allowance fields are **crowd-reported** and may be
  outdated; always confirm acceptance with NYSC and the organisation.
- User-facing review labels mean *MyPlatoon moderator review only*, not
  official external verification.

### Production migration caveat

Prior MyPlatoon code was deployed against Neon in earlier work. We have
**not copied** any users from Neon into Aiven automatically. Switching Vercel
to the newly created empty `myplatoon` database without a data transfer
will make existing accounts appear absent, even though the old data remains
on Neon. Back up and transfer the old database before switching production
if you need to retain existing accounts. Do not point multiple applications
at `defaultdb` as a shortcut.
